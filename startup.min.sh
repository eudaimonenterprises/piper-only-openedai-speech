#!/bin/bash

[ -f speech.env ] && . speech.env

bash download_voices_tts-1.sh

python speech.py $EXTRA_ARGS $@
