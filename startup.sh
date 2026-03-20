#!/bin/bash

[ -f speech.env ] && . speech.env

echo "First startup may download voice models. Please wait."

bash download_voices_tts-1.sh

python speech.py $EXTRA_ARGS $@
