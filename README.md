# OpenedAI Speech (Piper-only)

Notice: This software is mostly obsolete and will no longer be updated.

Some Alternatives:

* https://speaches.ai/
* https://github.com/remsky/Kokoro-FastAPI
* https://github.com/astramind-ai/Auralis
* https://lightning.ai/docs/litserve/home?code_sample=speech

----

An OpenAI API compatible text to speech server.

* Compatible with the OpenAI audio/speech endpoint
* Not affiliated with OpenAI in any way, does not require an OpenAI API Key
* A free, private, text-to-speech server using Piper TTS

Full Compatibility:
* `tts-1`: `alloy`, `echo`, `fable`, `onyx`, `nova`, and `shimmer` (configurable)
* response_format: `mp3`, `opus`, `aac`, `flac`, `wav` and `pcm`
* speed 0.25-4.0 (and more)

Details:
* Model `tts-1` via piper tts (very fast, runs on cpu)
* Occasionally, certain words or symbols may sound incorrect, you can fix them with regex

## Recent Changes

Version 0.18.2-piper, 2024-08-16

* Remove all XTTS/Coqui AI dependencies
* Piper is now the only TTS backend
* Simplified installation and configuration

## Installation instructions

### Create a `speech.env` environment file

Copy the `sample.env` to `speech.env` (customize if needed)
```bash
cp sample.env speech.env
```

#### Defaults
```bash
TTS_HOME=voices
HF_HOME=voices
#EXTRA_ARGS=--log-level DEBUG
```

### Option A: Manual installation
```shell
sudo apt install curl ffmpeg
python -m venv .venv
source .venv/bin/activate
pip install -U -r requirements.txt
bash startup.sh
```

### Option B: Docker Image (*recommended*)

```shell
docker compose up
```

## Server Options

```
usage: speech.py [-h] [-P PORT] [-H HOST] [-L {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
```

options:
  -h, --help            show this help message and exit
  -P PORT, --port PORT  Server tcp port (default: 8000)
  -H HOST, --host HOST  Host to listen on, Ex. 0.0.0.0 (default: 0.0.0.0)
  -L {DEBUG,INFO,WARNING,ERROR,CRITICAL}, --log-level Set the log level

## Sample Usage

```shell
curl http://localhost:8000/v1/audio/speech -H "Content-Type: application/json" -d '{"model": "tts-1", "input": "Hello world.", "voice": "alloy", "response_format": "mp3"}' > speech.mp3
```

## Custom Voices Howto

### Piper

  1. Select the piper voice from the piper samples
  2. Update the `config/voice_to_speaker.yaml` with a new section for the voice
  3. New models will be downloaded as needed

## Configuration

The `config/voice_to_speaker.yaml` file maps OpenAI voices to Piper voice models.

Example configuration:

```yaml
tts-1:
  alloy:
    model: voices/en_US-libritts_r-medium.onnx
    speaker: 79
```