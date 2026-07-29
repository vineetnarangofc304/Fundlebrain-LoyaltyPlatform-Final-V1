#!/usr/bin/env python3
"""Render the public /watch cinematic reel into a narrated, downloadable MP4.

Strategy for frame-accurate A/V sync:
  1. Pull each scene's cached TTS mp3 from the backend, measure exact durations (ffprobe).
  2. Concatenate the mp3s (in scene order) into one narration track.
  3. Drive the reel in a headless browser with `?rec=1`, injecting the EXACT per-scene
     durations so each scene occupies precisely its audio length -> zero drift.
  4. Record the page to webm, then mux the concatenated narration over it (ffmpeg).
"""
import json
import os
import subprocess
import sys
import time

import requests

SCENE_IDS = [
    "open", "act1", "fb_underperform", "fb_churn", "fb_diagnose", "fb_upload",
    "act2", "mb_topup", "mb_campaign", "mb_reconcile", "mb_rule", "mb_error", "close",
]

API = "http://localhost:8001"
BASE = os.environ.get("PAGE_BASE_URL", "").rstrip("/")
WORK = "/app/scripts/render_work"
VIDEO_DIR = os.path.join(WORK, "video")
OUT = "/app/backend/generated/fundle_film.mp4"
TAIL = 0.6  # seconds we linger after the reel signals done, before closing


def sh(cmd):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def ffprobe_dur(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        check=True, capture_output=True, text=True).stdout.strip()
    return float(out)


def main():
    os.makedirs(VIDEO_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    # 1) fetch mp3s + durations
    durations = []
    mp3_paths = []
    for i, sid in enumerate(SCENE_IDS):
        p = os.path.join(WORK, f"scene_{i:02d}_{sid}.mp3")
        r = requests.get(f"{API}/api/watch/tts/{sid}", timeout=120)
        r.raise_for_status()
        with open(p, "wb") as f:
            f.write(r.content)
        d = ffprobe_dur(p)
        durations.append(round(d, 3))
        mp3_paths.append(p)
        print(f"scene {i:02d} {sid:16s} {d:6.2f}s  {len(r.content)} bytes", flush=True)

    S = round(sum(durations), 3)
    print(f"TOTAL narration = {S:.2f}s across {len(durations)} scenes", flush=True)

    # 2) concat mp3s
    concat_txt = os.path.join(WORK, "concat.txt")
    with open(concat_txt, "w") as f:
        for p in mp3_paths:
            f.write(f"file '{p}'\n")
    narration = os.path.join(WORK, "narration.mp3")
    sh(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c", "copy", narration])
    print("narration duration =", ffprobe_dur(narration), flush=True)

    # 3) record the reel
    from playwright.sync_api import sync_playwright

    page_url = f"{BASE}/watch?rec=1"
    print("recording", page_url, flush=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required", "--no-sandbox",
                  "--disable-gpu", "--disable-dev-shm-usage", "--use-gl=swiftshader"])
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1,
            record_video_dir=VIDEO_DIR,
            record_video_size={"width": 1920, "height": 1080})
        page = context.new_page()
        page.add_init_script(f"window.__REC_DUR__ = {json.dumps(durations)};")
        page.goto(page_url, wait_until="networkidle", timeout=90000)
        page.wait_for_function("() => typeof window.__REC_START__ === 'function'", timeout=30000)
        page.evaluate("() => window.__REC_START__()")
        page.wait_for_function("() => window.__REC_DONE__ === true",
                               timeout=int((S + 90) * 1000))
        page.wait_for_timeout(int(TAIL * 1000))
        video = page.video
        context.close()  # finalizes the webm
        webm = video.path()
        browser.close()
    print("raw video =", webm, flush=True)

    # 4) mux
    L = ffprobe_dur(webm)
    trim_start = max(0.0, L - S - TAIL)
    print(f"video length={L:.2f}s  trim_start={trim_start:.2f}s  keep={S:.2f}s", flush=True)
    vf = ("scale=1920:1080:force_original_aspect_ratio=decrease,"
          "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p")
    sh(["ffmpeg", "-y", "-ss", f"{trim_start:.3f}", "-i", webm, "-i", narration,
        "-t", f"{S:.3f}", "-map", "0:v:0", "-map", "1:a:0",
        "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", OUT])

    sz = os.path.getsize(OUT)
    print(f"DONE -> {OUT}  ({sz/1e6:.1f} MB, {ffprobe_dur(OUT):.1f}s)", flush=True)


if __name__ == "__main__":
    if not BASE:
        print("ERROR: set PAGE_BASE_URL", file=sys.stderr)
        sys.exit(1)
    t0 = time.time()
    main()
    print(f"elapsed {time.time()-t0:.0f}s", flush=True)
