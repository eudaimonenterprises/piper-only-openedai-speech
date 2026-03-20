#!/usr/bin/env python

import argparse
import os
import shutil
import yaml

parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument('sample', action='store', help="Set the wav sample file")
parser.add_argument('-n', '--name', action='store', help="Set the name for the voice (by default will use the WAV file name)")
parser.add_argument('--openai-model', action='store', default="tts-1", help="Set the openai model for the voice (only tts-1 is supported)")
parser.add_argument('--voice-path', action='store', default="voices", help="Set the default voices file path")
parser.add_argument('--config-path', action='store', default="config/voice_to_speaker.yaml", help="Set the config file path")

args = parser.parse_args()

basename = os.path.basename(args.sample)
name_noext, ext = os.path.splitext(basename)

if not args.name:
    args.name = name_noext
else:
    basename = f"{args.name}.wav"

dest_file = os.path.join(args.voice_path, basename)
if args.sample != dest_file:
    shutil.copy2(args.sample, dest_file)

# Create config directory if it doesn't exist
config_dir = os.path.dirname(args.config_path)
if config_dir and not os.path.exists(config_dir):
    os.makedirs(config_dir)

if not os.path.exists(args.config_path):
    # Create a basic config with the piper voice
    if not os.path.exists('config'):
        os.makedirs('config')
    shutil.copy2('voice_to_speaker.default.yaml', args.config_path)

with open(args.config_path, 'r', encoding='utf8') as file:
    voice_map = yaml.safe_load(file) or {}

model_conf = voice_map.get(args.openai_model, {})
# For piper voices, we need to find a matching model
try:
    # Get first available piper model from default config
    with open('voice_to_speaker.default.yaml', 'r') as f:
        default_voice_map = yaml.safe_load(f)
        if args.openai_model in default_voice_map and len(default_voice_map[args.openai_model]) > 0:
            first_voice = list(default_voice_map[args.openai_model].keys())[0]
            default_piper_model = default_voice_map[args.openai_model][first_voice]['model']
        else:
            default_piper_model = 'voices/en_US-libritts_r-medium.onnx'
except:
    default_piper_model = 'voices/en_US-libritts_r-medium.onnx'

# Use the model from an existing voice or default
existing_voices = model_conf if isinstance(model_conf, dict) else {}
if len(existing_voices) > 0:
    first_existing = list(existing_voices.keys())[0]
    if 'model' in existing_voices[first_existing]:
        default_piper_model = existing_voices[first_existing]['model']

model_conf[args.name] = {
    'model': default_piper_model,
    'speaker': os.path.join(args.voice_path, basename),
}
voice_map[args.openai_model] = model_conf

with open(args.config_path, 'w', encoding='utf8') as ofile:
    yaml.safe_dump(voice_map, ofile, default_flow_style=False, allow_unicode=True)

print(f"Updated: {args.config_path}")
print(f"Added voice: {args.openai_model}/{args.name}")
print(f"Added section:")
print(f"{args.openai_model}:")
print(f"  {args.name}:")
print(f"    model: {default_piper_model}")
print(f"    speaker: voices/{basename}")
