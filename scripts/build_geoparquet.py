"""Convert raw boundary data into per-prefecture GeoParquet.

Outputs (under data/processed/):
  shochiiki/pref=XX/data.parquet   e-Stat 2020 small areas (町丁・字), one row per polygon
  shochiiki_YYYY/pref=XX/data.parquet  same for 2000/2005/2010/2015 (run with the years as args)
  municipality/pref=XX/data.parquet N03 2025 municipalities, dissolved to one row per 団体コード
  japan_prefectures.parquet / .geojson  simplified prefecture outlines for the nationwide base map

Run: .venv/bin/python scripts/build_geoparquet.py            (2020 + municipalities + prefectures)
     .venv/bin/python scripts/build_geoparquet.py 2000 2005  (older small areas only)
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

SHOCHIIKI_COLS = [
    "PREF", "CITY", "S_AREA", "PREF_NAME", "CITY_NAME", "S_NAME",
    "HCODE", "AREA", "JINKO", "SETAI", "X_CODE", "Y_CODE",
]


# year: (raw dir, shapefile prefix, output dir). 2020 keeps its original paths.
SHOCHIIKI_YEARS = {
    2000: ("estat_shochiiki_2000", "h12ka", "shochiiki_2000"),
    2005: ("estat_shochiiki_2005", "h17ka", "shochiiki_2005"),
    2010: ("estat_shochiiki_2010", "h22ka", "shochiiki_2010"),
    2015: ("estat_shochiiki_2015", "h27ka", "shochiiki_2015"),
    2020: ("estat_shochiiki", "r2ka", "shochiiki"),
}


def build_shochiiki(year: int = 2020) -> None:
    raw_dir, prefix, out_dir = SHOCHIIKI_YEARS[year]
    for i in range(1, 48):
        pref = f"{i:02d}"
        src = RAW / raw_dir / "extracted" / f"{prefix}{pref}.shp"
        g = gpd.read_file(src, encoding="cp932")[SHOCHIIKI_COLS + ["geometry"]]
        # 2010 and earlier are JGD2000 (EPSG:4612); store everything as JGD2011 (EPSG:6668).
        g = g.to_crs(6668)
        # KEY_CODE in the source is occasionally truncated; rebuild the 11-digit key.
        g["key_code"] = g["PREF"].str.zfill(2) + g["CITY"].str.zfill(3) + g["S_AREA"].str.zfill(6)
        g["city_code"] = g["key_code"].str[:5]
        g.columns = [c.lower() for c in g.columns]
        dst = OUT / out_dir / f"pref={pref}" / "data.parquet"
        dst.parent.mkdir(parents=True, exist_ok=True)
        g.to_parquet(dst, compression="zstd")
        print(f"{out_dir} {pref}: {len(g)} rows")


def build_municipality() -> gpd.GeoDataFrame:
    n = gpd.read_file(RAW / "n03" / "extracted" / "N03-20250101.shp")
    n = n.rename(columns={
        "N03_001": "pref_name", "N03_002": "subpref_name", "N03_003": "gun_name",
        "N03_004": "city_name", "N03_005": "ward_name", "N03_007": "city_code",
    })
    # Rows without a code are 所属未定地 (disputed/unassigned land); drop them.
    n = n[n["city_code"].notna()]
    m = n.dissolve(by="city_code", aggfunc="first").reset_index()
    m["pref"] = m["city_code"].str[:2]
    for pref, part in m.groupby("pref"):
        dst = OUT / "municipality" / f"pref={pref}" / "data.parquet"
        dst.parent.mkdir(parents=True, exist_ok=True)
        part.to_parquet(dst, compression="zstd")
    print(f"municipality: {len(m)} rows")
    return m


def build_prefectures(m: gpd.GeoDataFrame) -> None:
    parts = m[["pref", "pref_name", "geometry"]].explode(index_parts=False)
    # Drop islets under ~1 km² (1e-4 deg²); thousands of rocks dominate file size on a national map.
    parts = parts[parts.geometry.area > 1e-4]
    p = parts.dissolve(by="pref", aggfunc="first").reset_index()
    # ~0.01 deg ≈ 1 km: plenty for a nationwide outline map.
    p["geometry"] = p.geometry.simplify(0.01, preserve_topology=True)
    p.to_parquet(OUT / "japan_prefectures.parquet", compression="zstd")
    p.to_file(OUT / "japan_prefectures.geojson", driver="GeoJSON", COORDINATE_PRECISION=4)
    print(f"prefectures: {len(p)} rows")


if __name__ == "__main__":
    import sys

    OUT.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 1:  # e.g. `build_geoparquet.py 2000 2005`: only those years' small areas
        for y in sys.argv[1:]:
            build_shochiiki(int(y))
    else:
        build_shochiiki()
        build_prefectures(build_municipality())
