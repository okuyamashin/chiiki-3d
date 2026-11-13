"""Main roads: 国土数値情報 N13-24 (road centrelines from 国土基本情報, 2024, CC BY 4.0) and
N06-25 (expressways with route names).

Input:  data/raw/ksj_n13/zip/N13-24_MMMM_SHP.zip  one per 1st-order mesh (160), read in place via /vsizip/
        data/raw/ksj_n06/extracted/N06-25_GML/UTF-8/N06-25_HighwaySection.shp
Output: data/processed/roads/mesh=MMMM/data.parquet   N13 segments with category 1/2/4 only
            (国道・都道府県道・高速自動車国道等; 市区町村道 etc. stay in the raw zips - ~95 % of rows)
        data/processed/expressways.parquet             N06 sections in service now (end year 9999)
        output/3d/roads_main.geojson                   expressways (N06) + 国道 (N13), simplified
The viewer draws 都道府県道 and smaller roads from 国土地理院ベクトルタイル instead of a file.

N13 columns  category  道路分類 1 国道, 2 都道府県道, 3 市区町村道等, 4 高速自動車国道等, 5 その他, 6 不明
             kind      種別 1 通常部, 2 庭園路, 3 徒歩道, 4 石段
             state     道路状態 1 通常部, 2 橋・高架, 3 トンネル, 4 雪囲い, 5 建設中
             width     幅員区分 1 <3m, 2 3-5.5m, 3 5.5-13m, 4 13-19.5m, 5 >=19.5m, 6 不明
             toll      有料区分 1 無料, 2 有料
N06 columns  name, cat (路線種別 1 高速自動車国道 2 並行する自専道 3 一般国道の自専道 4 本四 5 都市高速),
             opened (供用開始年), lanes (999 -> NA)
Licence: N13 CC BY 4.0. N06 is CC BY when used as the current network; using it as a
time series (e.g. opened year over time) is 非商用.

Run: .venv/bin/python scripts/build_roads.py [tolerance_m]   (default 20)
"""

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

ROOT = Path(__file__).resolve().parent.parent
N13 = ROOT / "data" / "raw" / "ksj_n13" / "zip"
N06 = ROOT / "data" / "raw" / "ksj_n06" / "extracted" / "N06-25_GML" / "UTF-8" / "N06-25_HighwaySection.shp"
PROC = ROOT / "data" / "processed"
OUT = ROOT / "output" / "3d" / "roads_main.geojson"
TOL = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
LCC = "+proj=lcc +lat_1=30 +lat_2=42 +lat_0=36 +lon_0=136 +ellps=GRS80 +units=m +no_defs"


def one_mesh(zp: Path) -> tuple[str, int, gpd.GeoDataFrame]:
    """Save the main roads of one mesh; return the simplified 国道 geometry for the viewer."""
    mesh = zp.stem.split("_")[1]
    src = f"/vsizip/{zp}/{zp.stem}/{zp.stem.removesuffix('_SHP')}.shp"
    g = gpd.read_file(src, where="N13_003 IN ('1','2','4')")
    g = gpd.GeoDataFrame({
        "registered": g["N13_001"],
        "kind": g["N13_002"].astype("int8"), "category": g["N13_003"].astype("int8"),
        "state": g["N13_004"].astype("int8"), "level": g["N13_005"].astype("int16"),
        "width": g["N13_006"].astype("int8"), "toll": g["N13_007"].astype("int8"),
        "mesh2": g["N13_008"],
    }, geometry=g.geometry, crs=g.crs)
    d = PROC / "roads" / f"mesh={mesh}"
    d.mkdir(parents=True, exist_ok=True)
    g.to_parquet(d / "data.parquet")
    kokudo = g[g["category"] == 1]
    if kokudo.empty:
        return mesh, len(g), gpd.GeoDataFrame(geometry=[], crs=LCC)
    geom = shapely.line_merge(shapely.union_all(kokudo.to_crs(LCC).geometry.values))
    geom = shapely.simplify(geom, TOL)
    return mesh, len(g), gpd.GeoDataFrame(geometry=[geom], crs=LCC)


def expressways() -> gpd.GeoDataFrame:
    g = gpd.read_file(N06, encoding="utf-8")
    g = g[g["N06_003"].astype(int) == 9999]
    lanes = pd.to_numeric(g["N06_010"], errors="coerce")
    out = gpd.GeoDataFrame({
        "name": g["N06_007"], "cat": g["N06_008"].astype("int8"), "use": g["N06_009"].astype("int8"),
        "opened": g["N06_001"].astype(int), "lanes": lanes.where(lanes != 999).astype("Int16"),
    }, geometry=g.geometry, crs=g.crs)
    out.to_parquet(PROC / "expressways.parquet")
    return out


def lines_coords(geom) -> list:
    out = []
    for p in shapely.get_parts(geom):
        c = np.round(shapely.get_coordinates(p), 5)
        if len(c) >= 2:
            out.append(c.tolist())
    return out


def main() -> None:
    zips = sorted(N13.glob("N13-24_*_SHP.zip"))
    kokudo, total = [], 0
    with ProcessPoolExecutor(max_workers=4) as ex:
        for mesh, n, k in ex.map(one_mesh, zips):
            total += n
            kokudo.append(k)
    print(f"N13 main-road segments {total:,} in {len(zips)} meshes")

    feats = []
    kk = pd.concat(kokudo, ignore_index=True).to_crs(6668)
    for geom in kk.geometry:
        coords = lines_coords(geom)
        if coords:
            feats.append({"type": "Feature", "properties": {"c": 1},
                          "geometry": {"type": "MultiLineString", "coordinates": coords}})
    ex = expressways()
    exv = ex.to_crs(LCC).dissolve(by="name", aggfunc={"cat": "min", "opened": "min"}).reset_index()
    exv["geometry"] = shapely.simplify(shapely.line_merge(exv.geometry.values), TOL)
    for r in exv.to_crs(6668).itertuples():
        coords = lines_coords(r.geometry)
        if coords:
            feats.append({"type": "Feature", "properties": {"c": 4, "n": r.name, "t": int(r.cat), "y": int(r.opened)},
                          "geometry": {"type": "MultiLineString", "coordinates": coords}})
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":")))
    print(f"expressway sections {len(ex):,} ({ex['name'].nunique()} routes); "
          f"{OUT.name}: {len(feats):,} features, {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
