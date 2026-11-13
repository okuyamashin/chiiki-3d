"""Nationwide 町丁・字 choropleth from the 2020 census, log-scale colour, as one SVG.

Input:  data/processed/shochiiki/pref=XX/data.parquet, data/processed/population_2020.parquet
Output: output/japan_chome_pop2020.svg      (mode "pop":     people per area)
        output/japan_chome_density2020.svg  (mode "density": people per km² of land)

Same geometry pipeline as build_chome_svg.py (LCC, coverage_simplify, relative integer
paths). Population is joined by key_code (pop_total) - not the boundary's JINKO, which is
0 on the extra polygons of a split area. Density divides by the land area of all polygons
sharing a key_code (water survey areas, hcode 8154, excluded), measured in an equal-area
projection before simplification. Colour: one-hue blue ramp in log classes;
0 people = neutral gray, no data / secret = darker gray.

Run: .venv/bin/python scripts/build_chome_pop_svg.py [pop|density] [tolerance_m]
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from build_chome_svg import LCC, UNIT, geom_d

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
MODE = sys.argv[1] if len(sys.argv) > 1 else "pop"
TOL = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
AEA = "+proj=aea +lat_1=30 +lat_2=42 +lat_0=36 +lon_0=136 +ellps=GRS80 +units=m +no_defs"

# Blue ramp steps 100..700 (light -> dark).
BLUES = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
         "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
ZERO, NODATA = "#f0efec", "#c9c8c4"

if MODE == "pop":
    OUT = ROOT / "output" / "japan_chome_pop2020.svg"
    TITLE = "人口（2020年国勢調査・町丁字別、対数）"
    UNIT_LABEL = "人"
    EDGES = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000]  # class lower bounds
    RAMP = BLUES
elif MODE == "density":
    OUT = ROOT / "output" / "japan_chome_density2020.svg"
    TITLE = "人口密度（2020年国勢調査・町丁字別、人/km²、対数）"
    UNIT_LABEL = ""
    EDGES = [0, 1, 3, 10, 30, 100, 300, 1000, 3000, 10000, 30000]  # first class: >0 to <1
    RAMP = [BLUES[i] for i in (0, 1, 2, 4, 5, 6, 7, 8, 10, 11, 12)]
else:
    sys.exit(f"unknown mode {MODE!r} (pop|density)")
FILLS = [NODATA, ZERO] + RAMP  # index 0 -> NODATA, 1 -> ZERO (0 people), 2+k -> RAMP[k]


def classify(value: np.ndarray, pop: np.ndarray) -> np.ndarray:
    cls = np.searchsorted(EDGES, value, side="right") - 1
    cls = np.where(pop == 0, -1, cls)
    cls = np.where(np.isnan(pop), -2, cls)
    return cls + 2


def class_label(k: int) -> str:
    lo = EDGES[k]
    if k + 1 == len(EDGES):
        return f"{lo:,}{UNIT_LABEL}以上"
    hi = EDGES[k + 1]
    if MODE == "density":
        return f"1未満" if lo == 0 else f"{lo:,}–{hi:,}未満"
    return f"{lo:,}{UNIT_LABEL}" if hi - 1 == lo else f"{lo:,}–{hi - 1:,}{UNIT_LABEL}"


def legend(x: int, y: int) -> str:
    s = 2600  # swatch size in user units (26 km)
    fs = 2400
    out = [f'<g id="legend" font-family="Hiragino Sans, sans-serif" font-size="{fs}" fill="#333">',
           f'<text x="{x}" y="{y - 1800}" font-size="{fs * 1.25:.0f}" font-weight="600">{TITLE}</text>']
    rows = [(NODATA, "データなし・秘匿"), (ZERO, "人口0")]
    rows += [(c, class_label(k)) for k, c in enumerate(RAMP)]
    for i, (c, label) in enumerate(rows):
        yy = y + i * (s + 500)
        out.append(f'<rect x="{x}" y="{yy}" width="{s * 2}" height="{s}" rx="400" fill="{c}"/>')
        out.append(f'<text x="{x + s * 2 + 1200}" y="{yy + s * 0.8:.0f}">{label}</text>')
    out.append("</g>")
    return "\n".join(out)


def main() -> None:
    pop = pd.read_parquet(PROC / "population_2020.parquet", columns=["key_code", "pop_total"])
    pop = pop.set_index("key_code")["pop_total"].astype("float64")

    bounds = np.array([np.inf, np.inf, -np.inf, -np.inf])
    groups, counts, n_total = [], np.zeros(len(FILLS), int), 0
    for i in range(1, 48):
        pref = f"{i:02d}"
        g = gpd.read_parquet(PROC / "shochiiki" / f"pref={pref}" / "data.parquet",
                             columns=["key_code", "hcode", "geometry"])
        g = g[g["hcode"] != 8154]
        p = g["key_code"].map(pop).to_numpy(dtype="float64")
        if MODE == "density":
            km2 = g.to_crs(AEA).geometry.area.groupby(g["key_code"]).transform("sum") / 1e6
            value = p / km2.to_numpy()
        else:
            value = p
        cls = classify(value, p)
        g = g.to_crs(LCC)
        geoms = shapely.coverage_simplify(shapely.make_valid(g.geometry.values), TOL)
        paths = []
        for c in np.unique(cls):
            d = "".join(geom_d(x) for x in geoms[cls == c])
            if d:
                paths.append(f'<path fill="{FILLS[c]}" d="{d}"/>')
        groups.append(f'<g id="pref-{pref}">\n' + "\n".join(paths) + "\n</g>")
        # count areas by key_code, not polygons
        k = pd.Series(cls).groupby(g["key_code"].to_numpy()).first()
        counts += np.bincount(k, minlength=len(FILLS))
        b = shapely.total_bounds(geoms)
        bounds[:2] = np.minimum(bounds[:2], b[:2])
        bounds[2:] = np.maximum(bounds[2:], b[2:])
        n_total += len(g)
        print(f"{pref}: {len(g):6d} polygons", flush=True)

    minx, miny, maxx, maxy = bounds / UNIT
    pad = 200
    x0, y0 = int(minx) - pad, int(-maxy) - pad
    w, h = int(maxx - minx) + 2 * pad, int(maxy - miny) + 2 * pad

    with open(OUT, "w") as f:
        f.write(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} {y0} {w} {h}" '
            f'width="{w // 50}" height="{h // 50}">\n'
            f"<!-- {TITLE}, e-Stat. {n_total} polygons, "
            f"simplified {TOL:g} m, 1 unit = {UNIT:g} m, LCC -->\n"
            f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="#fff"/>\n'
            '<g stroke="#fff" stroke-width="0.3" stroke-linejoin="round" '
            'style="vector-effect:non-scaling-stroke">\n'
        )
        f.write("\n".join(groups))
        f.write("\n</g>\n")
        f.write(legend(x0 + int(w * 0.62), y0 + int(h * 0.60)))
        f.write("\n</svg>\n")
    labels = ["nodata", "pop 0"] + [class_label(k) for k in range(len(RAMP))]
    for lab, n in zip(labels, counts):
        print(f"  {lab:>16}: {n:6d} areas")
    print(f"{OUT}  {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
