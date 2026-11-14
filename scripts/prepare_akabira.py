"""Add verified municipal totals and comparison panels to the Akabira terrain viewer.
Run after build_3d_terrain.py and compare_akabira_utashinai.py. No network or TTS.
"""
import csv,json,unicodedata
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'output/3d'
p=OUT/'terrain_01218.json';D=json.loads(p.read_text())
A=json.loads((ROOT/'output/comparison_01218_01227/age_totals.json').read_text())
D['city']['pops']={y:d['総数、年齢「不詳」含む'] for y,d in A['01218'].items()}
# Municipal totals avoid suppressed small-area age cells.
D['city']['pop15']={y:d['総数、年齢「不詳」含む']-d['総数15歳未満'] for y,d in A['01218'].items()}
D['viewer']={'labelLimit':12}
slopes={}
for code in ['01218','01227']:
 d=json.loads((OUT/f'terrain_{code}.json').read_text());g=d['grid'];shape=(g['ny'],g['nx'])
 z=np.fromfile(OUT/g['bin'],dtype='<u2').reshape(shape).astype(float);z[z==65535]=np.nan;z/=10
 mask=np.fromfile(OUT/g['mask_bin'],dtype='u1').reshape(shape)>0
 # Distances in meters, matching each grid's latitude scale.
 dx=g['dlon']*111320*np.cos(np.radians(g['lat0']+(g['ny']-1)*g['dlat']/2));dy=g['dlat']*110574
 zy,zx=np.gradient(z,dy,dx);slope=np.degrees(np.arctan(np.hypot(zx,zy)));valid=mask&np.isfinite(slope)
 slopes[code]={'threshold_degrees':5,'valid_nodes':int(valid.sum()),'gentle_nodes':int((valid&(slope<5)).sum()),'gentle_km2':float((valid&(slope<5)).sum()*dx*dy/1e6),'gentle_percent':float(np.mean(slope[valid]<5)*100),'grid_dx_m':float(dx),'grid_dy_m':float(dy)}
(ROOT/'output/comparison_01218_01227/terrain_slope.json').write_text(json.dumps(slopes,ensure_ascii=False,indent=2)+'\n')
def table(title,subtitle,columns,rows,note):return dict(title=title,subtitle=subtitle,columns=columns,rows=rows,note=note)
def val(c,y,s,a):return A[c][str(y)][f'{s}{a}~{a+4}歳']
analysis={}
analysis['terrainCompare']=table('傾斜の緩い土地を比べる','市境内・傾斜5度未満。30m格子から独自計算',['指標','赤平','歌志内'],[['面積',*[f"{slopes[c]['gentle_km2']:.1f}km²" for c in ['01218','01227']]],['市内の有効格子に占める割合',*[f"{slopes[c]['gentle_percent']:.1f}％" for c in ['01218','01227']]]],'国土地理院10m DEMを30m格子に再標本化。水面・既成市街地等も含み、居住可能面積や開発可能面積ではない。高さの強調前の標高を使用。')
analysis['commuting']=table('通勤は流入超過か、流出超過か','2020年国勢調査・15歳以上・全産業',['指標','赤平','歌志内'],[['市民の就業者','4,045人','1,150人'],['市内居住・市内就業','2,928人','565人'],['市外へ通勤','1,086人','581人'],['市外へ通勤する割合','26.8％','50.5％'],['市外から通勤','1,689人','317人'],['流入 − 流出','＋603人','−264人']],'総務省「統計でみる市区町村のすがた2026」F2701/F2705/F2803、国勢調査総数。製造業だけの通勤ではない。従業地不詳等は別に残る。')
rows=[]
for y in range(2000,2020,5):
 rows.append([f'{y}→{y+5}',*[f'{(val(c,y+5,s,25)/val(c,y,s,20)-1)*100:+.1f}％' for c in ['01218','01227'] for s in ['男','女']]])
analysis['youngCompare']=table('20代前半から後半への変化','20〜24歳を5年後の25〜29歳まで追う',['期間','赤平 男','赤平 女','歌志内 男','歌志内 女'],rows,'国勢調査の市全体・男女5歳階級から計算。個人追跡ではなく、死亡・転出入・調査上の差を含む。増減の理由を直接示さない。')
rows=[]
for y in range(2000,2020,5):
 row=[f'{y}→{y+5}']
 for c in ['01218','01227']:
  for s in ['男','女']:
   n=sum(val(c,y,s,a) for a in [50,55,60,65]);m=sum(val(c,y+5,s,a+5) for a in [50,55,60,65]);row.append(f'{(m/n-1)*100:+.1f}％')
 rows.append(row)
analysis['olderCompare']=table('50〜60代の同世代人口は増えるか','50〜69歳を5年後の55〜74歳まで追う',['期間','赤平 男','赤平 女','歌志内 男','歌志内 女'],rows,'国勢調査から計算。死亡を含む人口変化で、帰郷者数や相続理由は分からない。5歳刻みでも両市・男女・全期間で減少。')
D['city']['analysis']=analysis
p.write_text(json.dumps(D,ensure_ascii=False,separators=(',',':')))
print(json.dumps(slopes,ensure_ascii=False,indent=2))
