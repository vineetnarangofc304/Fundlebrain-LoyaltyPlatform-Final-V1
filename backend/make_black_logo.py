"""Recolor the light-grey 'fundle' wordmark letters to solid black,
preserving the colourful accent icons (fork/spoon/swoosh). Keeps transparency."""
from PIL import Image
import colorsys

SRC = "/app/backend/fundle_logo_white.png"
DST = "/app/backend/fundle_logo_black.png"

img = Image.open(SRC).convert("RGBA")
print("size", img.size)
px = img.load()
w, h = img.size
for y in range(h):
    for x in range(w):
        r, g, b, a = px[x, y]
        if a == 0:
            continue
        mx, mn = max(r, g, b), min(r, g, b)
        sat = 0 if mx == 0 else (mx - mn) / mx
        # low-saturation (grey/white/near-white) => make black, keep alpha
        if sat < 0.18:
            px[x, y] = (0, 0, 0, a)
        # else keep the colourful accent pixel as-is

img.save(DST)
print("WROTE", DST)
