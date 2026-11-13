"""Nationwide 町丁・字 (2020 census small areas) blank map as a single SVG.

Input:  data/processed/shochiiki/pref=XX/data.parquet  (from build_geoparquet.py)
Output: output/japan_chome_blank.svg

- Water survey areas (hcode 8154) are dropped; only land small areas are drawn.
- Projected to a Japan-wide Lambert conformal conic, simplified per prefecture with
  shapely.coverage_simplify so neighbouring 町丁 keep a shared edge (no gaps/overlaps).
- One <path> per prefecture (id="pref-XX"); polygons are written with relative
  integer coordinates to keep the file small.

Run: .venv/bin/python scripts/build_chome_svg.py [tolerance_m]   (default 30)
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "processed" / "shochiiki"
OUT = ROOT / "output" / "japan_chome_blank.svg"

TOL = 30.0  # simplification tolerance, metres (override with argv[1] when run directly)
UNIT = 10.0  # metres per SVG user unit (integer coords -> 10 m grid)
LCC = "+proj=lcc +lat_1=30 +lat_2=42 +lat_0=36 +lon_0=136 +ellps=GRS80 +units=m +no_defs"


def ring_d(coords: np.ndarray) -> str:
    """Closed ring -> 'M x y l dx dy ... z' with integer relative deltas."""
    pts = np.round(coords[:-1] / UNIT).astype(np.int64)
    pts[:, 1] *= -1  # SVG y grows downward
    d = np.diff(pts, axis=0)
    d = d[(d != 0).any(axis=1)]  # drop zero-length steps after rounding
    if len(d) < 2:
        return ""
    body = " ".join(f"{dx} {dy}" for dx, dy in d)
    return f"M{pts[0, 0]} {pts[0, 1]}l{body}z"


def geom_d(geom) -> str:
    parts = []
    for poly in getattr(geom, "geoms", [geom]):
        if poly.is_empty or poly.geom_type != "Polygon":
            continue
        for ring in [poly.exterior, *poly.interiors]:
            s = ring_d(np.asarray(ring.coords))
            if s:
                parts.append(s)
    return "".join(parts)


def main() -> None:
    prefs = []
    bounds = np.array([np.inf, np.inf, -np.inf, -np.inf])
    n_total = 0
    for i in range(1, 48):
        pref = f"{i:02d}"
        g = gpd.read_parquet(SRC / f"pref={pref}" / "data.parquet", columns=["hcode", "geometry"])
        g = g[g["hcode"] != 8154].to_crs(LCC)
        geoms = shapely.make_valid(g.geometry.values)
        geoms = shapely.coverage_simplify(geoms, TOL)
        d = "".join(geom_d(x) for x in geoms)
        prefs.append((pref, d))
        b = shapely.total_bounds(geoms)
        bounds = np.minimum(bounds, [b[0], b[1], np.inf, np.inf])
        bounds = np.maximum(bounds, [-np.inf, -np.inf, b[2], b[3]])
        n_total += len(g)
        print(f"{pref}: {len(g):6d} areas, {len(d) / 1e6:6.2f} MB", flush=True)

    minx, miny, maxx, maxy = bounds / UNIT
    pad = 200
    x0, y0 = int(minx) - pad, int(-maxy) - pad
    w, h = int(maxx - minx) + 2 * pad, int(maxy - miny) + 2 * pad

    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w") as f:
        f.write(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} {y0} {w} {h}" '
            f'width="{w // 50}" height="{h // 50}">\n'
            f"<!-- 2020年国勢調査 小地域（町丁・字）境界, e-Stat. {n_total} areas, "
            f"simplified {TOL:g} m, 1 unit = {UNIT:g} m, LCC -->\n"
            '<g fill="#fff" stroke="#555" stroke-width="0.6" stroke-linejoin="round" '
            'vector-effect="non-scaling-stroke">\n'
        )
        for pref, d in prefs:
            f.write(f'<path id="pref-{pref}" vector-effect="non-scaling-stroke" d="{d}"/>\n')
        f.write("</g>\n</svg>\n")
    print(f"{OUT}  {OUT.stat().st_size / 1e6:.1f} MB, {n_total} areas")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        TOL = float(sys.argv[1])
    main()
