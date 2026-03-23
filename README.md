# BenchBoss — Serverless on AWS Lambda

A Python Discord bot with a `/ping` command, deployable to AWS Lambda.
Discord sends an HTTP POST for every slash command — no persistent process required.

---

## Project Structure

```
BenchBoss/
├── bench_boss/
│   ├── bot.py           # Core logic — signature verification + command handling
│   └── calendar.py      # WebCalReader — fetches and parses iCal calendars
├── tests/
│   └── test_bot.py      # Unit tests
├── local_server.py      # Flask server for local development and Discord testing
├── lambda_function.py   # AWS Lambda entry point (production)
├── register_commands.py # One-time script to register slash commands with Discord
├── Pipfile              # Python dependencies
└── template.yaml        # AWS SAM deployment template
```

---

## Part 1 — Prerequisites

Install the following before anything else.

### Python 3.13

```powershell
winget install Python.Python.3.13
```

Verify:
```powershell
python --version
```

### AWS CLI

Required for creating the local DynamoDB table (Part 3.2) and deploying to AWS (Part 6).

```powershell
winget install Amazon.AWSCLI
```

Verify:
```powershell
aws --version
```

### ngrok

1. Download from https://ngrok.com/download (Windows 64-bit)
2. Extract `ngrok.exe` somewhere on your PATH (e.g. `C:\Windows\System32`)
3. Create a free account at https://ngrok.com
4. Authenticate ngrok with your token (found at https://dashboard.ngrok.com/get-started/your-authtoken):
```powershell
ngrok config add-authtoken <your-authtoken>
```

Verify:
```powershell
ngrok version
```

---

## Part 2 — Create a Discord Application

### 2.1 Create the app

1. Go to https://discord.com/developers/applications
2. Click **New Application**, give it a name, click **Create**

### 2.2 Note your credentials

On the **General Information** tab, copy and save:

| Value | Used in |
|---|---|
| **Application ID** | `DISCORD_APP_ID` env var |
| **Public Key** | `DISCORD_PUBLIC_KEY` env var |

### 2.3 Create a Bot and get a token

1. In the left sidebar click **Bot**
2. Under **Token** click **Reset Token**, copy and save it as `DISCORD_TOKEN`
   > Never commit this to git — treat it like a password.

### 2.4 Invite the bot to your server

1. In the sidebar click **OAuth2 → URL Generator**
2. Under **Scopes** check `applications.commands`
3. Copy the generated URL, open it in a browser, select your server, click **Authorize**

---

## Part 3 — Local Setup

### 3.1 Install pipenv and dependencies

```powershell
pip install pipenv
pipenv install --dev
```

This installs all packages from `Pipfile` (including dev dependencies like pytest) and generates `Pipfile.lock`.

### 3.2 Set up DynamoDB Local

The bot stores RSVP state in DynamoDB. For local development you run DynamoDB on your machine instead of connecting to AWS.

#### Docker (recommended)

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. Start DynamoDB Local:

```powershell
docker run -d --name dynamodb-local -p 8000:8000 amazon/dynamodb-local
```

Verify it is running:

```powershell
docker ps
```

Stop/start it later with:
```powershell
docker stop dynamodb-local
docker start dynamodb-local
```

---

#### Create the table

Once DynamoDB Local is running, create the events table. The AWS CLI sends the request to `localhost:8000` — credentials can be any non-empty string for local use:

```powershell
$env:AWS_ACCESS_KEY_ID     = "local"
$env:AWS_SECRET_ACCESS_KEY = "local"
$env:AWS_DEFAULT_REGION    = "us-east-1"

aws dynamodb create-table `
  --table-name bench-boss-events `
  --attribute-definitions AttributeName=event_key,AttributeType=S `
  --key-schema AttributeName=event_key,KeyType=HASH `
  --billing-mode PAY_PER_REQUEST `
  --endpoint-url http://localhost:8000
```

Verify the table was created:

```powershell
aws dynamodb list-tables --endpoint-url http://localhost:8000
```

Expected output:
```json
{
    "TableNames": ["bench-boss-events"]
}
```

> You only need to run `create-table` once. The table persists between restarts when using the Docker container.

### 3.3 Lint and format

This project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting.

Check for lint errors:
```powershell
pipenv run ruff check bench_boss/ tests/
```

Auto-fix lint errors:
```powershell
pipenv run ruff check --fix bench_boss/ tests/
```

Format code:
```powershell
pipenv run ruff format bench_boss/ tests/
```

### 3.4 Run unit tests

```powershell
pipenv run pytest tests/ -v
```

Run with coverage:

```powershell
pipenv run pytest tests/ -v --cov=bench_boss --cov-report=term-missing
```

`--cov=bench_boss` measures coverage for the `bench_boss` package only.
`--cov-report=term-missing` prints which lines are not covered.

### 3.5 Register slash commands with Discord

Run this once (and again whenever you add or change commands):

Commands are registered as guild (server-specific) commands for instant availability during development.

```powershell
$env:DISCORD_TOKEN  = "<your-bot-token>"
$env:DISCORD_APP_ID = "<your-application-id>"
$env:GUILD_ID       = "<your-server-id>"
pipenv run python register_commands.py
```

> Your Guild ID is found in Discord by right-clicking your server → **Copy Server ID**
> (enable Developer Mode first under Settings → Advanced).

Expected output:
```
Registered 2 command(s):
  /ping — Check if the bot is alive.
  /schedule — Show upcoming calendar events for the next 7 days.
```

---

## Part 4 — Run Locally and Test with Discord

### 4.1 Start the local server

Open a PowerShell window. You need four env vars — the Discord credentials plus the DynamoDB table name and a fake AWS region (boto3 requires one even for local endpoints):

```powershell
$env:DISCORD_PUBLIC_KEY     = "<your-public-key>"
$env:DISCORD_TOKEN          = "<your-bot-token>"
$env:DYNAMODB_TABLE         = "bench-boss-events"
$env:AWS_ENDPOINT_URL       = "http://localhost:8000"
$env:AWS_ACCESS_KEY_ID      = "local"
$env:AWS_SECRET_ACCESS_KEY  = "local"
$env:AWS_DEFAULT_REGION     = "us-east-1"
pipenv run python local_server.py
```

`AWS_ENDPOINT_URL` tells boto3 to send all AWS requests to DynamoDB Local instead of the real AWS endpoint. The `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` values can be any non-empty string — DynamoDB Local does not validate credentials.

> Make sure DynamoDB Local is running (Part 3.2) before starting the server.

You should see:
```
 * Running on http://127.0.0.1:3000
```

### 4.2 Start ngrok

Open a **second** PowerShell window:

```powershell
ngrok http 3000
```

ngrok will print a public HTTPS URL:
```
Forwarding  https://xxxx-xx-xx-xx-xx.ngrok-free.app -> http://localhost:3000
```

Copy the `https://` URL.

### 4.3 Point Discord at your local server

1. Go to **Discord Developer Portal → Your App → General Information**
2. Paste your ngrok URL + `/interactions` into **Interactions Endpoint URL**
   - e.g. `https://xxxx-xx-xx-xx-xx.ngrok-free.app/interactions`
3. Click **Save Changes**

Discord will send a verification PING to your local server. If it saves successfully, your bot is connected.

### 4.4 Test in Discord

Go to your server and type `/ping`. The bot will reply **Pong!**

> **Each time you restart ngrok** you get a new URL. Update the Interactions Endpoint URL
> in the Discord Developer Portal each session. The free ngrok plan does not support
> reserved/static URLs.

---

## Part 5 — Adding Commands

1. Add a handler in `bot.py` inside `handle_interaction()`:
   ```python
   if command == "hello":
       return {
           "statusCode": 200,
           "body": {"type": CHANNEL_MESSAGE_WITH_SOURCE, "data": {"content": "Hello!"}},
       }
   ```
2. Add the command definition to `register_commands.py`:
   ```python
   {"name": "hello", "description": "Say hello."}
   ```
3. Run `pipenv run python register_commands.py` again
4. Restart `local_server.py`

---

## Part 6 — Deploy to AWS (Production)

### 6.1 Install AWS CLI and SAM CLI

```powershell
winget install Amazon.AWSCLI
winget install Amazon.SAM-CLI
```

Configure AWS credentials:
```powershell
aws configure
```

### 6.2 Create an S3 bucket for SAM artifacts (one-time)

```powershell
aws s3 mb s3://<your-unique-bucket-name>
```

### 6.3 Deploy

```powershell
sam build
sam deploy --guided
```

Follow the prompts. When asked for `DiscordPublicKey`, paste your public key.

The deploy output will print your **Interactions URL**:
```
InteractionsUrl: https://abc123.execute-api.us-east-1.amazonaws.com/Prod/interactions
```

### 6.4 Update Discord

1. Copy the URL from the deploy output
2. Go to **Discord Developer Portal → General Information**
3. Paste it into **Interactions Endpoint URL** and click **Save Changes**

Your bot is now live on AWS.