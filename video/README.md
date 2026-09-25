# Mosaic Forest Management — 60s motion-graphics spot, 100% code

A one-minute brand film generated entirely programmatically. No footage, no
stock assets, no DAW: every pixel is drawn with **pycairo** and every sample is
synthesised with **numpy/scipy**.

| | |
|---|---|
| Output | `out/final.mp4` — 1920×1080, 30 fps, H.264 + AAC |
| Visuals | `render.py` — cairo vector rendering, 4-process parallel encode via ffmpeg |
| Audio | `audio.py` — pad, arpeggio, written lead melody, sub/heartbeat, wind, birds, whooshes |
| Fonts | Inter / Inter Display (`fonts/ttf`, OFL) |

## Storyboard

| Time | Scene | What it shows |
|---|---|---|
| 0–8s | **Title** | Mosaic tiles assemble bottom-up into a conifer mark; wordmark + tagline |
| 8–19s | **One forest. Many ages.** | A Voronoi "mosaic" of forest patches, each cycling harvest → planted → growing → mature on its own clock; protected areas hatched |
| 19–30s | **Plant.** | Fractal conifers grow from seedlings across a dawn hillside; 100% replant stat |
| 30–41s | **Grow.** | A 60-year rotation ring (Plant / Grow / Thin / Harvest / Replant) with a live year counter and a tree that grows, is thinned, harvested and replanted inside it |
| 41–51s | **Protect.** | CO₂ particles fly in and become leaves on a growing tree; river; carbon / water / habitat cards |
| 51–56s | **Share.** | A trail draws itself across the landscape with campsite, trail, viewpoint and partnership markers |
| 56–60s | **Outro** | Mark reassembles, "Plant. Grow. Protect. Share.", URL |

Scene cuts use a mosaic tile-wipe; scene boundaries are shared with `audio.py`
so the whooshes and low booms land exactly on the cuts.

## Build

```bash
pip install numpy scipy pycairo imageio-ffmpeg
cp fonts/ttf/*.ttf ~/.local/share/fonts/ && fc-cache -f
python render.py          # -> out/video.mp4  (~4 min on 4 cores)
python audio.py           # -> out/audio.wav
ffmpeg -i out/video.mp4 -i out/audio.wav -c:v copy -c:a aac -b:a 192k -shortest out/final.mp4
```

`python render.py --stills 150 400 780` dumps PNG frames for quick checks;
`--scale 0.5` renders a fast low-res preview.
