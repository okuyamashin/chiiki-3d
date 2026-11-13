"""Tidy census small-area (町丁・字) population tables, 2000-2020, into one Parquet per year.

Inputs (data/raw/estat_population/extracted/, from e-Stat 統計GIS 小地域 downloads):
  basic table  人口総数・男・女・世帯総数
  age table    年齢（5歳階級・4区分）別・男女別人口

Output: data/processed/population_{year}.parquet, one row per finest small area,
keyed by an 11-digit key_code (same scheme as the e-Stat boundary data of that year).
  "-" (zero) becomes 0; secret cells ("X" etc.) become NA.
  key_code is aligned to that year's boundaries (data/processed/shochiiki[_YYYY]/).

Run after scripts/build_geoparquet.py: .venv/bin/python scripts/build_population.py
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "raw" / "estat_population" / "extracted"
OUT = ROOT / "data" / "processed"

# year: (basic table, age table)
TABLES = {
    2000: ("T000001", "T000002"),
    2005: ("T000050", "T000051"),
    2010: ("T000572", "T000573"),
    2015: ("T000848", "T000849"),
    2020: ("T001081", "T001082"),
}
# 2000/2005 files have HTKSYU; 2010+ have HTKSYORI/HTKSAKI/GASSAN.
META = ["KEY_CODE", "HYOSYO", "HTKSYU", "CITYNAME", "NAME", "HTKSYORI", "HTKSAKI", "GASSAN"]
BASIC_NAMES = {"人口総数": "pop_total", "男": "pop_male", "女": "pop_female", "世帯総数": "households"}


def read_table(table: str) -> pd.DataFrame:
    frames = []
    for i in range(1, 48):
        path = SRC / f"tbl{table}C{i:02d}.txt"
        labels = pd.read_csv(path, encoding="cp932", nrows=1, header=0, dtype=str)
        df = pd.read_csv(path, encoding="cp932", skiprows=[1], dtype=str)
        rename = {c: labels[c].iloc[0].replace("　", "").strip() for c in df.columns if c not in META}
        frames.append(df.rename(columns=rename))
    return pd.concat(frames, ignore_index=True)


def tidy(df: pd.DataFrame) -> pd.DataFrame:
    # Drop municipality totals (5-digit) and a 9-digit parent when it has 11-digit 丁目 children.
    df = df[df["KEY_CODE"].str.len() > 5].copy()
    parents = set(df.loc[df["KEY_CODE"].str.len() == 11, "KEY_CODE"].str[:9])
    df = df[~((df["KEY_CODE"].str.len() == 9) & df["KEY_CODE"].isin(parents))]
    df["key_code"] = df["KEY_CODE"].str.ljust(11, "0")
    values = [c for c in df.columns if c not in META + ["key_code"]]
    for c in values:
        df[c] = pd.to_numeric(df[c].replace("-", "0"), errors="coerce")
    df = df.rename(columns={"CITYNAME": "city_name", "NAME": "s_name"})
    return df[["key_code", "city_name", "s_name"] + values]


def align_to_boundary(pop: pd.DataFrame, year: int) -> pd.DataFrame:
    """Rewrite key_code to the same year's boundary's when only the first 9 digits agree.

    Areas without 丁目 have a 9-digit code in the tables (padded here with "00"),
    but the boundary polygon's 11-digit code often ends in another sub-id (e.g. 01, 90).
    """
    boundary_dir = OUT / ("shochiiki" if year == 2020 else f"shochiiki_{year}")
    files = sorted(boundary_dir.glob("pref=*/data.parquet"))
    if not files:
        print(f"{year}: no boundaries in {boundary_dir.name}, key_code left unaligned")
        return pop
    keys = pd.concat([pd.read_parquet(f, columns=["key_code", "hcode"]) for f in files])
    keys = keys.loc[keys["hcode"] == 8101, "key_code"].drop_duplicates()
    loose = keys[~keys.isin(pop["key_code"])]
    by9 = loose.groupby(loose.str[:9]).agg(lambda s: s.iloc[0] if len(s) == 1 else None).dropna()
    miss = ~pop["key_code"].isin(keys)
    k9 = pop.loc[miss, "key_code"].str[:9]
    k9 = k9[~k9.duplicated(keep=False)]  # ambiguous on the stats side too: leave as is
    pop.loc[k9.index, "key_code"] = k9.map(by9).fillna(pop.loc[k9.index, "key_code"])
    return pop


def build(year: int) -> None:
    basic_id, age_id = TABLES[year]
    basic = tidy(read_table(basic_id)).rename(columns=BASIC_NAMES)
    age = tidy(read_table(age_id)).drop(columns=["city_name", "s_name"])
    age = age.rename(columns=lambda c: c.replace("、年齢「不詳」含む", ""))
    pop = basic.merge(age, on="key_code", how="left")
    pop = align_to_boundary(pop, year)
    for c in pop.columns[3:]:
        if (pop[c].dropna() % 1 == 0).all():  # counts -> nullable int; keep e.g. averages as float
            pop[c] = pop[c].astype("Int64")
    dst = OUT / f"population_{year}.parquet"
    pop.to_parquet(dst, compression="zstd", index=False)
    print(f"{year}: {len(pop)} areas, pop {pop['pop_total'].sum():,.0f}, {len(pop.columns)} columns -> {dst.name}")


if __name__ == "__main__":
    for y in TABLES:
        build(y)
