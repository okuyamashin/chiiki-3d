"""Collect the prepared Kamikoani upload assets; no publishing or network actions."""
from pathlib import Path
import shutil, os, re, json
ROOT=Path(__file__).resolve().parent.parent
out=ROOT/'output/upload_05327'
for d in ['youtube','note/images']: (out/d).mkdir(parents=True,exist_ok=True)
files=['movie_05327.mp4','movie_05327.ja.srt','movie_05327.en.srt','thumb_05327.jpg','chapters_05327.txt','chapters_05327.en.txt','youtube_05327.md']
files += [f'youtube_05327.{lang}.{kind}.txt' for lang in ['ja','en'] for kind in ['title','description']]
for name in files:
 src=ROOT/'output/video'/name; dst=out/'youtube'/name
 if dst.exists(): dst.unlink()
 if name.endswith('.mp4'): os.link(src,dst)
 else: shutil.copy2(src,dst)
shutil.copy2(ROOT/'articles/note_05327.md',out/'note/note_05327.md')
for name in ['01_terrain.png','02_industry.png','03_map2020.png','04_compare.png']:
 shutil.copy2(ROOT/'output/note_05327'/name,out/'note/images'/name)
shutil.copy2(ROOT/'output/video/thumb_05327.jpg',out/'note/cover_05327.jpg')
(out/'README.md').write_text('''# 上小阿仁村 公開用一式

## YouTube

- 本編：youtube/movie_05327.mp4（1080p・60fps、約7分37秒、日本語Otani音声）
- サムネイル：youtube/thumb_05327.jpg（1280×720）
- 字幕：youtube/movie_05327.ja.srt ／ movie_05327.en.srt
- 日英投稿文一覧：youtube/youtube_05327.md
- 貼り付け用：youtube/youtube_05327.ja.title.txt と .ja.description.txt
- 英語翻訳欄用：youtube/youtube_05327.en.title.txt と .en.description.txt
- 日英チャプター：youtube/chapters_05327.txt と chapters_05327.en.txt（説明文にも収録）

本編をアップし、動画の言語を日本語に設定します。日本語・英語の字幕をそれぞれ「タイミングあり」で追加し、英語タイトルと説明を翻訳欄に登録してください。字幕の文内時刻は各音声の長さと日本語の文字数から推定しているため、公開前にプレビューで確認してください。

## note

- 本文：note/note_05327.md
- 本文画像4点：note/images/
- 見出し画像：note/cover_05327.jpg

本文を貼り付け、画像を各挿入位置にアップロードしてください。見出し画像はnote側でトリミングを確認します。YouTube動画URLは本文に反映済みです。note編集画面でURLを単独行に貼り付け、埋め込み表示を確認してください。

推奨タグ：上小阿仁村、秋田県、人口減少、林業、地理、データ可視化

## 公開前の残作業

- noteへの本文・画像の配置と、動画の埋め込み確認
- 音声・字幕・リンクの最終プレビュー

YouTube：https://youtu.be/acN0Qy7RMnI

公開ビューアー：https://okuyamashin.github.io/chiiki-3d/?code=05327

このフォルダーを生成する処理ではアップロード・公開は行いません。

動画は元ファイルとハードリンクで共有しています。配布・コピー時は通常のファイルとして扱えます。
''')
manifest=[{'path':str(p.relative_to(out)),'bytes':p.stat().st_size} for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifest.json']
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
# Validate subtitle ordering and time bounds, title/description limits and required asset presence.
for lang in ['ja','en']:
 s=(out/f'youtube/movie_05327.{lang}.srt').read_text()
 cues=s.strip().split('\n\n'); last=0
 for cue in cues:
  a,b=cue.splitlines()[1].split(' --> ')
  def seconds(t):
   h,m,s=t.replace(',','.').split(':');return int(h)*3600+int(m)*60+float(s)
  a,b=seconds(a),seconds(b); assert last<=a<b<=456.8;last=b
 title=(out/f'youtube/youtube_05327.{lang}.title.txt').read_text().strip()
 desc=(out/f'youtube/youtube_05327.{lang}.description.txt').read_text()
 assert len(title)<=100 and len(desc)<=5000
 print(lang,len(cues),'cues; title',len(title),'description',len(desc))
print(out)
