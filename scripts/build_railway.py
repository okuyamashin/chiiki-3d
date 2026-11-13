"""Railway lines and stations (国土数値情報 N02-25) with station ridership (S12-25, 2011-2024).

Input:  data/raw/ksj_n02/extracted/N02-25_GML/UTF-8/N02-25_{RailroadSection,Station}.shp
        data/raw/ksj_s12/extracted/S12-25_GML/UTF-8/S12-25_NumberOfPassengers.shp
Output: data/processed/railway/sections.parquet  one row per N02 section (LineString)
        data/processed/railway/stations.parquet  one row per station-on-a-line, point at the
            middle of the N02 platform line, ridership columns pax_2011 .. pax_2024
        output/3d/railway.geojson   lines merged per (operator, line), simplified, for the viewer
        output/3d/stations.geojson  one point per station group (乗換駅 = one point)
N02 may split one station into several rows (platform segments) with the same station_code;
stations.parquet keeps them all, so dedupe on station_code before summing ridership.

Ridership (乗降客数, people/day) is kept only where S12 重複コード = 1 (not counted under
another row) and データ有無コード = 1 (data present); otherwise NA. A station group's total
sums its rows, so a transfer station shows all operators together.

Codes  kind  (N02_001 鉄道区分): 11 JR普通鉄道, 12 普通鉄道, 13 鋼索, 14-17 モノレール等, 21-25 軌道
       owner (N02_002 事業者種別): 1 新幹線, 2 JR在来線, 3 公営, 4 民営, 5 第三セクター

Run: .venv/bin/python scripts/build_railway.py [tolerance_m]   (default 20)
"""

import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

ROOT = Path(__file__).resolve().parent.parent
N02 = ROOT / "data" / "raw" / "ksj_n02" / "extracted" / "N02-25_GML" / "UTF-8"
S12 = ROOT / "data" / "raw" / "ksj_s12" / "extracted" / "S12-25_GML" / "UTF-8"
PROC = ROOT / "data" / "processed" / "railway"
OUT = ROOT / "output" / "3d"
TOL = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
LCC = "+proj=lcc +lat_1=30 +lat_2=42 +lat_0=36 +lon_0=136 +ellps=GRS80 +units=m +no_defs"
YEARS = list(range(2011, 2025))  # S12-25: 4 columns per year starting at S12_006


def read(path: Path) -> gpd.GeoDataFrame:
    return gpd.read_file(path, encoding="utf-8")


def sections() -> gpd.GeoDataFrame:
    g = read(N02 / "N02-25_RailroadSection.shp")
    g = g.rename(columns={"N02_001": "kind", "N02_002": "owner", "N02_003": "line", "N02_004": "operator"})
    g["kind"] = g["kind"].astype(int)
    g["owner"] = g["owner"].astype(int)
    return g[["kind", "owner", "line", "operator", "geometry"]]


def ridership() -> pd.DataFrame:
    s = read(S12 / "S12-25_NumberOfPassengers.shp").drop(columns="geometry")
    out = pd.DataFrame({"station_code": s["S12_001c"]})
    for i, y in enumerate(YEARS):
        dup, avail, _note, pax = (f"S12_{6 + 4 * i + k:03d}" for k in range(4))
        v = pd.to_numeric(s[pax], errors="coerce")
        ok = (pd.to_numeric(s[dup]) == 1) & (pd.to_numeric(s[avail]) == 1)
        out[f"pax_{y}"] = v.where(ok).astype("Int64")
    # one S12 row per station_code is expected; keep the max just in case
    return out.groupby("station_code", as_index=False).max()


def stations() -> gpd.GeoDataFrame:
    g = read(N02 / "N02-25_Station.shp")
    g = g.rename(columns={"N02_001": "kind", "N02_002": "owner", "N02_003": "line", "N02_004": "operator",
                          "N02_005": "name", "N02_005c": "station_code", "N02_005g": "group_code"})
    g["kind"] = g["kind"].astype(int)
    g["owner"] = g["owner"].astype(int)
    g["geometry"] = shapely.line_interpolate_point(g.geometry.values, 0.5, normalized=True)
    g = g.merge(ridership(), on="station_code", how="left")
    return g


def viewer_lines(sec: gpd.GeoDataFrame) -> dict:
    m = sec.to_crs(LCC).dissolve(by=["operator", "line"], aggfunc={"kind": "first", "owner": "min"}).reset_index()
    m["geometry"] = shapely.line_merge(m.geometry.values)
    m["geometry"] = m.geometry.simplify(TOL)
    m = m.to_crs(6668)
    feats = []
    for r in m.itertuples():
        geom = shapely.get_parts(r.geometry)
        coords = [np.round(shapely.get_coordinates(p), 5).tolist() for p in geom if not p.is_empty]
        feats.append({"type": "Feature", "properties": {"o": r.operator, "l": r.line, "k": int(r.kind), "w": int(r.owner)},
                      "geometry": {"type": "MultiLineString", "coordinates": coords}})
    return {"type": "FeatureCollection", "features": feats}


def viewer_stations(st: gpd.GeoDataFrame) -> dict:
    last, first = f"pax_{YEARS[-1]}", "pax_2019"
    feats = []
    for code, grp in st.groupby("group_code"):
        pt = shapely.centroid(shapely.multipoints(shapely.get_coordinates(grp.geometry.values)))
        # N02 splits one station into several platform segments sharing a station_code
        u = grp.drop_duplicates("station_code")
        p24 = u[last].sum(min_count=1)
        p19 = u[first].sum(min_count=1)
        lines = sorted({f"{o} {l}" for o, l in zip(grp["operator"], grp["line"])})
        feats.append({"type": "Feature", "properties": {
            "n": grp["name"].iloc[0], "ls": lines,
            "p": None if pd.isna(p24) else int(p24), "p19": None if pd.isna(p19) else int(p19),
            "w": int(grp["owner"].min())},
            "geometry": {"type": "Point", "coordinates": [round(pt.x, 5), round(pt.y, 5)]}})
    return {"type": "FeatureCollection", "features": feats}


def main() -> None:
    PROC.mkdir(parents=True, exist_ok=True)
    sec = sections()
    st = stations()
    sec.to_parquet(PROC / "sections.parquet")
    st.to_parquet(PROC / "stations.parquet")
    print(f"sections {len(sec):,}  stations {len(st):,}  "
          f"with {YEARS[-1]} ridership {st[f'pax_{YEARS[-1]}'].notna().sum():,}")
    for name, fc in [("railway.geojson", viewer_lines(sec)), ("stations.geojson", viewer_stations(st))]:
        (OUT / name).write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")))
        print(f"{name}: {len(fc['features']):,} features, {(OUT / name).stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
