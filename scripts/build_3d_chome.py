"""Per-prefecture 町丁・字 polygons (2020) with population attributes for the 3D polygon viewer.

Input:  data/processed/shochiiki/pref=XX/data.parquet, data/processed/population_{2015,2020}.parquet
Output: output/3d/chome/XX.geojson, one Feature per polygon, properties
          n  city + 町丁字 name
          p  population 2020 (pop_total, joined by key_code; null = no data / secret)
          d  people per km² of land (all polygons sharing key_code, water areas hcode 8154 excluded)
          a  share aged 65+ in % (null when pop is 0 / unknown)
          c  change 2015->2020 in % (null when key_code is absent in 2015 or 2015 pop is 0)
Geometry: coverage_simplify in LCC (shared edges kept), lon/lat with 5 decimals (~1 m).

Run: .venv/bin/python scripts/build_3d_chome.py [tolerance_m]
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
OUT = ROOT / "output" / "3d" / "chome"
TOL = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
LCC = "+proj=lcc +lat_1=30 +lat_2=42 +lat_0=36 +lon_0=136 +ellps=GRS80 +units=m +no_defs"
AEA = "+proj=aea +lat_1=30 +lat_2=42 +lat_0=36 +lon_0=136 +ellps=GRS80 +units=m +no_defs"


def main() -> None:
    cols = ["key_code", "city_name", "s_name", "pop_total", "総数６５歳以上"]
    p20 = pd.read_parquet(PROC / "population_2020.parquet", columns=cols).groupby("key_code").agg(
        city=("city_name", "first"), name=("s_name", "first"),
        pop=("pop_total", lambda s: s.sum(min_count=1)), old=("総数６５歳以上", lambda s: s.sum(min_count=1)))
    p15 = pd.read_parquet(PROC / "population_2015.parquet", columns=["key_code", "pop_total"])
    p15 = p15.groupby("key_code")["pop_total"].sum(min_count=1).astype("float64")
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for i in range(1, 48):
        pref = f"{i:02d}"
        g = gpd.read_parquet(PROC / "shochiiki" / f"pref={pref}" / "data.parquet",
                             columns=["key_code", "city_name", "s_name", "hcode", "geometry"])
        g = g[g["hcode"] != 8154].reset_index(drop=True)
        a = p20.reindex(g["key_code"])
        pop = a["pop"].astype("float64").to_numpy()
        km2 = g.to_crs(AEA).geometry.area.groupby(g["key_code"]).transform("sum").to_numpy() / 1e6
        old = a["old"].astype("float64").to_numpy()
        prev = p15.reindex(g["key_code"]).to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            dens = np.where(km2 > 0, pop / km2, np.nan)
            aged = np.where(pop > 0, old / pop * 100, np.nan)
            chg = np.where(prev > 0, (pop - prev) / prev * 100, np.nan)
        geoms = shapely.coverage_simplify(shapely.make_valid(g.to_crs(LCC).geometry.values), TOL)
        city = a["city"].reset_index(drop=True).fillna(g["city_name"])
        name = (city + " " + a["name"].reset_index(drop=True).fillna(g["s_name"])).to_numpy()
        out = gpd.GeoDataFrame({
            "n": name,
            "p": pd.array(pop).round(0).astype("Int64"),
            "d": np.round(dens, 0), "a": np.round(aged, 1), "c": np.round(chg, 1),
        }, geometry=gpd.GeoSeries(geoms, crs=LCC)).to_crs("EPSG:4326")
        out = out[~out.geometry.is_empty & out.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
        dst = OUT / f"{pref}.geojson"
        out.to_file(dst, driver="GeoJSON", COORDINATE_PRECISION=5, engine="pyogrio")
        total += dst.stat().st_size
        print(f"{pref}: {len(out):6d} polygons {dst.stat().st_size / 1e6:5.1f} MB", flush=True)
    print(f"total {total / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
