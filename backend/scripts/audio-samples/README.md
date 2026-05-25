# Audio samples for smoke tests (#4 / #5 / #6)

Real .wav files are **not committed** (binary bloat). Generate them locally or supply your own.

## Required format

All smoke scripts expect: **mono · 16-bit · 24kHz PCM** (Realtime API native).

## Convert any wav/mp3 → required format

```bash
ffmpeg -i your_input.mp3 -ac 1 -ar 24000 -sample_fmt s16 backend/scripts/audio-samples/cs_zh_01.wav
```

## Generate a quick synthetic test tone (no ffmpeg needed)

```bash
cd backend
python -c "
from scripts.smoke_translate import make_synthetic_pcm16, write_pcm16_wav
from pathlib import Path
write_pcm16_wav(Path('scripts/audio-samples/tone_1s.wav'), make_synthetic_pcm16(seconds=1.0))
print('wrote scripts/audio-samples/tone_1s.wav')
"
```

## Recommended demo clips for evaluating translate / whisper / assistant

| file                    | content (Chinese)                                                                          | duration |
|-------------------------|--------------------------------------------------------------------------------------------|----------|
| `cs_zh_01_simple.wav`   | "你好，我想问一下订单 A12345 现在到哪里了？"                                                   | ~3s      |
| `cs_zh_02_tariff.wav`   | "我那个咖啡机的订单关税太贵了，能不能退一部分？订单号 A12345。"                                | ~5s      |
| `cs_zh_03_insurance.wav`| "我之前买了保险 INS-7788，这次跨境运费能不能用保险抵掉？"                                      | ~5s      |
| `cs_zh_04_escalate.wav` | "上面那个客服没听懂我说的，我要找你们经理。我说的是订单 A12345 关税要降。"                       | ~7s      |

Record with macOS QuickTime / Windows Voice Recorder, then convert with the ffmpeg command above.
