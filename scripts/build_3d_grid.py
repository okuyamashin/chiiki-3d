"""Aggregate 町丁・字 population (2000-2020) onto a nationwide 1 km grid for the 3D viewer.

Each small area's pop_total is placed at its representative point (x_code / y_code of the
boundary data of the same year) and summed per grid cell (equal-area projection, 1 km).
Large rural 字 therefore put all their people in one cell - fine at national scale.

Output: output/3d/grid.json  {cell_m, years, lon[], lat[], pop{year: []}}
Run:    .venv/bin/python scripts/build_3d_grid.py [cell_m]
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
OUT = ROOT / "output" / "3d" / "grid.json"
CELL = float(sys.argv[1]) if len(sys.argv) > 1 else 1000.0
YEARS = [2000, 2005, 2010, 2015, 2020]
AEA = "+proj=aea +lat_1=30 +lat_2=42 +lat_0=36 +lon_0=136 +ellps=GRS80 +units=m +no_defs"
fwd = Transformer.from_crs("EPSG:6668", AEA, always_xy=True)
inv = Transformer.from_crs(AEA, "EPSG:6668", always_xy=True)


def points(year: int) -> pd.DataFrame:
    d = PROC / ("shochiiki" if year == 2020 else f"shochiiki_{year}")
    cols = ["key_code", "hcode", "x_code", "y_code"]
    b = pd.concat([pd.read_parquet(f, columns=cols) for f in sorted(d.glob("pref=*/data.parquet"))])
    b = b[b["hcode"] != 8154].groupby("key_code")[["x_code", "y_code"]].first()
    pop = pd.read_parquet(PROC / f"population_{year}.parquet", columns=["key_code", "pop_total"])
    pop = pop.groupby("key_code")["pop_total"].sum()
    df = b.join(pop, how="inner").dropna()
    df = df[df["pop_total"] > 0]
    total = pop.sum()
    print(f"{year}: {len(df)} areas, {df['pop_total'].sum():,.0f} / {total:,.0f} people placed")
    return df


def main() -> None:
    cells = {}
    for y in YEARS:
        df = points(y)
        x, yy = fwd.transform(df["x_code"].to_numpy(float), df["y_code"].to_numpy(float))
        ix, iy = np.floor(x / CELL).astype(np.int64), np.floor(yy / CELL).astype(np.int64)
        s = pd.Series(df["pop_total"].to_numpy(float)).groupby([ix, iy]).sum()
        cells[y] = s
    grid = pd.concat(cells, axis=1).fillna(0).astype(int)
    grid = grid[(grid > 0).any(axis=1)]
    ix = grid.index.get_level_values(0).to_numpy()
    iy = grid.index.get_level_values(1).to_numpy()
    lon, lat = inv.transform((ix + 0.5) * CELL, (iy + 0.5) * CELL)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "cell_m": CELL,
        "years": YEARS,
        "lon": np.round(lon, 4).tolist(),
        "lat": np.round(lat, 4).tolist(),
        "pop": {str(y): grid[y].tolist() for y in YEARS},
    }
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print(f"{len(grid)} cells, max {grid.max().max():,} -> {OUT} {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
