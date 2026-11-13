"""Plain 3D terrain of one municipality + every municipality touching it (no statistics on it).

Terrain (clipped to the union of the municipalities):
  default  国土地理院 標高タイル dem_png z14 (DEM10B, ~10 m), bilinear-sampled to a RES_M grid,
           written as Uint16 decimeters (65535 = no data) to terrain_<code>.bin
  --mesh3  国土数値情報 G04-a 3rd-mesh mean elevation (~1 km), bicubic to ~230 m, inline in JSON
Lines:   municipality outlines (2020 N03) for all; small areas (町丁・字, 2020) inside the target.
Overlays (clipped to the same area, densified so they can be draped on the terrain):
  roads   国土数値情報 N13-24 (raw zips, all categories, 通常部 only; tunnels flagged)
  rail    国土数値情報 N02-25 sections (data/processed/railway)
  rivers  国土数値情報 W05 streams (data/processed/rivers), lakes W09 (data/processed/lakes.parquet)

Output: output/3d/terrain_<city_code>.json
Run:    .venv/bin/python scripts/build_3d_terrain.py [pref_code city_name] [--mesh3] [--res 30]
        (default: 01 歌志内市; GSI tiles are fetched by scripts/fetch_gsi_dem.py as needed)
"""

import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from scipy.interpolate import RectBivariateSpline

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_gsi_dem import fetch  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
MESH3 = "--mesh3" in sys.argv
RES_M = float(sys.argv[sys.argv.index("--res") + 1]) if "--res" in sys.argv else 30.0
if "--res" in sys.argv:
    args.remove(sys.argv[sys.argv.index("--res") + 1])
PREF, CITY = (args[0], args[1]) if len(args) > 1 else ("01", "歌志内市")
SUB = 4  # mesh3 mode: grid nodes per mesh3 cell side

muni = gpd.read_parquet(PROC / f"municipality/pref={PREF}/data.parquet").dissolve("city_code", aggfunc="first")
target = muni[muni.city_name == CITY]
code = target.index[0]
near = muni[muni.intersects(target.union_all().buffer(0.001))].copy()
area = near.union_all()
minx, miny, maxx, maxy = area.bounds

def terrain_mesh3():
    # mesh3 elevation as a regular lon/lat array (cell centers), with a margin for the spline
    elev = pd.read_parquet(PROC / "elevation_mesh3.parquet", columns=["lon", "lat", "elev_mean"])
    pad = 3
    i0, i1 = int(np.floor(miny * 120)) - pad, int(np.ceil(maxy * 120)) + pad
    j0, j1 = int(np.floor((minx - 100) * 80)) - pad, int(np.ceil((maxx - 100) * 80)) + pad
    elev = elev[elev.lat.between(i0 / 120, i1 / 120) & elev.lon.between(100 + j0 / 80, 100 + j1 / 80)]
    ii = np.floor(elev.lat.values * 120).astype(int) - i0
    jj = np.floor((elev.lon.values - 100) * 80).astype(int) - j0
    z = np.full((i1 - i0, j1 - j0), np.nan)
    z[ii, jj] = elev.elev_mean.values
    z = pd.DataFrame(z).interpolate(axis=1, limit_direction="both").interpolate(axis=0, limit_direction="both").values
    lat_c = (np.arange(i0, i1) + 0.5) / 120
    lon_c = 100 + (np.arange(j0, j1) + 0.5) / 80
    spline = RectBivariateSpline(lat_c, lon_c, z, kx=3, ky=3)

    dlat, dlon = 1 / 120 / SUB, 1 / 80 / SUB
    lats = np.arange(np.floor(miny / dlat), np.ceil(maxy / dlat) + 1) * dlat
    lons = np.arange(np.floor(minx / dlon), np.ceil(maxx / dlon) + 1) * dlon
    grid = spline(lats, lons)
    return lons, lats, grid


def terrain_gsi(z=14):
    d, (x0, y0, x1, y1) = fetch(minx, miny, maxx, maxy, z)
    mos = np.full(((y1 - y0 + 1) * 256, (x1 - x0 + 1) * 256), np.nan, dtype=np.float32)
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            f = d / f"{x}_{y}.png"
            if not f.exists():
                continue
            a = np.asarray(Image.open(f).convert("RGB")).astype(np.int64)
            v = a[..., 0] * 65536 + a[..., 1] * 256 + a[..., 2]
            h = np.where(v < 2 ** 23, v, v - 2 ** 24) * 0.01
            h[v == 2 ** 23] = np.nan
            mos[(y - y0) * 256:(y - y0 + 1) * 256, (x - x0) * 256:(x - x0 + 1) * 256] = h
    dlat = RES_M / 110574
    dlon = RES_M / (111320 * np.cos(np.radians((miny + maxy) / 2)))
    lats = np.arange(np.floor(miny / dlat), np.ceil(maxy / dlat) + 1) * dlat
    lons = np.arange(np.floor(minx / dlon), np.ceil(maxx / dlon) + 1) * dlon
    n = 2 ** z * 256  # global pixel coords of each grid node (pixel centers at +0.5)
    px = (lons + 180) / 360 * n - x0 * 256 - 0.5
    py = (1 - np.arcsinh(np.tan(np.radians(lats))) / np.pi) / 2 * n - y0 * 256 - 0.5
    PX, PY = np.meshgrid(px, py)
    ix, iy = np.floor(PX).astype(int), np.floor(PY).astype(int)
    tx, ty = PX - ix, PY - iy
    ix, iy = ix.clip(0, mos.shape[1] - 2), iy.clip(0, mos.shape[0] - 2)
    grid = (mos[iy, ix] * (1 - tx) * (1 - ty) + mos[iy, ix + 1] * tx * (1 - ty)
            + mos[iy + 1, ix] * (1 - tx) * ty + mos[iy + 1, ix + 1] * tx * ty)
    return lons, lats, grid


lons, lats, grid = terrain_mesh3() if MESH3 else terrain_gsi()
dlon, dlat = lons[1] - lons[0], lats[1] - lats[0]
gx, gy = np.meshgrid(lons, lats)
inside = shapely.contains_xy(area.buffer(dlat * 0.7), gx, gy)
grid = np.where(inside, np.round(grid, 1), np.nan)
tmask = shapely.contains_xy(target.union_all(), gx, gy)  # nodes inside the target municipality
dst = ROOT / "output" / "3d" / f"terrain_{code}.json"
meta = {"lon0": lons[0], "lat0": lats[0], "dlon": dlon, "dlat": dlat, "nx": len(lons), "ny": len(lats)}
if MESH3:
    meta["z"] = [None if np.isnan(v) else float(v) for v in grid.ravel()]
    meta["mask"] = tmask.ravel().astype(int).tolist()
    meta["source"] = "国土数値情報 標高・傾斜度3次メッシュ（約1km, 2011）を約230m格子に補間"
else:
    zb = np.where(np.isnan(grid), 65535, np.clip(np.round(grid * 10), 0, 65534)).astype("<u2")
    dst.with_suffix(".bin").write_bytes(zb.tobytes())
    meta["bin"] = dst.with_suffix(".bin").name
    dst.with_suffix(".mask.bin").write_bytes(tmask.astype("u1").tobytes())  # 1 = target municipality
    meta["mask_bin"] = dst.with_suffix(".mask.bin").name
    meta["source"] = f"国土地理院 標高タイル（基盤地図情報 数値標高モデル 10m）を約{RES_M:.0f}m格子に"


def lines(geom, tol=0.0002, step=0.0003):
    geom = shapely.segmentize(geom.simplify(tol), step)  # densify so lines follow the terrain
    rings = []
    for poly in getattr(geom, "geoms", [geom]):
        for ring in [poly.exterior, *poly.interiors]:
            rings.append(np.round(np.asarray(ring.coords), 6).tolist())
    return rings


def flat(geom, tol=0.00005, step=0.0003):
    """(Multi)LineString -> list of [lon, lat] paths, simplified (~5 m) and densified (~30 m)."""
    geom = shapely.segmentize(shapely.simplify(geom, tol), step)
    return [np.round(np.asarray(g.coords), 5).tolist() for g in getattr(geom, "geoms", [geom]) if not g.is_empty]


def merged(gdf, keys):
    """Clip to the area, merge segments per key so paths are long, flatten to paths."""
    gdf = gdf[gdf.intersects(area)]
    out = []
    for k, g in gdf.groupby(keys, dropna=False):
        geom = shapely.line_merge(shapely.intersection(shapely.union_all(g.geometry.values), area))
        geom = shapely.union_all([x for x in getattr(geom, "geoms", [geom]) if x.geom_type.endswith("LineString")])
        for path in flat(geom):
            out.append({**dict(zip(keys, k if isinstance(k, tuple) else (k,))), "p": path})
    return out


def overlays():
    bbox = (minx, miny, maxx, maxy)
    m1 = {f"{int(lat * 1.5)}{int(lon - 100)}" for lat in np.arange(miny, maxy + 0.5, 0.5) for lon in np.arange(minx, maxx + 0.5, 0.5)
          if lat <= maxy + 0.67 and lon <= maxx + 1}
    roads = []
    for m in sorted(m1):
        zp = ROOT / "data" / "raw" / "ksj_n13" / "zip" / f"N13-24_{m}_SHP.zip"
        if zp.exists():
            g = gpd.read_file(f"/vsizip/{zp}/{zp.stem}/{zp.stem.removesuffix('_SHP')}.shp", bbox=bbox,
                              where="N13_002 = '1'")
            roads.append(gpd.GeoDataFrame({"c": g.N13_003.astype(int), "t": (g.N13_004 == "3").astype(int),
                                           "w": g.N13_006.astype(int)}, geometry=g.geometry).to_crs(6668))
    roads = pd.concat(roads)
    roads["c"] = roads.c.replace({5: 3, 6: 3})  # その他・不明 -> 市町村道等
    roads.loc[(roads.c == 3) & (roads.w <= 1), "c"] = 7  # 幅3m未満の細道
    rail = gpd.read_parquet(PROC / "railway" / "sections.parquet").cx[minx:maxx, miny:maxy]
    rail = rail.assign(l=rail.operator + " " + rail.line)
    rivers = gpd.read_parquet(PROC / f"rivers/pref={PREF}/data.parquet").cx[minx:maxx, miny:maxy]
    rivers = rivers.assign(s=rivers.section.astype(int), n=rivers.name.fillna(""))
    lakes = gpd.read_parquet(PROC / "lakes.parquet").cx[minx:maxx, miny:maxy]
    lakes = lakes[lakes.intersects(area)]
    return {
        "roads": merged(roads, ["c", "t"]),
        "rail": merged(rail, ["l"]),
        "rivers": merged(rivers, ["s", "n"]),
        "lakes": [{"n": r["name"], "rings": lines(shapely.intersection(r.geometry, area), 0.00005, 0.0003)}
                  for _, r in lakes.iterrows()],
    }


small = gpd.read_parquet(PROC / f"shochiiki/pref={PREF}/data.parquet")
small = small[(small.city_code == code) & (small.hcode == 8101)].dissolve("key_code", aggfunc="first")
YEARS = [2000, 2005, 2010, 2015, 2020]  # census years with small-area population; key_code is stable here
BANDS = [f"{a}～{a + 4}歳" for a in range(0, 75, 5)] + ["75歳以上"]  # 5-year bands, 75+ as one (2020 has no finer split)
Z2F = str.maketrans("0123456789", "０１２３４５６７８９")
SEXCOLS = {s: [f"{s}{b.translate(Z2F)}" for b in BANDS] for s in ("男", "女")}
popdf = {y: pd.read_parquet(PROC / f"population_{y}.parquet").set_index("key_code") for y in YEARS}
pops = {y: d.pop_total for y, d in popdf.items()}
pop = pops[2020]


IND = pd.read_parquet(PROC / "industry.parquet") if (PROC / "industry.parquet").exists() else None
IND_COLS = ["employed", "prim", "cons", "manu", "trade", "trans", "med", "svc", "gov", "employee", "self", "family"]


def industry(k):
    """{year: {group: n}} employed persons by harmonised industry group (see build_industry.py)."""
    if IND is None:
        return {}
    r = IND[IND.key_code == k].set_index("year")[IND_COLS]
    return {int(y): {c: None if pd.isna(v) else int(v) for c, v in row.items()} for y, row in r.iterrows()}


def pop15(k):
    """{year: population aged 15+} = total minus 0-14."""
    return {y: None if k not in d.index or pd.isna(d.loc[k, "総数１５歳未満"]) else int(d.loc[k, "pop_total"] - d.loc[k, "総数１５歳未満"])
            for y, d in popdf.items()}


def ages(k):
    """{year: {"m": [16 bands], "f": [...]}} for one small area; None where a value is missing or suppressed."""
    out = {}
    for y, d in popdf.items():
        if k not in d.index:
            continue
        r = pd.to_numeric(d.loc[k, SEXCOLS["男"] + SEXCOLS["女"]], errors="coerce")
        out[y] = {sx: [None if pd.isna(r[c]) else int(r[c]) for c in SEXCOLS[s]] for sx, s in (("m", "男"), ("f", "女"))}
    return out
if not MESH3:  # node -> small area (1-based index into "small", 0 = none), for colouring the target by small area
    aza = np.zeros(gx.shape, "u1")
    for i, geom in enumerate(small.geometry, 1):
        aza[shapely.contains_xy(geom, gx, gy)] = i
    dst.with_suffix(".aza.bin").write_bytes(aza.tobytes())
    meta["aza_bin"] = dst.with_suffix(".aza.bin").name
out = {
    "name": CITY,
    "origin": [round((minx + maxx) / 2, 6), round((miny + maxy) / 2, 6)],
    "grid": meta,
    "munis": [{"name": r.city_name, "target": c == code, "rings": lines(r.geometry),
               "label": list(shapely.Point(r.geometry.representative_point()).coords[0])}
              for c, r in near.iterrows()],
    **overlays(),
    "city": {
        "ind": industry(code),
        "pop15": {y: int(sum(v for v in (pop15(k)[y] for k in small.index) if v is not None)) for y in YEARS},
        "longrun": (lambda lr: [[int(r.year), int(r["pop"])] for _, r in lr[lr.city_code == code].iterrows()])(
            pd.read_csv(ROOT / "data" / "raw" / "manual" / "longrun_population.csv", dtype={"city_code": str}))
        if (ROOT / "data" / "raw" / "manual" / "longrun_population.csv").exists() else [],
    },
    "small": [{"name": r.s_name, "pop": None if pd.isna(pop.get(k)) else int(pop.get(k)),
               "pops": {y: None if pd.isna(pops[y].get(k)) else int(pops[y].get(k)) for y in YEARS},
               "ages": ages(k), "ind": industry(k), "pop15": pop15(k), "rings": lines(r.geometry, 0.0001, 0.0003),
               "label": list(r.geometry.representative_point().coords[0])} for k, r in small.iterrows()],
}
dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
zz = grid[~np.isnan(grid)]
print(f"{CITY}: neighbors {[n for n in near.city_name if n != CITY]}, grid {len(lons)}x{len(lats)}, "
      f"{inside.sum():,} nodes, elev {zz.min():.0f}-{zz.max():.0f} m, {len(small)} small areas, "
      f"{len(out['roads'])} road / {len(out['rail'])} rail / {len(out['rivers'])} river paths, "
      f"{len(out['lakes'])} lakes, json {dst.stat().st_size/1e6:.1f} MB "
      f"-> {dst.relative_to(ROOT)} ({'mesh3' if MESH3 else f'GSI {RES_M:.0f} m'})")
