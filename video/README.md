# Mosaic Forest Management — 60s motion-graphics spot, 100% code

A 90-second brand film generated entirely programmatically. No footage, no
stock assets, no DAW: every pixel is drawn with **pycairo** and every sample is
synthesised with **numpy/scipy**. Art direction follows mosaicforests.com —
white/taupe palette, topographic contour lines, Jost type, the gradient-ring "O".

| | |
|---|---|
| Output | `out/final.mp4` — 90 s, 1920×1080, 30 fps, H.264 + AAC (`final_web.mp4` is a smaller encode) |
| Visuals | `render.py` — cairo vector rendering, contourpy contour lines, 4-process parallel encode via ffmpeg |
| Audio | `audio.py` — cinematic ambient: string ensemble, sub drone, marimba motif, soft pulse, taiko, shimmer, cello line, whooshes on the cuts (F major, 72 BPM) |
| Voice | `voiceover.py` — Kokoro neural TTS (offline ONNX), one cue per scene, music ducked under the voice |
| Fonts | Jost + Inter (`fonts/ttf`, OFL) |

## Storyboard

| Time | Scene | What it shows |
|---|---|---|
| 0–10s | **Title** | Contour lines draw on; MOSAIC wordmark builds with the gradient-ring O; "Innovation and stewardship meet here." |
| 10–24s | **Redefining the forest economy** | One land mosaic at the centre, six land uses radiating out: forestry, renewable energy, watershed services, recreation, real estate, carbon |
| 24–42s | **Koksilah Watershed pilot** | River draws on, riparian buffers widen, harvest blocks near water turn to retained forest, roads disappear, 715 ha set-aside, monitoring sparklines |
| 42–55s | **One forest. Many ages.** | Voronoi mosaic of patches cycling harvest → planted → growing → mature on their own clocks; protected areas hatched |
| 55–70s | **B.C. mills first** | Real coastline (Natural Earth 10m) with 14 mill towns placed by lat/lon, counts to 60+ / 30; "100% first offered to domestic mills" |
| 70–80s | **Keeping B.C. working** | Fibre to mills · workers & contractors · coastal communities |
| 80–90s | **Outro** | Wordmark, tagline, mosaicforests.com |

Scene cuts use a mosaic tile-wipe; the cut times are shared with `audio.py`
so whooshes and low booms land exactly on them.

Copy and figures are taken from mosaicforests.com (Koksilah pilot release,
Log Sales & Market Access page).

## Build

```bash
pip install numpy scipy pycairo contourpy imageio-ffmpeg kokoro-onnx soundfile   # shapely only to regenerate data/coast.json
cp fonts/ttf/*.ttf ~/.local/share/fonts/ && fc-cache -f
python render.py          # -> out/video.mp4  (~4 min on 4 cores)
python audio.py           # -> out/audio.wav (music)
python voiceover.py       # -> out/voice.wav, out/mix.wav (needs tts/kokoro-v1.0.onnx + tts/voices-v1.0.bin,
                          #    from github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0)
ffmpeg -i out/video.mp4 -i out/mix.wav -c:v copy -c:a aac -b:a 192k -shortest out/final.mp4
```

`python render.py --stills 150 400 780` dumps PNG frames for quick checks;
`--scale 0.5` renders a fast low-res preview.

## Video 2 — "Stump to road" (educational explainer, 2:33)

Same brand system, built for someone who has never seen a logging show. Animated
side-view machinery drawn in cairo: feller-buncher, skidder, processor, log truck,
tower yarder with skyline + carriage, winch-assist anchor and tethered harvester, lowbed.

| Time | Scene | What it shows |
|---|---|---|
| 0–11s | Title | "Stump to road." with the three system glyphs |
| 11–33s | Ground-based | Gentle slope: feller-buncher fells and bunches, skidder shuttles bunches to the landing, processor bucks, loader fills the truck |
| 33–58s | Cable yarding | Steep slope: yarder on the road, skyline to a tailhold, carriage cycles turns uphill, rigging crew at the tail |
| 58–78s | Tethered | Anchor machine + winch on the road, harvester working down the face on the tether |
| 78–103s | Piece size | Same turn with 3 big vs 8 small logs; live cost-per-m³ curve as piece size shrinks (illustrative) |
| 103–123s | Mobilisation | Map with a lowbed moving between blocks; calendar strip of producing vs move days, one big block vs four small |
| 123–145s | Connectivity | Machines with signal arcs feeding a live dashboard; what the data lets us do |
| 145–153s | Outro | "Better data. Better decisions. Stronger contractors." |

```bash
python render_harvest.py      # -> out/harvest_video.mp4 (reuses render.py's engine)
python audio_harvest.py       # -> out/harvest_audio.wav
python voiceover_harvest.py   # -> out/harvest_voice.wav, out/harvest_mix.wav
ffmpeg -i out/harvest_video.mp4 -i out/harvest_mix.wav -c:v copy -c:a aac -b:a 192k -shortest out/harvest_final.mp4
```
