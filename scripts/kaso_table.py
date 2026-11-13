"""Famous depopulated municipalities: own numbers vs. their surroundings (radius), 2000 -> 2020.

Each small area (町丁・字) is a point at its representative x_code/y_code of the same year.
Municipality membership uses the 2020 municipality polygons for every year, so mergers
don't break the comparison. Center = 2020 population-weighted centroid of the municipality.

Output: output/analysis/kaso_table.csv
Run:    .venv/bin/python scripts/kaso_table.py
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
OUT = ROOT / "output" / "analysis" / "kaso_table.csv"
YEARS = [2000, 2020]
RADII = [20, 50]  # km

# (pref, city_name in 2020, why it is known)
PLACES = [
    ("北海道", "夕張市", "財政破綻(2007)"),
    ("北海道", "歌志内市", "人口最少の市"),
    ("秋田県", "上小阿仁村", "秋田の山間村"),
    ("群馬県", "南牧村", "高齢化率日本一"),
    ("東京都", "檜原村", "都内唯一の島外の村"),
    ("東京都", "青ヶ島村", "人口最少の村"),
    ("山梨県", "丹波山村", "多摩川最上流"),
    ("長野県", "天龍村", "長野の高齢化最先端"),
    ("奈良県", "野迫川村", "紀伊山地の最小村"),
    ("奈良県", "川上村", "人口減少率上位"),
    ("島根県", "海士町", "離島の移住成功例"),
    ("徳島県", "上勝町", "葉っぱビジネス"),
    ("徳島県", "神山町", "サテライトオフィス"),
    ("高知県", "大川村", "離島除き人口最少"),
]


def points(year: int) -> gpd.GeoDataFrame:
    d = PROC / ("shochiiki" if year == 2020 else f"shochiiki_{year}")
    b = pd.concat([pd.read_parquet(f, columns=["key_code", "hcode", "area", "x_code", "y_code"])
                   for f in sorted(d.glob("pref=*/data.parquet"))])
    # A key_code can have several pieces (islets): use the largest piece's point.
    b = b[b["hcode"] != 8154].sort_values("area", ascending=False)
    b = b.groupby("key_code")[["x_code", "y_code"]].first()
    p = pd.read_parquet(PROC / f"population_{year}.parquet",
                        columns=["key_code", "pop_total", "総数６５歳以上", "総数１５歳未満"])
    p = p.groupby("key_code").sum(min_count=1)
    df = b.join(p, how="inner")
    df = df[df["pop_total"] > 0].rename(columns={"総数６５歳以上": "p65", "総数１５歳未満": "p14"})
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.x_code, df.y_code), crs=6668)


def mesh3_code(lon, lat):
    """JIS X 0410 3rd mesh code (~1 km) of each point."""
    lat_m, lon_m = np.floor(lat * 120).astype(int), np.floor((lon - 100) * 80).astype(int)
    return ((lat_m // 80) * 1000000 + (lon_m // 80) * 10000 + (lat_m % 80 // 10) * 1000
            + (lon_m % 80 // 10) * 100 + (lat_m % 10) * 10 + lon_m % 10)


def haversine(lon, lat, lon0, lat0):
    lon, lat, lon0, lat0 = map(np.radians, (lon, lat, lon0, lat0))
    a = np.sin((lat - lat0) / 2) ** 2 + np.cos(lat) * np.cos(lat0) * np.sin((lon - lon0) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


muni = pd.concat([gpd.read_parquet(f) for f in sorted(PROC.glob("municipality/pref=*/data.parquet"))])
muni = gpd.GeoDataFrame(muni, crs=6668)
pts = {y: points(y) for y in YEARS}
elev = pd.read_parquet(PROC / "elevation_mesh3.parquet").set_index("mesh3")
for y in YEARS:  # elevation / slope of the 1 km cell where each small area's point sits
    m = elev.reindex(mesh3_code(pts[y].x_code.values, pts[y].y_code.values))
    pts[y]["elev"], pts[y]["slope"] = m.elev_mean.values, m.slope_mean.values
mesh_g = gpd.GeoDataFrame(elev.dropna(subset=["elev_mean"]).reset_index(),
                          geometry=gpd.points_from_xy(*elev.dropna(subset=["elev_mean"])[["lon", "lat"]].T.values), crs=6668)
for y in YEARS:
    j = gpd.sjoin(pts[y], muni[["pref_name", "city_name", "geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated()].drop(columns="index_right")
    # Coastal / islet points can fall just outside the 2020 polygons: take the nearest one.
    miss = j.pref_name.isna()
    near = gpd.sjoin_nearest(j.loc[miss, ["geometry"]].to_crs(6677), muni[["pref_name", "city_name", "geometry"]].to_crs(6677))
    near = near[~near.index.duplicated()]
    j.loc[near.index, ["pref_name", "city_name"]] = near[["pref_name", "city_name"]].values
    print(f"{y}: {miss.sum()} points ({j.loc[miss, 'pop_total'].sum():,.0f} people) snapped to nearest municipality")
    pts[y] = j

rows = []
for pref, city, note in PLACES:
    p20 = pts[2020]
    own = p20[(p20.pref_name == pref) & (p20.city_name == city)]
    assert len(own), (pref, city)
    lon0 = np.average(own.x_code, weights=own.pop_total)
    lat0 = np.average(own.y_code, weights=own.pop_total)
    r = {"pref": pref, "city": city, "note": note}
    for y in YEARS:
        p = pts[y]
        dist = haversine(p.x_code.values, p.y_code.values, lon0, lat0)
        scopes = {"own": (p.pref_name == pref).values & (p.city_name == city).values}
        scopes |= {f"r{k}": dist <= k for k in RADII}
        for s, m in scopes.items():
            sub = p[m]
            r[f"{s}_pop{y}"] = sub.pop_total.sum()
            if y == 2020:
                e = sub.dropna(subset=["elev"])  # where people live, population-weighted
                r[f"{s}_elev_pw"] = np.average(e.elev, weights=e.pop_total)
                r[f"{s}_slope_pw"] = np.average(e.slope, weights=e.pop_total)
                aged = sub[sub.p65.notna()]  # secret cells (tiny areas) have no age breakdown
                r[f"{s}_age65"] = aged.p65.sum() / aged.pop_total.sum() * 100
                r[f"{s}_age14"] = aged.p14.sum() / aged.pop_total.sum() * 100
    # terrain of the whole municipality (all land meshes inside, inhabited or not)
    poly = muni[(muni.pref_name == pref) & (muni.city_name == city)].union_all()
    terr = mesh_g[mesh_g.within(poly)]
    r["own_elev_area"], r["own_slope_area"] = terr.elev_mean.mean(), terr.slope_mean.mean()
    for s in ["own"] + [f"r{k}" for k in RADII]:
        r[f"{s}_chg"] = (r[f"{s}_pop2020"] / r[f"{s}_pop2000"] - 1) * 100
    rows.append(r)

df = pd.DataFrame(rows)
OUT.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT, index=False)
nat = {y: pts[y].pop_total.sum() for y in YEARS}
e20 = pts[2020].dropna(subset=["elev"])
print(f"national pop-weighted elev {np.average(e20.elev, weights=e20.pop_total):.0f} m, "
      f"slope {np.average(e20.slope, weights=e20.pop_total):.1f} deg; land mean elev "
      f"{mesh_g.elev_mean.mean():.0f} m, slope {mesh_g.slope_mean.mean():.1f} deg")
print(f"national: {nat[2000]:,.0f} -> {nat[2020]:,.0f} ({(nat[2020]/nat[2000]-1)*100:+.1f}%), "
      f"65+ {pts[2020].p65.sum()/nat[2020]*100:.1f}%")
pd.set_option("display.width", 250)
print(df.round(1).to_string())
