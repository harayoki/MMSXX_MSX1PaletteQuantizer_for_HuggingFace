# MMSXX_MSX1PaletteQuantizer_for_HuggingFace

MMSXX MSX1 Palette Quantizer を Hugging Face Spaces（CPU, Gradio）で動かすためのアプリです。プリビルトの CLI ツールを呼び出して、画像を MSX1 向け形式へ変換します。

## 特長
- PNG 画像を最大 32 枚アップロードし、変換結果を並べてプレビューできます。
- 重要な変換パラメータ（color system, dithering, dark dithering, 8dot, distance など）を調整し、単体またはバッチで再実行できます。
- オプションで LUT ファイルをアップロードし、指定された場合のみコンバータへ渡します。
- 画像単体の PNG / SC2 ダウンロード、バッチ ZIP（png/sc2/dsk/32krom）ダウンロードに対応します。MegaROM は未実装として表示されます。

## 必要環境
- Python 3.9 以上
- `bin/` 以下に含まれる Linux 向けバイナリに実行権限が必要です。
- 依存インストール: `pip install -r requirements.txt`

## ローカルでの実行手順
1. バイナリに実行権限を付与します。
   ```bash
   chmod +x bin/msx1pq_cli bin/basic_sc2_viewer.bin bin/create_sc2_32k_rom.bin
   ```
2. Python 依存をインストールします。
   ```bash
   pip install -r requirements.txt
   ```
3. Gradio アプリを起動します。
   ```bash
   python app.py
   ```
4. ターミナルに表示されるローカル URL をブラウザで開きます。

## Hugging Face Spaces での利用
Spaces 上では `bin/` のバイナリを Python から直接実行します（ビルド不要）。エントリポイントは `app.py` で、起動時にバイナリへ実行権限を付与します。

## 補足
- UI で未指定のオプションは CLI のデフォルトを使用し、明示的に選択された引数のみを渡します。
- DSK バッチ生成は 720KB のディスク容量を超えると追加を停止し、除外されたファイルを報告します。
- 32KB ROM 作成は最大 2 枚の SC2 ファイルのみ使用し、超過分は警告とともにスキップします。
