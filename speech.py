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


@contextlib.asynccontextmanager
async def lifespan(app):
    yield
    gc.collect()


app = OpenAIStub(lifespan=lifespan)
args = None


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
    voice_map = map_voice_to_speaker(voice, 'tts-1')
    try:
        piper_model = voice_map['model']

    except KeyError as e:
        raise ServiceUnavailableError(f"Configuration error: tts-1 voice '{voice}' is missing 'model:' setting. KeyError: {e}")

    speaker = voice_map.get('speaker', None)

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

    parser.add_argument('-P', '--port', action='store', default=8000, type=int, help="Server tcp port")
    parser.add_argument('-H', '--host', action='store', default='0.0.0.0', help="Host to listen on, Ex. 0.0.0.0")
    parser.add_argument('-L', '--log-level', default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Set the log level")

    args = parser.parse_args()

    default_exists('config/pre_process_map.yaml')
    default_exists('config/voice_to_speaker.yaml')

    logger.remove()
    logger.add(sink=sys.stderr, level=args.log_level)

    app.register_model('tts-1')

    uvicorn.run(app, host=args.host, port=args.port)