@echo off

set /p < speech.env

call download_voices_tts-1.bat

python speech.py %EXTRA_ARGS%
