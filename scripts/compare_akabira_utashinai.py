"""Compare census municipal totals, avoiding small-area suppression/aggregation issues.
Uses locally downloaded e-Stat Statistics GIS tables (C01, Hokkaido).
Cohort differences include deaths and census coverage changes; they are not migration counts.
"""
import csv,json,unicodedata
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'output/comparison_01218_01227';OUT.mkdir(parents=True,exist_ok=True)
TABLES={2000:'T000002',2005:'T000051',2010:'T000573',2015:'T000849',2020:'T001082'}
D={}
for year,table in TABLES.items():
 with (ROOT/f'data/raw/estat_population/extracted/tbl{table}C01.txt').open(encoding='cp932') as f:
  rd=csv.reader(f);next(rd);labels=next(rd)
  for row in rd:
   if row[0] not in ['01218','01227']:continue
   d={}
   for label,value in zip(labels,row):
    if not label:continue
    label=unicodedata.normalize('NFKC',label).replace(' ','')
    assert value not in ['X',''], (year,row[0],label)
    d[label]=int(value.replace(',','')) if value!='-' else 0
   D.setdefault(row[0],{})[year]=d
(OUT/'age_totals.json').write_text(json.dumps(D,ensure_ascii=False,indent=2)+'\n')
def pop(code,y,sex,a):return D[code][y][f'{sex}{a}~{a+4}歳']
rows=[]
for code in D:
 for y in range(2000,2020,5):
  for sex in ['男','女']:
   for a in range(0,70,5):
    n=pop(code,y,sex,a);m=pop(code,y+5,sex,a+5)
    rows.append(dict(code=code,year=y,sex=sex,age_from=a,before=n,after=m,change=m-n,pct=round((m/n-1)*100,3) if n else None))
with (OUT/'cohorts.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
for code in D:
 print(code)
 for y in range(2000,2020,5):
  for sex in ['男','女']:
   n=sum(pop(code,y,sex,a) for a in [50,55,60,65]);m=sum(pop(code,y+5,sex,a+5) for a in [50,55,60,65])
   print(y,sex,'50-69 ->55-74',n,m,round((m/n-1)*100,1))
# This comparison concerns all employed people, not manufacturing alone.
commuting={'01218':dict(resident_employed=4045,local=2928,outbound=1086,workplace_employed=4648,inbound=1689),'01227':dict(resident_employed=1150,local=565,outbound=581,workplace_employed=886,inbound=317)}
(OUT/'commuting_2020.json').write_text(json.dumps(commuting,ensure_ascii=False,indent=2)+'\n')
