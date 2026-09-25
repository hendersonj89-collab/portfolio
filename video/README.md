# Mosaic Forest Management — 60s motion-graphics spot, 100% code

A one-minute brand film generated entirely programmatically. No footage, no
stock assets, no DAW: every pixel is drawn with **pycairo** and every sample is
synthesised with **numpy/scipy**. Art direction follows mosaicforests.com —
white/taupe palette, topographic contour lines, Jost type, the gradient-ring "O".

| | |
|---|---|
| Output | `out/final.mp4` — 1920×1080, 30 fps, H.264 + AAC (`final_web.mp4` is a smaller encode) |
| Visuals | `render.py` — cairo vector rendering, contourpy contour lines, 4-process parallel encode via ffmpeg |
| Audio | `audio.py` — felt-piano ostinato, strings, bass, soft percussion, written lead, whooshes on the cuts (G major, 96 BPM) |
| Fonts | Jost + Inter (`fonts/ttf`, OFL) |

## Storyboard

| Time | Scene | What it shows |
|---|---|---|
| 0–7s | **Title** | Contour lines draw on; MOSAIC wordmark builds with the gradient-ring O; "Innovation and stewardship meet here." |
| 7–17s | **Redefining the forest economy** | One land mosaic at the centre, six land uses radiating out: forestry, renewable energy, watershed services, recreation, real estate, carbon |
| 17–29s | **Koksilah Watershed pilot** | River draws on, riparian buffers widen, harvest blocks near water turn to retained forest, roads disappear, 715 ha set-aside, monitoring sparklines |
| 29–39s | **One forest. Many ages.** | Voronoi mosaic of patches cycling harvest → planted → growing → mature on their own clocks; protected areas hatched |
| 39–49s | **B.C. mills first** | Real coastline (Natural Earth 10m) with 14 mill towns placed by lat/lon, counts to 60+ / 30; "100% first offered to domestic mills" |
| 49–55s | **Keeping B.C. working** | Fibre to mills · workers & contractors · coastal communities |
| 55–60s | **Outro** | Wordmark, tagline, mosaicforests.com |

Scene cuts use a mosaic tile-wipe; the cut times are shared with `audio.py`
so whooshes and low booms land exactly on them.

Copy and figures are taken from mosaicforests.com (Koksilah pilot release,
Log Sales & Market Access page).

## Build

```bash
pip install numpy scipy pycairo contourpy imageio-ffmpeg   # shapely only to regenerate data/coast.json
cp fonts/ttf/*.ttf ~/.local/share/fonts/ && fc-cache -f
python render.py          # -> out/video.mp4  (~4 min on 4 cores)
python audio.py           # -> out/audio.wav
ffmpeg -i out/video.mp4 -i out/audio.wav -c:v copy -c:a aac -b:a 192k -shortest out/final.mp4
```

`python render.py --stills 150 400 780` dumps PNG frames for quick checks;
`--scale 0.5` renders a fast low-res preview.
