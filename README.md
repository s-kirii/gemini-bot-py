# gemini-bot-py

`discord.py` で実装した Gemini 連携 Discord Bot です。
本リポジトリは **GCP（Compute Engine）常時運用**を前提にしています。

- コマンド: `/ask`, `/pocky`
- 応答生成: Gemini API (`generateContent`)
- 履歴保存: `data/history.json`（ユーザー単位・最新N件）
- サーバー制限: `.env` の `DISCORD_SERVER_ID` のみ実行許可
- Google Calendar 操作: 予定の登録・更新・削除・照会（Geminiが依頼文から自動判定）

詳細設計は `docs/system-specification.md` を参照してください。

## 1. 前提

- Google Cloud プロジェクト作成済み
- Discord Bot アプリ作成済み（`DISCORD_TOKEN` 取得済み）
- Gemini API キー取得済み
- Python 3.11+

## 2. Discord側の設定手順

### 2.1 Developer Portal で Bot を確認

Discord Developer Portal の対象アプリで以下を確認します。

- `Bot` タブで Bot が有効
- `TOKEN` を再発行または取得（`.env` の `DISCORD_TOKEN` に設定）

### 2.2 OAuth2 で招待 URL を作成

`OAuth2 > URL Generator` で以下を選択します。

- Scopes: `bot`, `applications.commands`
- Bot Permissions: 最低限 `View Channels`, `Send Messages`, `Read Message History`

生成された URL で、利用したいサーバーに Bot を招待します。

### 2.3 サーバー ID（Guild ID）を取得

- Discord の開発者モードを有効化
- 対象サーバーを右クリックして「サーバーIDをコピー」
- `.env` の `DISCORD_SERVER_ID` に設定

### 2.4 Interactions Endpoint URL の確認

このアプリは `discord.py` の Gateway 方式で動作します。  
`General Information` の `INTERACTIONS ENDPOINT URL` は空（未設定）にしてください。  
Webhook URL が設定されたままだと、コマンドが Python Bot 側に届かない場合があります。

## 3. GCPでの運用開始手順

### 3.1 VM作成（Free Tier想定）

GCP Console: `Compute Engine > VM instances > Create instance`

- Region: `us-west1` / `us-central1` / `us-east1`
- Machine: `e2-micro`
- Provisioning model: `Standard`
- Boot disk type: `Standard persistent disk (pd-standard)`
- Boot disk size: `30GB` 以下（例: `10GB`）
- Firewall: `Allow HTTP traffic` / `Allow HTTPS traffic` はオフ

### 3.2 SSH接続後のセットアップ

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip

cd /opt
sudo git clone https://github.com/s-kirii/gemini-bot-py.git
sudo chown -R $USER:$USER /opt/gemini-bot-py
cd /opt/gemini-bot-py

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
cp system_prompt.txt.sample system_prompt.txt
```

`.env` に最低限設定:

- `DISCORD_TOKEN`
- `DISCORD_SERVER_ID`
- `GEMINI_API_KEY`

Google Calendar 機能を使う場合は追加で以下を設定:

- `GOOGLE_CALENDAR_ID`
- `GOOGLE_SERVICE_ACCOUNT_FILE`  
  例: `/opt/gemini-bot-py/secrets/service-account.json`
- `CALENDAR_TIMEZONE`（任意、default: `Asia/Tokyo`）

### 3.3 手動起動確認

```bash
cd /opt/gemini-bot-py
source .venv/bin/activate
python main.py
```

Discord で `/pocky` か `/ask` が応答することを確認し、`Ctrl+C` で停止します。

### 3.4 systemdで常駐化

```bash
sudo tee /etc/systemd/system/gemini-bot.service >/dev/null <<'EOF2'
[Unit]
Description=Gemini Discord Bot (Python)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=__YOUR_USER__
WorkingDirectory=/opt/gemini-bot-py
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/gemini-bot-py/.venv/bin/python /opt/gemini-bot-py/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF2

sudo sed -i "s/__YOUR_USER__/$(whoami)/" /etc/systemd/system/gemini-bot.service
sudo systemctl daemon-reload
sudo systemctl enable gemini-bot
sudo systemctl start gemini-bot
```

状態確認:

```bash
sudo systemctl status gemini-bot
journalctl -u gemini-bot -f
```

`active (running)` と `connected to Gateway` が出ていれば稼働中です。

## 4. 更新手順（デプロイ）

```bash
cd /opt/gemini-bot-py
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart gemini-bot
```

## 5. 運用コマンド

- 起動: `sudo systemctl start gemini-bot`
- 停止: `sudo systemctl stop gemini-bot`
- 再起動: `sudo systemctl restart gemini-bot`
- 自動起動有効: `sudo systemctl enable gemini-bot`
- 自動起動無効: `sudo systemctl disable gemini-bot`
- ログ追跡: `journalctl -u gemini-bot -f`

## 6. 環境変数

必須:
- `DISCORD_TOKEN`
- `DISCORD_SERVER_ID`
- `GEMINI_API_KEY`

任意:
- `GEMINI_MODEL`（default: `gemini-2.5-flash`）
- `SYSTEM_PROMPT_PATH`（default: `system_prompt.txt`）
- `HISTORY_PATH`（default: `data/history.json`）
- `MAX_HISTORY_ITEMS`（default: `10`）
- `FAMILY_IDxx` / `FAMILY_NAMExx`
- `GOOGLE_CALENDAR_ID`（Calendar機能を有効化する場合は必須）
- `GOOGLE_SERVICE_ACCOUNT_FILE`（または `GOOGLE_APPLICATION_CREDENTIALS`）
- `CALENDAR_TIMEZONE`（default: `Asia/Tokyo`）

## 7. セキュリティ運用

- `.env`, `system_prompt.txt`, `data/history.json` は Git 管理しない
- 秘密情報を誤って公開した場合は即時ローテーション
- GCP Billing Budget を設定して超過通知を受ける

## 8. 補足

- `DISCORD_PUBLIC_KEY` は Python 版では未使用（Gateway方式のため）
- 他サーバーでコマンドが見えても、実行時に `DISCORD_SERVER_ID` で拒否されます
- 家庭内で使用しているDiscordサーバー内での運用のため開発しました。pockyと言うオカメインコを飼っているのでシステムプロンプトからpockyの性格をインストールしてpockyと思って話しかけています。かわいいです。コマンド名にpockyとあるのはそう言うことです。
