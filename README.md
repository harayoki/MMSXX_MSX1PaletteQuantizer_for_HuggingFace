# MMSXX_MSX1PaletteQuantizer for Hugging Face Spaces

Gradio ベースの MSX1 Palette Quantizer Web UI です。PyPI 版の
`msx1palettequantizer` を利用しつつ、将来的に C++ 実行ファイル版とも
連携できる構成で初期化しています。

## 使い方（ローカル / Spaces 共通）
1. 依存関係をインストールします。
   ```bash
   pip install -r requirements.txt
   ```
2. Gradio アプリを起動します。
   ```bash
   python app.py
   ```
3. ブラウザで表示される UI から画像を最大 32 枚アップロードし、
   出力フォーマットやパレット設定を選んで変換してください。

## ディレクトリ構成
- `app.py`: Gradio アプリ本体。Spaces ではエントリポイントになります。
- `msx1_palette_ui/`: UI ロジックと処理ヘルパー。
  - `config.py`: オプション管理。Python/C++ 双方で共通利用します。
  - `processing.py`: PyPI モジュールを呼び出す画像処理。SC4 や DSK/ROM
    出力の TODO もここに記載しています。
  - `cpp_runner.py`: `bin/` に配置した C++ 実行ファイルを叩くヘルパー。
  - `output_handlers.py`: ZIP 生成と将来の DSK/ROM/MegaROM 拡張ポイント。
- `bin/`: C++ 実行ファイル配置用ディレクトリ（初期状態は README のみ）。
- `requirements.txt`: Spaces 用の依存リスト。

## C++ 実行ファイルについて
`bin/msx1palettequantizer` として CUI 版の実行ファイルを配置すると、
`msx1_palette_ui.cpp_runner.run_cpp_quantizer` から呼び出せます。

## 将来拡張
- SC4 出力の実装
- DSK/ROM/MegaROM などの追加パッケージング
- C++ バイナリとのモード切り替え UI
