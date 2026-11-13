# chiiki-3d

国勢調査の小地域（町丁・字）の統計を、地形の3D表示に重ねて、地域の人口がどう減っていくかを見るためのツールです。

## 公開ページ

**歌志内市（北海道）**: https://okuyamashin.github.io/chiiki-3d/

- 10mメッシュの標高から作った地形の上に、道路・鉄道・川と、9つの字の境界を重ねています。
- 字ごとの人口（2000〜2020年）で色を付け、男女・年齢別の人口ピラミッドを表示します。
- 1920年からの人口の推移と、産業別の就業者のグラフを切り替えて表示できます。
- 左下の ▶ を押すと、地図とグラフを動かしながら、全体 → 地区 → 動きの順にナレーション付きで説明します（18場面）。

## 構成

| 場所 | 内容 |
|---|---|
| `scripts/` | データの取得・加工、3D用データの作成、ナレーション音声の作成 |
| `docs/` | GitHub Pages で公開しているもの（ビューアと歌志内市のデータ） |
| `data/raw/manual/` | 手で入力したデータ（1920年からの人口と出典） |

ダウンロードしたデータと加工結果（`data/`、`output/`、合計12GBほど）はリポジトリに含めていません。スクリプトで作り直せます。

## 作り直し方

Python 3.10 以降と、geopandas / pandas / numpy / shapely / pyogrio / pyarrow / pyproj / scipy / pillow / matplotlib が必要です。

```sh
python -m venv .venv && .venv/bin/pip install -r requirements.txt
```

国土数値情報と e-Stat のデータを `data/raw/` に置いてから、主な処理を次の順に実行します。

```sh
.venv/bin/python -I scripts/build_geoparquet.py      # 小地域の境界（e-Stat）
.venv/bin/python -I scripts/build_population.py      # 小地域の人口・年齢（2000〜2020年）
.venv/bin/python -I scripts/build_industry.py 01     # 産業別就業者（都道府県コードを指定）
.venv/bin/python -I scripts/build_roads.py           # 道路（国土数値情報 N13）
.venv/bin/python -I scripts/build_railway.py         # 鉄道（N02）
.venv/bin/python -I scripts/build_rivers.py          # 河川・湖沼（W05・W09）
.venv/bin/python -I scripts/build_3d_terrain.py      # 地形と重ねる線・統計 → output/3d/terrain_<code>.*
sh scripts/publish_pages.sh 01227                    # 公開用に docs/ へコピー
```

ビューアは `output/3d/` を配信して `terrain.html?code=01227` を開きます（`python3 -m http.server 8791 --directory output/3d`）。

### ナレーション

ツアーの台本は `tour_<code>.json` です。各場面に説明文、カメラの位置、表示する年やグラフを書きます。`readings` は読み上げのときだけ使う読み（例：字 → あざ）です。

音声は ElevenLabs で作っています。APIキーをプロジェクト直下の `.env`（リポジトリには含めない）に `ELEVENLABS_API_KEY=...` と書き、次のように作ります。音声ファイルがない場面は、ブラウザの読み上げで再生します。

```sh
.venv/bin/python -I scripts/tts_elevenlabs.py --voice <voice_id> --model eleven_v4 --steps all
```

## データの出典

- 標高：国土地理院 標高タイル（基盤地図情報 数値標高モデル 10m）
- 行政区域・道路・鉄道・河川・湖沼：「国土数値情報（行政区域・道路・鉄道・河川・湖沼データ）」（国土交通省）を加工して作成
- 小地域の境界・人口・年齢・産業別就業者：政府統計の総合窓口（e-Stat）国勢調査 小地域集計（総務省統計局）を加工して作成
- 1920〜2010年の歌志内市の人口：歌志内市「まち・ひと・しごと創生総合戦略」（平成28年1月）掲載の国勢調査の値
- ナレーション音声：ElevenLabs（声：Konoha、モデル：Eleven v4）
- 3D表示：deck.gl
