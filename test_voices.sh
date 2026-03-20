#!/bin/bash

URL=${1:-http://localhost:8001/v1/audio/speech}

for voice in alloy echo fable onyx nova shimmer ; do
    echo $voice
    
    curl -s $URL -H "Content-Type: application/json" -d "{
        \"model\": \"tts-1\",
        \"input\": \"The quick brown fox jumped over the lazy dog. This voice is called $voice, how do you like this voice?\",
        \"voice\": \"$voice\",
        \"speed\": 1.0
      }" | mpv --really-quiet -
done

curl -s $URL -H "Content-Type: application/json" -d "{
    \"model\": \"tts-1\",
    \"input\": \"the slowest voice\",
    \"voice\": \"onyx\",
    \"speed\": 0.25
  }" | mpv --really-quiet -

curl -s $URL -H "Content-Type: application/json" -d "{
    \"model\": \"tts-1\",
    \"input\": \"And this is how fast it can go, the fastest voice\",
    \"voice\": \"nova\",
    \"speed\": 4.0
  }" | mpv --really-quiet -
