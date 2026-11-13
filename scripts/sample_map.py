"""Sanity-check map: nationwide outline + household density by 町丁 for Shibuya/Meguro.

Run: .venv/bin/python scripts/sample_map.py  -> output/sample_map.png
"""

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
plt.rcParams["font.family"] = "Hiragino Sans"

japan = gpd.read_parquet(PROC / "japan_prefectures.parquet")
tokyo = gpd.read_parquet(PROC / "shochiiki" / "pref=13" / "data.parquet")
area = tokyo[tokyo["city_name"].isin(["渋谷区", "目黒区"]) & (tokyo["hcode"] == 8101)].to_crs(6677)
area = area.dissolve(by="key_code", aggfunc={"city_name": "first", "s_name": "first", "setai": "sum"}).reset_index()
area["setai_per_ha"] = area["setai"] / (area.geometry.area / 10_000)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 7), gridspec_kw={"width_ratios": [1, 1.3]})
japan.plot(ax=ax1, color="#f2f2f2", edgecolor="#888", linewidth=0.4)
japan[japan["pref"] == "13"].plot(ax=ax1, color="#4a7bd0")
ax1.set_xlim(127.5, 146.5); ax1.set_ylim(30, 46)
ax1.set_title("都道府県 白地図（japan_prefectures.parquet）"); ax1.set_axis_off()

area.plot(ax=ax2, column="setai_per_ha", cmap="Blues", scheme="quantiles", k=5,
          edgecolor="white", linewidth=0.3, legend=True,
          legend_kwds={"title": "世帯/ha（5分位）", "loc": "lower left", "fontsize": 8})
area.dissolve(by="city_name").boundary.plot(ax=ax2, color="#333", linewidth=1)
ax2.set_title(f"渋谷区・目黒区 町丁別 世帯密度（2020年国勢調査, {len(area)}町丁）"); ax2.set_axis_off()

out = ROOT / "output" / "sample_map.png"
out.parent.mkdir(exist_ok=True)
fig.tight_layout(); fig.savefig(out, dpi=130)
print(out)
