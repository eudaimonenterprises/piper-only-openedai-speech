#!/usr/bin/env python3
import argparse
import contextlib
import gc
import json
import os
import re
import subprocess
import sys

from fastapi.responses import StreamingResponse
from loguru import logger
from openedai import OpenAIStub, BadRequestError, ServiceUnavailableError
from pydantic import BaseModel
import uvicorn
import yaml
import py3langid
import requests

@contextlib.asynccontextmanager
async def lifespan(app):
    yield
    gc.collect()


app = OpenAIStub(lifespan=lifespan)
args = None


# Load voice map and extract supported language codes
with open('voice_to_speaker.default.yaml', 'r', encoding='utf8') as f:
    voice_map = yaml.safe_load(f)
SUPPORTED_LANGS = set(voice_map.get('tts-1', {}).keys())

def get_voice_for_text(text: str, fallback_voice: str) -> str:
    """Detect language from text; if unsupported, use the user-selected voice"""
    try:
        lang, _ = py3langid.classify(text)
        detected = lang[:2]
        return detected if detected in SUPPORTED_LANGS else fallback_voice
    except Exception:
        return fallback_voice

def download_piper_model(model_name: str, voice_path: str = "voices"):
    """Download missing Piper .onnx model from HuggingFace"""
    import requests
    
    clean_name = model_name.replace('.onnx', '')
    parts = clean_name.split('-')
    if len(parts) < 3:
        logger.error(f"Cannot parse model name: {model_name}")
        return False
    
    lang_region = parts[0]
    voice_name = parts[1]
    quality = parts[2]
    
    region = lang_region.split('_')[1] if '_' in lang_region else lang_region
    base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/"
    folder_path = f"{lang_region[:2]}/{region}/{voice_name}/{quality}"
    
    for ext in [".onnx", ".onnx.json"]:
        filename = f"{clean_name}{ext}"
        url = f"{base_url}{folder_path}/{filename}"
        local_path = os.path.join(voice_path, filename)
        
        if os.path.isfile(local_path):
            continue
        
        logger.info(f"Downloading {filename}...")
        try:
            r = requests.get(url, allow_redirects=True, timeout=30)
            r.raise_for_status()
            with open(local_path, 'wb') as f:
                f.write(r.content)
            logger.success(f"Downloaded: {local_path}")
        except Exception as e:
            logger.error(f"Failed to download {filename}: {e}")
            return False
    
    return True

def default_exists(filename: str):
    if not os.path.exists(filename):
        fpath, ext = os.path.splitext(filename)
        basename = os.path.basename(fpath)
        default = f"{basename}.default{ext}"
        
        logger.info(f"{filename} does not exist, setting defaults from {default}")

        with open(default, 'r', encoding='utf8') as from_file:
            with open(filename, 'w', encoding='utf8') as to_file:
                to_file.write(from_file.read())


# Read pre process map on demand so it can be changed without restarting the server
def preprocess(raw_input):
    default_exists('config/pre_process_map.yaml')
    with open('config/pre_process_map.yaml', 'r', encoding='utf8') as file:
        pre_process_map = yaml.safe_load(file)
        for a, b in pre_process_map:
            raw_input = re.sub(a, b, raw_input)
    
    raw_input = raw_input.strip()
    return raw_input


# Read voice map on demand so it can be changed without restarting the server
def map_voice_to_speaker(voice: str, model: str):
    default_exists('config/voice_to_speaker.yaml')
    with open('config/voice_to_speaker.yaml', 'r', encoding='utf8') as file:
        voice_map = yaml.safe_load(file)
        try:
            return voice_map[model][voice]

        except KeyError as e:
            raise BadRequestError(f"Error loading voice: {voice}, KeyError: {e}", param='voice')


class GenerateSpeechRequest(BaseModel):
    model: str = "tts-1"
    input: str
    voice: str = "alloy"
    response_format: str = "mp3"
    speed: float = 1.0


def build_ffmpeg_args(response_format, input_format, sample_rate):
    # Convert the output to the desired format using ffmpeg
    if input_format == 'WAV':
        ffmpeg_args = ["ffmpeg", "-loglevel", "error", "-f", "WAV", "-i", "-"]
    else:
        ffmpeg_args = ["ffmpeg", "-loglevel", "error", "-f", input_format, "-ar", sample_rate, "-ac", "1", "-i", "-"]
    
    if response_format == "mp3":
        ffmpeg_args.extend(["-f", "mp3", "-c:a", "libmp3lame", "-ab", "64k"])
    elif response_format == "opus":
        ffmpeg_args.extend(["-f", "ogg", "-c:a", "libopus"])
    elif response_format == "aac":
        ffmpeg_args.extend(["-f", "adts", "-c:a", "aac", "-ab", "64k"])
    elif response_format == "flac":
        ffmpeg_args.extend(["-f", "flac", "-c:a", "flac"])
    elif response_format == "wav":
        ffmpeg_args.extend(["-f", "wav", "-c:a", "pcm_s16le"])
    elif response_format == "pcm":
        ffmpeg_args.extend(["-f", "s16le", "-c:a", "pcm_s16le"])

    return ffmpeg_args


@app.post("/v1/audio/speech", response_class=StreamingResponse)
async def generate_speech(request: GenerateSpeechRequest):
    if len(request.input) < 1:
        raise BadRequestError("Empty Input", param='input')

    input_text = preprocess(request.input)

    if len(input_text) < 1:
        raise BadRequestError("Input text empty after preprocess.", param='input')

    voice = request.voice
    response_format = request.response_format.lower()
    speed = request.speed

    # Set the Content-Type header based on the requested format
    if response_format == "mp3":
        media_type = "audio/mpeg"
    elif response_format == "opus":
        media_type = "audio/ogg;codec=opus" # codecs?
    elif response_format == "aac":
        media_type = "audio/aac"
    elif response_format == "flac":
        media_type = "audio/x-flac"
    elif response_format == "wav":
        media_type = "audio/wav"
    elif response_format == "pcm":
        media_type = "audio/pcm;rate=22050"
    else:
        raise BadRequestError(f"Invalid response_format: '{response_format}'", param='response_format')

    # Piper is the only TTS backend

    # Determine correct voice based on text language + user selection
    voice_to_use = get_voice_for_text(request.input, request.voice)

    try:
        voice_cfg = map_voice_to_speaker(voice_to_use, 'tts-1')
    except BadRequestError as e:
        # Fallback to first available supported language (shouldn't happen with updated default.yaml)
        fallback_lang = list(SUPPORTED_LANGS)[0]
        logger.warning(f"Voice '{voice_to_use}' not found, using '{fallback_lang}'")
        voice_cfg = map_voice_to_speaker(fallback_lang, 'tts-1')

    piper_model = voice_cfg['model']

    # Ensure model file exists; download if missing
    piper_model_path = os.path.join("voices", piper_model)
    if not os.path.isfile(piper_model_path):
        logger.info(f"Model {piper_model} not found. Attempting download...")
        if not download_piper_model(piper_model, "voices"):
            raise ServiceUnavailableError(f"Failed to download model: {piper_model}")

    speaker = voice_cfg.get('speaker', None)

    tts_args = ["piper", "--model", str(piper_model), "--data-dir", "voices", "--download-dir", "voices", "--output-raw"]
    if speaker:
        tts_args.extend(["--speaker", str(speaker)])
    if speed != 1.0:
        tts_args.extend(["--length-scale", f"{1.0/speed}"])

    tts_proc = subprocess.Popen(tts_args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    tts_proc.stdin.write(bytearray(input_text.encode('utf-8')))
    tts_proc.stdin.close()

    try:
        with open(f"{piper_model}.json", 'r') as pvc_f:
            conf = json.load(pvc_f)
            sample_rate = str(conf['audio']['sample_rate'])

    except:
        sample_rate = '22050'

    ffmpeg_args = build_ffmpeg_args(response_format, input_format="s16le", sample_rate=sample_rate)

    # Pipe the output from piper to the input of ffmpeg
    ffmpeg_args.extend(["-"])
    ffmpeg_proc = subprocess.Popen(ffmpeg_args, stdin=tts_proc.stdout, stdout=subprocess.PIPE)

    return StreamingResponse(content=ffmpeg_proc.stdout, media_type=media_type)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='OpenedAI Speech API Server',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('-P', '--port', action='store', default=8001, type=int, help="Server tcp port")
    parser.add_argument('-H', '--host', action='store', default='127.0.0.1', help="Host to listen on, Ex. 127.0.0.1")
    parser.add_argument('-L', '--log-level', default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Set the log level")

    args = parser.parse_args()

    default_exists('config/pre_process_map.yaml')
    default_exists('config/voice_to_speaker.yaml')

    logger.remove()
    logger.add(sink=sys.stderr, level=args.log_level)

    app.register_model('tts-1')

    uvicorn.run(app, host=args.host, port=args.port)