#!/usr/bin/env bash
# Microphone check with a known sound (P3 without a phone). The PC plays five tones (250 Hz..4 kHz)
# for 20 s while the DK captures 1 s of audio twice over SWD (diag.py audio); the PC's own microphone
# records a reference, so a silent speaker cannot pass for a deaf microphone.
# Needs: firmware running from RAM (BOOT1 = H), PipeWire (pw-play, pw-record), the INMP441 port
# free and facing the PC speakers about 20 cm away.
# Exit: 0 tones heard by the INMP441, 1 not heard (deaf or blocked mic), 2 reference did not hear them.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ENV_SH="${STM32_ENV:-$HOME/2026-2/SSI/tools/stm32-env.sh}"
# shellcheck disable=SC1090
if [ -f "$ENV_SH" ]; then source "$ENV_SH" >/dev/null; fi
OUT="$HERE/../out/mic_check"
mkdir -p "$OUT"
python3 -I "$HERE/tone_lines.py" gen "$OUT/tones.wav" --secs 20

echo "== INMP441, silence"
python3 -I "$HERE/diag.py" audio --out "$OUT/silence" | grep AUDIO
python3 -I "$HERE/tone_lines.py" levels "$OUT/silence/audio.wav"

pw-record --rate 48000 --channels 1 --format s16 "$OUT/reference.wav" &
REC=$!
sleep 0.5
pw-play "$OUT/tones.wav" &
PLAY=$!
sleep 1.5
heard=1
for k in 1 2; do
  echo "== INMP441, tones ($k)"
  python3 -I "$HERE/diag.py" audio --out "$OUT/tones$k" | grep AUDIO
  if python3 -I "$HERE/tone_lines.py" levels "$OUT/tones$k/audio.wav"; then heard=0; fi
done
wait "$PLAY"
kill -INT "$REC" 2>/dev/null
wait "$REC" 2>/dev/null

echo "== PC microphone (reference)"
if ! python3 -I "$HERE/tone_lines.py" levels "$OUT/reference.wav" --start 5; then
  echo "RESULT: INVALID (the reference did not hear the tones: check the PC volume)"
  exit 2
fi
if [ "$heard" -eq 0 ]; then
  echo "RESULT: PASS (the INMP441 hears the tones)"
  exit 0
fi
echo "RESULT: FAIL (the reference hears the tones, the INMP441 does not)"
exit 1
