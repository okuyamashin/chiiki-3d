"""国土数値情報 G04-a (標高・傾斜度3次メッシュ, 2011) -> one nationwide Parquet.

Input:  data/raw/ksj_g04a/extracted/G04-a-11_*_ElevationAndSlopeAngleTertiaryMesh.shp
        (download: https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-G04-a.html, 176 1st-meshes)
Output: data/processed/elevation_mesh3.parquet, one row per 3rd mesh (~1 km, 30" x 45"):
  mesh3, lon, lat (cell center), elev_mean/max/min [m], slope_mean/max/min [deg],
  slope_max_dir / slope_min_dir (direction code). "unknown" (sea / no data) -> NA.
Run:    .venv/bin/python scripts/build_elevation.py
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "raw" / "ksj_g04a" / "extracted"
OUT = ROOT / "data" / "processed" / "elevation_mesh3.parquet"
COLS = {
    "G04a_001": "mesh3", "G04a_002": "elev_mean", "G04a_003": "elev_max", "G04a_004": "elev_min",
    "G04a_005": "elev_min_code", "G04a_006": "slope_max", "G04a_007": "slope_max_dir",
    "G04a_008": "slope_min", "G04a_009": "slope_min_dir", "G04a_010": "slope_mean",
}


def mesh3_center(code: pd.Series) -> tuple[pd.Series, pd.Series]:
    s = code.astype(str)
    p, u, q, v, r, w = (s.str[i:j].astype(int) for i, j in [(0, 2), (2, 4), (4, 5), (5, 6), (6, 7), (7, 8)])
    lat = p / 1.5 + q / 12 + r / 120 + 1 / 240
    lon = u + 100 + v / 8 + w / 80 + 1 / 160
    return lon, lat


frames = []
for f in sorted(SRC.glob("G04-a-11_*_ElevationAndSlopeAngleTertiaryMesh.shp")):
    frames.append(gpd.read_file(f, ignore_geometry=True, encoding="cp932"))
df = pd.concat(frames, ignore_index=True).rename(columns=COLS)[list(COLS.values())]
df["mesh3"] = df["mesh3"].astype("int64")
df = df.drop_duplicates("mesh3")
for c in df.columns.drop("mesh3"):
    df[c] = pd.to_numeric(df[c], errors="coerce")
df["lon"], df["lat"] = mesh3_center(df["mesh3"])
df = df[["mesh3", "lon", "lat"] + list(COLS.values())[1:]]
OUT.parent.mkdir(parents=True, exist_ok=True)
df.to_parquet(OUT, index=False)
print(f"{len(df):,} meshes, {df.elev_mean.notna().sum():,} with data -> {OUT.relative_to(ROOT)}")
print(df.describe().round(1).T.to_string())
