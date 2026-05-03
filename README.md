# BenchBoss — Discord Bot on AWS Lambda (SnapStart)

A Python Discord bot deployed as two SnapStart Lambdas:

- **Interactions Lambda** — invoked via a public Function URL on every slash command / button / modal submit.
- **Stream Lambda** — triggered by DynamoDB Streams when a TTL'd event row is removed, so the next calendar event is auto-posted.

State lives in a DynamoDB table with TTL + Streams enabled. There is no VPC, no load balancer, no container.

---

## Project Structure

```
BenchBoss/
├── bench_boss/
│   ├── bot.py              # Core logic — signature verification + command handling
│   ├── calendar.py         # WebCalReader — fetches and parses iCal calendars
│   ├── discord_api.py      # Embed and component builders
│   ├── dynamo.py           # DynamoDB persistence for event RSVP state
│   └── stream_handler.py   # DynamoDB stream event processor
├── tests/
│   ├── test_bot.py
│   ├── test_calendar.py
│   ├── test_discord_api.py
│   ├── test_dynamo.py
│   ├── test_stream_handler.py
│   ├── test_lambda_function.py
│   └── test_stream_lambda_handler.py
├── local/
│   ├── docker-compose.yml      # DynamoDB Local + Admin UI
│   ├── local_server.py         # Flask server for local Discord testing via ngrok
│   └── create_local_table.py   # One-time script to create the local DynamoDB table
├── infrastructure/
│   ├── template.yaml       # SAM template (Lambda + DynamoDB)
│   └── pipeline.yaml       # CodePipeline CI/CD stack
├── buildspec.yml               # CodeBuild instructions for the pipeline
├── lambda_function.py          # Interactions Lambda entry point (Function URL)
├── stream_lambda_handler.py    # Stream Lambda entry point (DynamoDB Streams)
├── register_commands.py        # One-time script to register slash commands with Discord
└── Pipfile                     # Python dependencies
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

### Make

```powershell
winget install GnuWin32.Make
```

After installation, add Make to your PATH if prompted (or manually add `C:\Program Files (x86)\GnuWin32\bin`).

Verify:
```powershell
make --version
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

### 3.1 Create your `.env` file

Copy the example below into a file named `.env` in the project root and fill in your values. This file is git-ignored and never committed.

```
DISCORD_PUBLIC_KEY=your-discord-public-key
DISCORD_TOKEN=your-discord-bot-token
DISCORD_APP_ID=your-discord-application-id
GUILD_ID=your-discord-guild-id
```

| Variable | Where to find it |
|---|---|
| `DISCORD_PUBLIC_KEY` | Developer Portal → Your App → General Information → Public Key |
| `DISCORD_TOKEN` | Developer Portal → Your App → Bot → Token |
| `DISCORD_APP_ID` | Developer Portal → Your App → General Information → Application ID |
| `GUILD_ID` | Discord — right-click your server → Copy Server ID (requires Developer Mode) |

> Enable Developer Mode in Discord under **User Settings → Advanced → Developer Mode**.

### 3.2 Install pipenv and dependencies

```powershell
pip install pipenv
make install
```

This installs all packages from `Pipfile` (including dev dependencies like pytest) and generates `Pipfile.lock`.

### 3.3 Set up DynamoDB Local

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

### 3.4 Lint and format

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

### 3.5 Run unit tests

```powershell
make test
```

Run with coverage:

```powershell
make cov
```

`--cov=bench_boss` measures coverage for the `bench_boss` package only.
`--cov-report=term-missing` prints which lines are not covered.

### 3.6 Register slash commands with Discord

Run this once (and again whenever you add or change commands). Commands are registered as guild (server-specific) commands for instant availability during development.

```powershell
make register
```

Values are read automatically from your `.env` file.

Expected output:
```
Registered 2 command(s):
  /ping — Check if the bot is alive.
  /schedule — Show upcoming calendar events for the next 7 days.
```

---

## Part 4 — Run Locally and Test with Discord

### 4.1 Start DynamoDB Local and the dev server

In one terminal, start DynamoDB Local (and the admin UI on http://localhost:8001):

```powershell
make dynamo-up
make dynamo-init   # only needed the first time (or after a reset)
```

Then run the local Flask server (port 3000):

```powershell
make local
```

The server reads `DISCORD_PUBLIC_KEY` / `DISCORD_TOKEN` / `DYNAMODB_TABLE` from `.env`.

### 4.2 Start ngrok

Open a **second** PowerShell window:

```powershell
ngrok http 3000
```

ngrok will print a public HTTPS URL:
```
Forwarding  https://xxxx-xx-xx-xx-xx.ngrok-free.app -> http://localhost:3000
```

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

## Development Guidelines

### Unit Tests

Whenever you add or modify code in the `bench_boss/` package, add or update the corresponding unit tests in `tests/`.

- New function or method → add tests covering the happy path and edge cases
- Modified function → update existing tests to reflect the change
- New module `bench_boss/foo.py` → create `tests/test_foo.py`

Run tests with coverage:
```powershell
make cov
```

### README Sync

Whenever `CLAUDE.md` is updated, update this `README.md` to reflect the new or changed instructions.

### Filltime Role Marking

When a user RSVPs via any button (accepted / declined / tentative) or is added via the **+** button, the bot checks whether they hold the **Filltime** role (Discord role ID `1085056467763208253`).

- **Role present** → name is stored and displayed as-is.
- **Role absent** → the display name is stored with a `*` suffix (e.g. `Jane*`) so admins can see at a glance who is not a fulltime member.

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

The bot runs as two **AWS Lambda** functions deployed via SAM:

- `BenchBossFunction` — handles Discord interactions via a public Function URL.
- `BenchBossStreamFunction` — triggered by the DynamoDB table's stream when a TTL'd event row is removed.

Both functions have **SnapStart** enabled, so the published `live` alias serves restored snapshots in ~200–400ms instead of a full cold start. There is no ALB, VPC, ECS service, or NAT gateway — total infra cost at this volume is effectively $0.

### 6.1 Prerequisites

Install the AWS CLI and SAM CLI:

```powershell
winget install Amazon.AWSCLI
winget install Amazon.SAM-CLI
```

Configure AWS credentials:
```powershell
aws configure
```

### 6.2 First-time deploy

```powershell
make deploy
```

This runs `sam build` (packaging code + dependencies into a zip) and then `sam deploy`. SAM provisions an S3 bucket for artifacts automatically (`--resolve-s3`).

After it finishes, the stack outputs the interactions endpoint:

```
InteractionsUrl: https://xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.lambda-url.us-east-1.on.aws/
```

### 6.3 Update Discord

1. Go to **Discord Developer Portal → Your App → General Information**
2. Paste the Function URL from the stack output into **Interactions Endpoint URL**
3. Click **Save Changes**

Discord sends a PING to verify the endpoint signs correctly. Your bot is now live.

### 6.4 Subsequent deploys

```powershell
make deploy
```

SAM diffs the template and code, ships only what changed. Each deploy publishes a new Lambda version; SnapStart re-snapshots automatically when the version is published, so cold starts stay fast.

---

## Part 7 — CI/CD Pipeline (CodePipeline)

For automated builds and deploys, this project ships an AWS-native pipeline
defined in `infrastructure/pipeline.yaml`. The pipeline is a single
CloudFormation stack that creates:

- A CodeBuild project that runs `ruff`, `pytest --cov`, and `sam build`/`sam package`
- A CodePipeline with five stages:
  1. **Source** — pulls from CodeCommit (`BenchBoss` repo, `main` branch)
  2. **Build** — runs lint + unit tests, then packages the Lambdas
  3. **DeployQA** — applies the SAM template as `bench-boss-qa`
  4. **ApproveProd** — manual approval gate (you click **Approve** in the console)
  5. **DeployProd** — applies the same template as `bench-boss-prod`
- An EventBridge rule that triggers the pipeline on every push to `main`
- An S3 bucket for build artifacts (30-day lifecycle)

QA and Prod deploy to the **same AWS account** but to separate CloudFormation
stacks, with separate Discord apps/tokens supplied per stage from
**AWS Secrets Manager**.

### 7.1 Create a separate Discord app for QA

Repeat **Part 2** with a new Discord application. Save the QA Public Key,
Bot Token, and App ID — these are the QA credentials. The production app
keeps its existing values.

### 7.2 Create the Secrets Manager secrets

The pipeline reads each stage's Discord credentials from a single JSON
secret per stage. Create both secrets once (replace the placeholder values):

```powershell
aws secretsmanager create-secret `
  --name bench-boss/qa `
  --region us-east-1 `
  --secret-string '{\"DiscordPublicKey\":\"<qa-public-key>\",\"DiscordToken\":\"<qa-bot-token>\"}'

aws secretsmanager create-secret `
  --name bench-boss/prod `
  --region us-east-1 `
  --secret-string '{\"DiscordPublicKey\":\"<prod-public-key>\",\"DiscordToken\":\"<prod-bot-token>\"}'
```

To rotate credentials later, use `aws secretsmanager update-secret` with the
same `--secret-string` shape.

### 7.3 Bootstrap the pipeline

```powershell
make pipeline-deploy
```

This deploys the `bench-boss-pipeline` stack. The pipeline will start its
first execution as soon as a commit lands on `main` (or you can manually
release a change from the console).

### 7.4 Approve a production release

1. Open the AWS Console → **CodePipeline** → `bench-boss-pipeline`
2. Wait for **DeployQA** to go green
3. Test the QA bot in your QA Discord server
4. Click **Review** on the **ApproveProd** stage → **Approve**
5. The **DeployProd** stage runs and updates the prod stack

If you want to abandon a build instead of promoting it, click **Reject** on
the approval action — the pipeline run ends, and the next push starts a
fresh execution.

### 7.5 Cost

At low commit volume the pipeline is roughly **$2–3/month** (CodePipeline
flat fee + a handful of build minutes + two Secrets Manager secrets).
CodeCommit is free for the first 5 active users.

### 7.6 Tearing it all down

```powershell
aws cloudformation delete-stack --stack-name bench-boss-prod --region us-east-1
aws cloudformation delete-stack --stack-name bench-boss-qa --region us-east-1
aws cloudformation delete-stack --stack-name bench-boss-pipeline --region us-east-1
aws secretsmanager delete-secret --secret-id bench-boss/qa --force-delete-without-recovery --region us-east-1
aws secretsmanager delete-secret --secret-id bench-boss/prod --force-delete-without-recovery --region us-east-1
```

> The pipeline's S3 artifact bucket must be emptied before the stack will
> delete cleanly. Either empty it from the console or run
> `aws s3 rm s3://<artifact-bucket-name> --recursive` first.