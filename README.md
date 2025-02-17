# bot_template

## 仮想環境の作成

プロジェクトのルートディレクトリで以下のコマンドを実行して仮想環境を作成します。

```bash
# 環境構築
python3 -m venv venv
#仮想環境のアクティベート
source venv/bin/activate
# 依存関係のインストール
pip install -r requirements.txt
```

## envの作成

コピーして秘密鍵の入力

```bash
cp .env_copy .env
```

## 実行

```bash
python ./src/2_simple_transfer.py
```

## 依存関係の保存

```bash
pip freeze >! requirements.txt
```
