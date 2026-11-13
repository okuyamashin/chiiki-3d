# 動画制作の手順（歌志内市 01227 の例）

国勢調査の小地域データを3D地形に重ねたビューアから、ナレーション付きの動画（YouTube）と記事用の画像（note）を作るまでの流れです。
完成した動画：[北海道歌志内市の概要と人口変動](https://youtu.be/yIbe7Qq4iUc)

コード `01227` を他の市町村のコードに替えれば、同じ手順で作れます。

## 全体の流れ

| # | 工程 | 手作業 / 自動 | 主な成果物 |
|---|---|---|---|
| 1 | データを用意する | 自動（長期の人口だけ手入力） | `output/3d/terrain_<code>.*` |
| 2 | ビューアで地域を見る | 手作業（確認） | — |
| 3 | 台本を書く | **手作業** | `output/3d/tour_<code>.json` |
| 4 | ナレーション音声を作る | 自動＋読みの修正 | `output/3d/audio/<code>/NN.mp3` |
| 5 | ページを公開する | 自動 | `docs/`（GitHub Pages） |
| 6 | オープニングを書き出す | 自動 | `output/video/intro_<code>.mp4` |
| 7 | オープニングの音を作る | 自動 | `output/audio/intro.wav` |
| 8 | 説明ツアーを書き出す | 自動（20分ほど） | `output/video/tour_<code>.mp4` |
| 9 | 1本につなげる | 自動 | `output/video/movie_<code>.mp4` |
| 10 | 字幕とチャプター | 自動（英訳は手作業） | `movie_<code>.ja.srt` / `.en.srt`、`chapters_<code>.txt` |
| 11 | YouTube の文章とサムネイル | **手作業** | `output/video/youtube_<code>.md`、`thumb_<code>_*.jpg` |
| 12 | note の画像 | 自動 | `output/note_<code>/` |

6〜12 は、ビューアを配信した状態で実行します。

```sh
python3 -m http.server 8791 --directory output/3d
```

---

## 1. データを用意する

README の「作り直し方」の順に実行します。地域ごとに要るのは次の2つです。

- `build_industry.py <都道府県コード>`：産業別の就業者（2000〜2020年）
- `build_3d_terrain.py`：地形・道路・鉄道・川・字の境界と、字ごとの人口・年齢・産業をまとめる

長期の人口（1920年〜）は国勢調査の小地域にないので、市の総合戦略などから `data/raw/manual/longrun_population.csv` に手で入力します。出典もそこに書きます。

## 2. ビューアで地域を見る

`http://localhost:8791/terrain.html?code=<code>` を開き、年のスライダー、人口ピラミッド、グラフ（長期の人口・産業）を切り替えて、話の材料を探します。
歌志内では次のことが分かりました。

- 谷の奥から人がいなくなる
- 若い女性が先に減る
- 高齢になっても戻らない
- 東光だけが例外

## 3. 台本を書く（`tour_<code>.json`）

構成は **全体 → 地区 → 動き → まとめ** の順です。まとめでは、次の3つを分けて説明します。

- その地域ならではのこと
- 同じ種類の町（炭鉱の町など）に共通すること
- 過疎地一般に共通すること

各場面に書くもの：

| キー | 内容 |
|---|---|
| `part` / `title` | 区切りと場面の題（YouTube のチャプター名になる） |
| `view` | カメラ（`at`、`zoom`、`pitch`、`bearing`、`shift`） |
| `set` | 表示（年、色分け、ピラミッド、グラフ）。前の場面の設定を引き継ぐ |
| `focus` | 枠で強調する字 |
| `text` | ナレーションと字幕の文。1文ずつ「。」で区切る |

そのほかに、次の項目も書きます。

- `intro.telop`：オープニングのテロップ。`{pop}` は2020年の人口に置き換わる
- `readings`：読み上げのときだけ使う読み。例：字→あざ、歌志内→うたしない、赤平→あかびら、その間→そのあいだ

数字は必ずビューアのデータで確かめてから書きます。

## 4. ナレーション音声を作る（ElevenLabs）

APIキーはプロジェクト直下の `.env` に `ELEVENLABS_API_KEY=...` と書きます。`.env` は git に入れません。

```sh
.venv/bin/python -I scripts/tts_elevenlabs.py --voice T7yYq3WpB94yAuOXraRi --model eleven_v4 --steps 1   # まず1場面で試す
.venv/bin/python -I scripts/tts_elevenlabs.py --voice T7yYq3WpB94yAuOXraRi --model eleven_v4 --steps all
```

- 声は Konoha、モデルは Eleven v4 を使っています。18場面でおよそ3,000文字を使います。
- 読み間違いがあったら、`readings` に追加してその場面だけ作り直します（例：`--steps 7,9,17`）。

## 5. ページを公開する

```sh
sh scripts/publish_pages.sh 01227
```

ビューア、データ、台本、音声を `docs/` にコピーします。commit して push すると GitHub Pages に反映されます。

## 6. オープニングを書き出す

日本全体から回転しながら市まで近づき、テロップ「北海道歌志内市」「人口2,989人（2020年）」を出します。最後は台本の最初の場面と同じ表示で終わるので、ツアーと切れ目なくつながります。

```sh
node scripts/render_intro.mjs --code 01227
```

- 1920×1080、30fps です。`--ui 1.5` でページを1.5倍の大きさで描き、字幕や地名を読みやすくしています。
- 1コマごとにタイルの読み込みを待つので、回線が遅くてもカクつきません。

## 7. オープニングの音を作る

```sh
node scripts/make_intro_audio.mjs --len <オープニングの秒数>
```

プログラムで合成するので、素材も著作権の心配もありません。音の構成は次のとおりです。

- 降りてくるにつれて開いていくパッド
- テロップと着地に合わせたベル
- 風の音

## 8. 説明ツアーを書き出す

```sh
node scripts/render_tour.mjs --code 01227
```

場面ごとの時間配分は次のとおりです。

- カメラの移動：2.2秒
- ナレーションの開始：場面の始まりから1.2秒後
- 次の場面へ：ナレーションの終わりから0.9秒後
- 最後の余白：2.5秒

ナレーションの mp3 を同じ時間軸に並べて、映像と一緒に MP4 にします。20分ほどかかります。

## 9. 1本につなげる

```sh
sh scripts/make_movie.sh 01227
```

「オープニングの映像＋音」と「ツアーの映像＋ナレーション」をつなぎます。歌志内は7分04秒になりました。

## 10. 字幕とチャプター

```sh
.venv/bin/python -I scripts/make_subtitles.py 01227
```

次のファイルができます。

- `movie_<code>.ja.srt`：日本語字幕。台本の漢字表記で、読みの表記ではありません
- `chapters_<code>.txt`：YouTube のチャプター

英語字幕を作るには `output/3d/tour_<code>.en.json` を手で用意します。日本語の1文に英語を1文ずつ対応させ、場面の題も英訳します。用意してあれば、次の2つも一緒にできます。

- `movie_<code>.en.srt`
- `chapters_<code>.en.txt`

字幕の時刻は、各場面のナレーションを文の長さで按分したものです。実際の音声とのずれは0.1秒以内でした。

## 11. YouTube の文章とサムネイル

`output/video/youtube_<code>.md` に、日本語と英語の次の項目をまとめます。

- タイトル
- 説明
- チャプター（10で作ったもの）
- データの出典
- 制作（deck.gl、ElevenLabs など）
- ハッシュタグ

推計（2050年の人口など）は、独自の推計であることを出典に明記します。

サムネイルには、オープニングの終わりのコマ（テロップが出ている、着地直前の場面）を 1280×720 で切り出して使います。

```sh
ffmpeg -ss <秒> -i output/video/intro_01227.mp4 -frames:v 1 -vf scale=1280:720 output/video/thumb_01227_<秒>.jpg
```

アップロードするもの：

- 動画：`movie_<code>.mp4`
- 字幕：`.ja.srt` と `.en.srt`
- サムネイル
- タイトルと説明：`youtube_<code>.md` から貼り付け

## 12. note の画像

```sh
node scripts/render_note_images.mjs --code 01227
```

`output/note_<code>/` に4枚できます。番号は記事の【画像】の目印に対応しています。

| ファイル | 内容 |
|---|---|
| `01_longrun.png` | 1920年からの人口の推移 |
| `02_industry.png` | 産業別の就業者 |
| `03_map2020` | 字ごとの人口で色を付けた地図 |
| `04_compare` | 2000年と2020年の比較（地図と人口ピラミッド） |

- 地図の2枚は書き出したあと JPG にしました。容量を抑えるためです。
- 記事の下書きは `articles/note_<code>.md` です。

---

## 他の地域で作るときに手で直すところ

- **長期の人口**：`data/raw/manual/longrun_population.csv`
- **台本**：`tour_<code>.json` の文、カメラ、`readings`（地名の読みは必ず確認）。英語字幕を作るなら `tour_<code>.en.json` と、地名のローマ字表記
- **オープニング**：テロップ（都道府県名・市町村名）。オープニングの長さが変わったら、音の `--len`
- **YouTube の文章**：出典と、その地域ならではの説明
