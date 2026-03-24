# BenchBoss — Serverless on AWS Lambda

A Python Discord bot with a `/ping` command, deployable to AWS Lambda.
Discord sends an HTTP POST for every slash command — no persistent process required.

---

## Project Structure

```
BenchBoss/
├── bench_boss/
│   ├── bot.py              # Core logic — signature verification + command handling
│   ├── calendar.py         # WebCalReader — fetches and parses iCal calendars
│   ├── discord_api.py      # Embed and component builders
│   └── dynamo.py           # DynamoDB persistence for event RSVP state
├── tests/
│   ├── test_bot.py         # Unit tests for bot logic
│   ├── test_calendar.py    # Unit tests for calendar parsing
│   ├── test_discord_api.py # Unit tests for embed/component builders
│   └── test_dynamo.py      # Unit tests for DynamoDB helpers
├── local/
│   ├── docker-compose.yml      # DynamoDB Local + Admin UI for local development
│   ├── local_server.py         # Flask server for local development and Discord testing
│   └── create_local_table.py   # One-time script to create the local DynamoDB table
├── lambda_function.py      # AWS Lambda entry point (production)
├── register_commands.py    # One-time script to register slash commands with Discord
├── Pipfile                 # Python dependencies
└── template.yaml           # AWS SAM deployment template
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
make install
```

This installs all packages from `Pipfile` (including dev dependencies like pytest) and generates `Pipfile.lock`.

### 3.2 Set up DynamoDB Local

The bot stores RSVP state in DynamoDB. For local development, `docker-compose` starts DynamoDB Local alongside a web-based admin UI so you can browse the data in your browser.

#### Start the containers

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. From the project root:

```powershell
make dynamo-up
```

This starts two containers:

| Container | Port | Purpose |
|---|---|---|
| `bench-boss-dynamo` | 8000 | DynamoDB Local |
| `bench-boss-dynamo-admin` | 8001 | Admin UI — view and edit data |

Verify they are running:

```powershell
docker ps
```

Stop/start later with:
```powershell
make dynamo-down
make dynamo-up
```

#### Create the table (once)

Run this once after the containers are up for the first time:

```powershell
make dynamo-init
```

#### View and edit data

Open **http://localhost:8001** in your browser. The admin UI lets you browse tables, inspect items, and run queries against your local DynamoDB.

> Data is stored in memory and is **lost when the container stops**. This is intentional for local dev — run `local/create_local_table.py` again after a fresh `docker-compose up`.

### 3.3 Lint and format

This project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting.

Check for lint errors:
```powershell
make lint
```

Auto-fix lint errors:
```powershell
make lint-fix
```

Format code:
```powershell
make format
```

### 3.4 Run unit tests

```powershell
make test
```

Run with coverage:

```powershell
make cov
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
make register
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
$env:DISCORD_PUBLIC_KEY = "<your-public-key>"
$env:DISCORD_TOKEN      = "<your-bot-token>"
make local
```

`make local` sets `DYNAMODB_TABLE`, `DYNAMODB_ENDPOINT`, and fake AWS credentials automatically. You only need to supply the two Discord env vars. `DYNAMODB_ENDPOINT` tells the bot to send DynamoDB requests to your local container instead of AWS.

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
3. Run `make register` again
4. Restart with `make local`

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
make deploy
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