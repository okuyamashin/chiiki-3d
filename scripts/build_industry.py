"""Employed persons by industry for census small areas (町丁・字) and municipalities, 2000-2020.

Input:  e-Stat 統計GIS 小地域 tables 「産業（大分類）別就業者数」 downloaded per prefecture into
        data/raw/estat_industry/<table>C<pref>.zip
          2000 T000008 (1993 revision: L サービス業 still holds 医療・福祉, 教育 ...)
          2005 T000070 (2002 revision)   2010 T000587 / 2015 T000865 / 2020 T001103 (2007/2013 revisions)
Output: data/processed/industry.parquet, one row per (year, key_code); key_code is 11 digits for small
        areas (same as population_<year>.parquet) and 5 digits for the municipality total.
        Columns: the harmonised groups below, employed (総数), employee / self / family (従業上の地位).
        "-" -> 0, secret cells ("X" etc.) -> NA.

Groups are chosen so every year can be compared; in 2000 医療・福祉 cannot be split from サービス,
so med is NA and its people sit in svc.

Run: .venv/bin/python -I scripts/build_industry.py [pref ...]   (default 01)
"""

import io
import re
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "estat_industry"
OUT = ROOT / "data" / "processed" / "industry.parquet"
TABLES = {2000: "T000008", 2005: "T000070", 2010: "T000587", 2015: "T000865", 2020: "T001103"}
URL = "https://www.e-stat.go.jp/gis/statmap-search/data?statsId={t}&code={p}&downloadType=2"
META = ["KEY_CODE", "HYOSYO", "HTKSYU", "CITYNAME", "NAME", "HTKSYORI", "HTKSAKI", "GASSAN"]

GROUPS = {  # group -> label prefixes (letter dropped) across the three classification revisions
    "prim": ["農業", "林業", "漁業", "鉱業", "農業、林業", "鉱業、採石業、砂利採取業"],
    "cons": ["建設業"],
    "manu": ["製造業"],
    "trade": ["卸・小売・飲食店", "卸売・小売業", "飲食店，宿泊業", "卸売業、小売業", "宿泊業、飲食サービス業"],
    "trans": ["運輸・通信業", "運輸業", "情報通信業", "運輸業、郵便業"],
    "med": ["医療，福祉", "医療、福祉"],
    "svc": ["電気・ガス・熱供給・水道業", "金融・保険業", "不動産業", "サービス業", "金融業、保険業",
            "不動産業、物品賃貸業", "学術研究、専門・技術サービス業", "生活関連サービス業、娯楽業",
            "教育、学習支援業", "教育，学習支援業", "複合サービス事業", "サービス業（他に分類されないもの）",
            "分類不能の産業"],
    "gov": ["公務（他に分類されないもの）", "公務（他に分類されるものを除く）"],
}
LABELS = {"prim": "農林漁業・鉱業", "cons": "建設", "manu": "製造", "trade": "卸売・小売・飲食",
          "trans": "運輸・通信", "med": "医療・福祉", "svc": "その他のサービス", "gov": "公務"}


def fetch(table: str, pref: str) -> Path:
    dst = RAW / f"{table}C{pref}.zip"
    if not (dst.exists() and zipfile.is_zipfile(dst)):
        RAW.mkdir(parents=True, exist_ok=True)
        data = urllib.request.urlopen(URL.format(t=table, p=pref), timeout=120).read()
        if not data.startswith(b"PK"):
            raise RuntimeError(f"{table} {pref}: not a zip (e-Stat returned a page)")
        dst.write_bytes(data)
        time.sleep(1)
    return dst


def clean(label: str) -> str:
    label = label.replace("　", " ").strip()
    return re.sub(r"^[Ａ-Ｚ]\s*", "", label).strip()


def read(year: int, pref: str) -> pd.DataFrame:
    with zipfile.ZipFile(fetch(TABLES[year], pref)) as z:
        raw = z.read(z.namelist()[0])
    head = pd.read_csv(io.BytesIO(raw), encoding="cp932", nrows=1, dtype=str)
    df = pd.read_csv(io.BytesIO(raw), encoding="cp932", skiprows=[1], dtype=str)
    labels = {c: clean(str(head[c].iloc[0])) for c in df.columns if c not in META}
    cols = [c for c in df.columns if c not in META]
    vals = df[cols].replace("-", "0").apply(pd.to_numeric, errors="coerce")
    first = {}  # first occurrence of a label = the industry part; the status block repeats 総数
    for c in cols:
        first.setdefault(labels[c], c)
    out = pd.DataFrame({"year": year, "code": df["KEY_CODE"], "city_name": df["CITYNAME"], "s_name": df["NAME"]})
    out["employed"] = vals[first["総数"]]
    for g, names in GROUPS.items():
        hit = [first[n] for n in names if n in first]
        out[g] = vals[hit].sum(axis=1, min_count=1) if hit else pd.NA
    if year == 2000:
        out["med"] = pd.NA
    status = {"employee": "雇用者", "self": "自営業主", "family": "家族従業者"}
    for k, prefix in status.items():
        c = next(c for c in cols if labels[c].startswith(prefix))
        out[k] = vals[c]
    return out


def tidy(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df.code.str.len().isin([5, 9, 11])].copy()
    small = df.code.str.len() > 5  # drop a 9-digit parent when it has 11-digit children (as in population)
    parents = set(df.loc[df.code.str.len() == 11, "code"].str[:9])
    df = df[~((df.code.str.len() == 9) & df.code.isin(parents))]
    df["key_code"] = df.code.where(df.code.str.len() == 5, df.code.str.ljust(11, "0"))
    return df.drop(columns="code")


def main() -> None:
    prefs = sys.argv[1:] or ["01"]
    frames = [tidy(read(y, p)) for p in prefs for y in TABLES]
    out = pd.concat(frames, ignore_index=True)
    num = ["employed", *GROUPS, "employee", "self", "family"]
    out[num] = out[num].astype("Int32")
    # some years carry no municipality rows (2010): add them as sums of the small areas
    have = set(zip(out.year, out.key_code))
    small = out[out.key_code.str.len() == 11].assign(city=lambda d: d.key_code.str[:5])
    sums = small.groupby(["year", "city"])[num].sum(min_count=1).reset_index().rename(columns={"city": "key_code"})
    sums = sums[[(y, k) not in have for y, k in zip(sums.year, sums.key_code)]]
    names = small.drop_duplicates(["year", "city"]).set_index(["year", "city"]).city_name
    sums["city_name"] = [names.get((y, k)) for y, k in zip(sums.year, sums.key_code)]
    out = pd.concat([out, sums.assign(s_name=None)], ignore_index=True)
    if OUT.exists():  # keep other prefectures already built
        old = pd.read_parquet(OUT)
        out = pd.concat([old[~old.key_code.str[:2].isin(prefs)], out], ignore_index=True)
    out.to_parquet(OUT)
    c = out[(out.key_code == "01227")].set_index("year")[["employed", *GROUPS]]
    print(f"{len(out):,} rows, prefs {sorted(out.key_code.str[:2].unique())} -> {OUT.relative_to(ROOT)}")
    print(c.to_string())


if __name__ == "__main__":
    main()
