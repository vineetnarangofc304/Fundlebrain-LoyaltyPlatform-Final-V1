#!/usr/bin/env python3
"""Render the vertical (9:16) /reel marketing films into narrated, downloadable MP4s.

Renders one or more clips (platform / fundle / master). For each clip:
  1. Fetch its ordered scene ids from GET /api/reel/script/{clip}.
  2. Pull each scene's cached TTS mp3, measure exact durations (ffprobe).
  3. Concatenate the mp3s (scene order) into one narration track.
  4. Drive /reel?clip={clip}&rec=1 headless at 1080x1920, injecting the EXACT per-scene
     durations (window.__REC_DUR__) so each scene occupies precisely its audio length.
  5. Record to webm, then mux the narration over it (ffmpeg) -> reel_{clip}.mp4.

Usage:
  PAGE_BASE_URL=<frontend-origin> [CLIP=platform] python render_reels_mp4.py
  (CLIP omitted -> renders all three)
"""
import json
import os
import subprocess
import sys
import time

import requests

API = "http://localhost:8001"
BASE = os.environ.get("PAGE_BASE_URL", "").rstrip("/")
WORK = "/app/scripts/reel_work"
OUT_DIR = "/app/backend/generated"
TAIL = 0.6
W, H = 1080, 1920

ALL_CLIPS = ["platform", "fundle", "master"]


def sh(cmd):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def ffprobe_dur(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        check=True, capture_output=True, text=True).stdout.strip()
    return float(out)


def render_clip(clip, pw):
    vdir = os.path.join(WORK, clip, "video")
    os.makedirs(vdir, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    order = requests.get(f"{API}/api/reel/script/{clip}", timeout=60).json()["order"]

    durations, mp3_paths = [], []
    for i, sid in enumerate(order):
        p = os.path.join(WORK, clip, f"{i:02d}_{sid}.mp3")
        r = requests.get(f"{API}/api/reel/tts/{clip}/{sid}", timeout=180)
        r.raise_for_status()
        with open(p, "wb") as f:
            f.write(r.content)
        d = ffprobe_dur(p)
        durations.append(round(d, 3))
        mp3_paths.append(p)
        print(f"[{clip}] scene {i:02d} {sid:12s} {d:6.2f}s", flush=True)

    S = round(sum(durations), 3)
    print(f"[{clip}] TOTAL narration = {S:.2f}s over {len(durations)} scenes", flush=True)

    concat_txt = os.path.join(WORK, clip, "concat.txt")
    with open(concat_txt, "w") as f:
        for p in mp3_paths:
            f.write(f"file '{p}'\n")
    narration = os.path.join(WORK, clip, "narration.mp3")
    sh(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c", "copy", narration])

    page_url = f"{BASE}/reel?clip={clip}&rec=1"
    print(f"[{clip}] recording {page_url}", flush=True)
    browser = pw.chromium.launch(
        headless=True,
        args=["--autoplay-policy=no-user-gesture-required", "--no-sandbox",
              "--disable-gpu", "--disable-dev-shm-usage", "--use-gl=swiftshader"])
    context = browser.new_context(
        viewport={"width": W, "height": H}, device_scale_factor=1,
        record_video_dir=vdir, record_video_size={"width": W, "height": H})
    page = context.new_page()
    page.add_init_script(f"window.__REC_DUR__ = {json.dumps(durations)};")
    page.goto(page_url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("() => typeof window.__REC_START__ === 'function'", timeout=30000)
    page.evaluate("() => window.__REC_START__()")
    page.wait_for_function("() => window.__REC_DONE__ === true", timeout=int((S + 90) * 1000))
    page.wait_for_timeout(int(TAIL * 1000))
    video = page.video
    context.close()
    webm = video.path()
    browser.close()

    L = ffprobe_dur(webm)
    trim_start = max(0.0, L - S - TAIL)
    out = os.path.join(OUT_DIR, f"reel_{clip}.mp4")
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p")
    sh(["ffmpeg", "-y", "-ss", f"{trim_start:.3f}", "-i", webm, "-i", narration,
        "-t", f"{S:.3f}", "-map", "0:v:0", "-map", "1:a:0",
        "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
    sz = os.path.getsize(out)
    print(f"[{clip}] DONE -> {out}  ({sz/1e6:.1f} MB, {ffprobe_dur(out):.1f}s)", flush=True)


def main():
    from playwright.sync_api import sync_playwright
    clips = [os.environ["CLIP"]] if os.environ.get("CLIP") else ALL_CLIPS
    with sync_playwright() as pw:
        for c in clips:
            render_clip(c, pw)


if __name__ == "__main__":
    if not BASE:
        print("ERROR: set PAGE_BASE_URL", file=sys.stderr)
        sys.exit(1)
    t0 = time.time()
    main()
    print(f"elapsed {time.time()-t0:.0f}s", flush=True)
