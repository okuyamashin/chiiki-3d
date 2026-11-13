"""Download GSI elevation tiles (dem_png, DEM10B at z14 ≈ 10 m) covering a lon/lat box.

Tiles: https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png  (国土地理院 標高タイル)
Saved: data/raw/gsi_dem/z{z}/{x}_{y}.png (already downloaded tiles are skipped; 404 = sea, noted).
Run:   .venv/bin/python scripts/fetch_gsi_dem.py minlon minlat maxlon maxlat [z]
"""

import math
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def tile_xy(lon, lat, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return int(x), int(y)


def fetch(minlon, minlat, maxlon, maxlat, z=14):
    d = ROOT / "data" / "raw" / "gsi_dem" / f"z{z}"
    d.mkdir(parents=True, exist_ok=True)
    x0, y0 = tile_xy(minlon, maxlat, z)
    x1, y1 = tile_xy(maxlon, minlat, z)
    got = miss = 0
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            f, nf = d / f"{x}_{y}.png", d / f"{x}_{y}.none"
            if f.exists() or nf.exists():
                continue
            url = f"https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png"
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "dem-fetch"}), timeout=30) as r:
                    f.write_bytes(r.read()); got += 1
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
                nf.touch(); miss += 1
            time.sleep(0.05)
    print(f"z{z} tiles x {x0}-{x1}, y {y0}-{y1}: {(x1-x0+1)*(y1-y0+1)} total, {got} downloaded, {miss} empty")
    return d, (x0, y0, x1, y1)


if __name__ == "__main__":
    a = list(map(float, sys.argv[1:5]))
    fetch(*a, z=int(sys.argv[5]) if len(sys.argv) > 5 else 14)
