# gemini-bot-py
Pythonで実装したDiscord Botです。Gemini APIを活用し、会話履歴の保持、リアルタイム検索を実現しています。ツール開発によって将来的ににエージェント化したいです。
JSで実装しているGEMINI-BOTのPython版。

## 実装済み機能

- Discord Slash Command (`/ask`) を受け取って Gemini API に問い合わせ
- 先に defer してから応答を書き換え（Discordの3秒制限対策）
- ユーザー単位の会話履歴を保持（JSONファイル永続化、直近N件）
- `tools: [{"google_search": {}}]` を使った Gemini 呼び出し
- サーバーID制限（指定サーバーのみ利用可）
- `FAMILY_IDxx` / `FAMILY_NAMExx` による表示名マッピング

## 必要環境

- Python 3.11+
- Discordアプリ作成済み（Bot tokenを取得済み）
- Gemini APIキー

## セットアップ

1. 依存インストール

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. 設定ファイル作成

```bash
cp .env.example .env
cp system_prompt.txt.sample system_prompt.txt
```

3. `.env` を編集

- 必須: `DISCORD_TOKEN`, `DISCORD_SERVER_ID`, `GEMINI_API_KEY`
- 任意: `GEMINI_MODEL`, `HISTORY_PATH`, `MAX_HISTORY_ITEMS`, `FAMILY_IDxx/FAMILY_NAMExx`

## 起動

```bash
python main.py
```

起動時に `DISCORD_SERVER_ID` のギルドへ `/ask` を同期します。

## コマンド

- `/ask message:<質問文>`

## ファイル構成

- `main.py`: エントリポイント
- `bot/config.py`: 環境変数読み込み
- `bot/discord_bot.py`: Discordイベント処理
- `bot/gemini_client.py`: Gemini API呼び出し
- `bot/history_store.py`: 会話履歴永続化
- `system_prompt.txt`: システムプロンプト（ローカル管理）

## 備考

- 既存JS版の `DISCORD_PUBLIC_KEY` はHTTPインタラクション署名検証用です。
  Python版はGateway接続方式のため、実行時には使用していません。
