# chiiki-3d

国勢調査の小地域（町丁・字）の統計を、地形の3D表示に重ねて、地域の人口がどう減っていくかを見るためのツールです。

## 公開ページ

**歌志内市（北海道）**: https://okuyamashin.github.io/chiiki-3d/

動画（YouTube）：[北海道歌志内市の概要と人口変動](https://youtu.be/yIbe7Qq4iUc)

- 10mメッシュの標高から作った地形の上に、道路・鉄道・川と、9つの字の境界を重ねています。
- 字ごとの人口（2000〜2020年）で色を付け、男女・年齢別の人口ピラミッドを表示します。
- 1920年からの人口の推移と、産業別の就業者のグラフを切り替えて表示できます。
- 左下の 🗾 を押すと、日本全体から一回転しながら歌志内市まで近づくイントロを流します。URLの末尾に `?intro=1` を付けると、開いたときに自動で流れます（動画の録画用）。
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

### 上小阿仁村のビューア

上小阿仁村（秋田県、`05327`）は、村の外接矩形から東西南北に約8kmの余白を取り、その範囲に周辺自治体を切り抜きます。隣接自治体の全域を含めず、小阿仁川の下流や周辺道路とのつながりを見るための範囲です。30m格子で地形を作ります。

```sh
.venv/bin/python -I scripts/build_industry.py 05
.venv/bin/python -I scripts/build_3d_terrain.py 05 上小阿仁村 --margin-km 8
cp docs/index.html output/3d/terrain.html
python3 -m http.server 8791 --directory output/3d
```

`http://localhost:8791/terrain.html?code=05327` を開きます。2000〜2020年の10地区の人口・男女年齢構成・産業別就業者を表示できます。説明ツアーは `scripts/tours/05327.scenes.json` を `scripts/compile_terrain_tour.py 05327` で生成します。長期人口は準備中です。ナレーションはOtaniで生成済みで、試作動画は `output/video/movie_05327.mp4`、確認用は `output/video/movie_05327_preview.mp4` です。`--margin-km` を省略すると従来どおり隣接自治体の全域を含めます。

### 動画の書き出し

動画制作の全体の手順は [VIDEO.md](VIDEO.md) にまとめています。

オープニングと説明ツアーを1コマずつ描いて、1本の MP4 にします（Google Chrome、Node.js、ffmpeg が必要）。ビューアを配信した状態で実行します。

```sh
npm install
node scripts/render_intro.mjs --code 01227      # オープニング（音なし）→ output/video/intro_01227.mp4
node scripts/make_intro_audio.mjs               # オープニングの音 → output/audio/intro.wav
node scripts/render_tour.mjs --code 01227       # ナレーション付きツアー → output/video/tour_01227.mp4（20分ほど）
sh scripts/make_movie.sh 01227                  # つなげる → output/video/movie_01227.mp4
.venv/bin/python -I scripts/make_subtitles.py   # 日本語・英語字幕（SRT）とYouTubeのチャプター
```

英語字幕の訳は `tour_<code>.en.json`（ナレーションの1文ごとに1行）にあります。

動画では字幕や地名が読めるよう、ページを1.5倍の大きさで描きます（`--ui` で変更）。

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
- イントロの写真：国土地理院 全国最新写真（シームレス）
- 3D表示：deck.gl

上小阿仁村の公開ビューア：https://okuyamashin.github.io/chiiki-3d/?code=05327

YouTube・noteの公開用文章、字幕、画像は [publication/05327](publication/05327/) に収録しています。本編MP4はサイズが大きいためリポジトリには含めません。

### 赤平市：歌志内との比較

赤平市（`01218`）の30m地形と15場面の解説ツアーです。通勤の流入・流出、20代男女、50〜60代の同世代人口、傾斜の緩い土地を歌志内と比較します。

```sh
.venv/bin/python -I scripts/build_3d_terrain.py 01 赤平市 --margin-km 8
.venv/bin/python scripts/compare_akabira_utashinai.py
.venv/bin/python scripts/prepare_akabira.py
.venv/bin/python scripts/compile_terrain_tour.py 01218
cp docs/index.html output/3d/terrain.html
```

`http://localhost:8791/terrain.html?code=01218`。解説はブラウザの日本語音声で再生します。Otani音声と動画は未生成です。台本は [articles/tour_01218.md](articles/tour_01218.md)、比較の方法は [articles/comparison_01218_01227.md](articles/comparison_01218_01227.md)。`prepare_akabira.py` は歌志内の生成済み地形も使用します。

194小地域の人口は全区分を色で表示し、地名・地区別人口ピラミッドは混雑を避け人口上位12区分に絞っています。人口の総数と15歳以上の分母は、秘匿を含む小地域の年齢の合算ではなく市全体の総数を使用します。比較表は「グラフ」から選択できます。
