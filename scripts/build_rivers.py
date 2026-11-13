"""Rivers (国土数値情報 W05, 2007-2009 by region) and lakes (W09-05) for analysis and the 3D viewer.

Input:  data/raw/ksj_w05/extracted/W05-YY_PP_GML/**/W05-YY_PP-g_Stream.shp  (one per prefecture,
            the newest edition available: 2009 北海道・近畿, 2008 関東・中部・中国, 2007 others,
            2006 四国), Shift-JIS, JGD2000 lon/lat without .prj
        data/raw/ksj_w09/extracted/W09-05-g_Lake.shp
Output: data/processed/rivers/pref=XX/data.parquet  every W05 stream segment (EPSG:6668)
        data/processed/lakes.parquet
        output/3d/rivers.geojson  1級・2級 rivers merged per river_code and class, simplified
        output/3d/lakes.geojson   lakes, simplified

Columns  system      水系域コード (6 digits)
         river_code  河川コード (水系 6 + 河川番号 4; 番号 0001 = 本川)
         section     区間種別 1 1級直轄, 2 1級指定, 3 2級, 4 指定区間外, 0 不明
                     (W05 codes 5-8 = the same + 湖沼区間; folded into 1-4, lake flag kept)
         name        河川名 ("名称不明" -> NA)

Licence: W05 is 非商用 (non-commercial only). Credit 国土数値情報 when publishing.
Run: .venv/bin/python scripts/build_rivers.py [tolerance_m]   (default 30)
"""

import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

ROOT = Path(__file__).resolve().parent.parent
W05 = ROOT / "data" / "raw" / "ksj_w05" / "extracted"
W09 = ROOT / "data" / "raw" / "ksj_w09" / "extracted" / "W09-05-g_Lake.shp"
PROC = ROOT / "data" / "processed"
OUT = ROOT / "output" / "3d"
TOL = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
LCC = "+proj=lcc +lat_1=30 +lat_2=42 +lat_0=36 +lon_0=136 +ellps=GRS80 +units=m +no_defs"
JGD2000 = "EPSG:4612"


def stream_file(pref: str) -> Path:
    files = sorted(W05.glob(f"W05-*_{pref}_GML/**/W05-*_{pref}-g_Stream.shp"), reverse=True)
    return files[0]  # newest edition first


def read_pref(pref: str) -> gpd.GeoDataFrame:
    f = stream_file(pref)
    # a few streams are single-point lines; read them as null and drop them
    g = gpd.read_file(f, encoding="cp932", on_invalid="ignore")
    g = g[g.geometry.notna()].set_crs(JGD2000).to_crs(6668)
    sec = g["W05_003"].astype(int)
    out = gpd.GeoDataFrame({
        "system": g["W05_001"], "river_code": g["W05_002"],
        "section": sec.where(sec < 5, sec - 4).astype("int8"), "lake": sec >= 5,
        "name": g["W05_004"].where(g["W05_004"] != "名称不明"),
        "edition": f.name[:6],
    }, geometry=g.geometry, crs=6668)
    return out


def viewer_rivers(parts: list[gpd.GeoDataFrame]) -> dict:
    g = pd.concat(parts, ignore_index=True)
    g = g[g["section"].isin([1, 2, 3])]
    # a segment on a prefecture border can appear in both files
    g = g[~g.geometry.to_wkb().duplicated()]
    g = g.to_crs(LCC)
    m = g.dissolve(by=["river_code", "section"], aggfunc={"name": "first"}).reset_index()
    m["geometry"] = shapely.line_merge(m.geometry.values)
    m["geometry"] = m.geometry.simplify(TOL)
    m["main"] = m["river_code"].str.endswith("0001")
    m = m.to_crs(6668)
    feats = []
    for r in m.itertuples():
        coords = [np.round(shapely.get_coordinates(p), 5).tolist() for p in shapely.get_parts(r.geometry) if not p.is_empty]
        coords = [c for c in coords if len(c) >= 2]
        if coords:
            feats.append({"type": "Feature",
                          "properties": {"n": None if pd.isna(r.name) else r.name, "s": int(r.section), "m": bool(r.main)},
                          "geometry": {"type": "MultiLineString", "coordinates": coords}})
    return {"type": "FeatureCollection", "features": feats}


def lakes() -> gpd.GeoDataFrame:
    g = gpd.read_file(W09, encoding="cp932").set_crs(JGD2000).to_crs(6668)
    return g.rename(columns={"W09_001": "name", "W09_002": "city_code", "W09_003": "max_depth", "W09_004": "water_level"})


def main() -> None:
    parts = []
    for i in range(1, 48):
        pref = f"{i:02d}"
        g = read_pref(pref)
        d = PROC / "rivers" / f"pref={pref}"
        d.mkdir(parents=True, exist_ok=True)
        g.to_parquet(d / "data.parquet")
        parts.append(g)
    allg = pd.concat(parts)
    print(f"segments {len(allg):,}  by section {allg['section'].value_counts().sort_index().to_dict()}")

    lk = lakes()
    lk.to_parquet(PROC / "lakes.parquet")
    lk_v = lk.to_crs(LCC)
    lk_v["geometry"] = lk_v.geometry.simplify(TOL)
    lk_v = lk_v[~lk_v.geometry.is_empty].to_crs(6668)
    lk_fc = json.loads(lk_v[["name", "geometry"]].rename(columns={"name": "n"}).to_json(drop_id=True))
    for f in lk_fc["features"]:
        f["geometry"]["coordinates"] = json.loads(json.dumps(f["geometry"]["coordinates"]),
                                                  parse_float=lambda s: round(float(s), 5))

    for name, fc in [("rivers.geojson", viewer_rivers(parts)), ("lakes.geojson", lk_fc)]:
        (OUT / name).write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")))
        print(f"{name}: {len(fc['features']):,} features, {(OUT / name).stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
