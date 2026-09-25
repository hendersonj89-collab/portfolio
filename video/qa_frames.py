#!/usr/bin/env python3
"""Extract QA frames from a rendered mp4 into out/qa/<name>/: every `step` seconds, plus a dense
sweep over [dense_from, dense_to] every `dense_step` seconds. Prints one line per frame: path + time."""
import os, subprocess, sys
import imageio_ffmpeg

video, name = sys.argv[1], sys.argv[2]
step = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
dense = (float(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6])) if len(sys.argv) > 6 else None
outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "qa", name)
os.makedirs(outdir, exist_ok=True)
ff = imageio_ffmpeg.get_ffmpeg_exe()
info = subprocess.run([ff, "-i", video], capture_output=True).stderr.decode(errors="ignore")
hh, mm, ss = info.split("Duration: ")[1].split(",")[0].split(":")
dur = int(hh) * 3600 + int(mm) * 60 + float(ss)
times = sorted(set([round(x * step, 2) for x in range(int(dur / step) + 1)] +
                   ([round(dense[0] + i * dense[2], 2) for i in range(int((dense[1] - dense[0]) / dense[2]) + 1)] if dense else [])))
for t in times:
    if t >= dur: continue
    p = os.path.join(outdir, f"t{t:07.2f}.png")
    subprocess.check_call([ff, "-y", "-loglevel", "error", "-ss", str(t), "-i", video, "-frames:v", "1", "-vf", "scale=960:-1", p])
    print(p, t)
