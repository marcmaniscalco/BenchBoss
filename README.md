# BenchBoss — Discord Bot on AWS Fargate

A Python Discord bot with a `/ping` command, deployable to AWS Fargate.
Discord sends an HTTP POST for every slash command to a long-running Flask server running in a Fargate container.

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
│   ├── test_bot.py         # Unit tests for bot logic
│   ├── test_calendar.py    # Unit tests for calendar parsing
│   ├── test_discord_api.py # Unit tests for embed/component builders
│   ├── test_dynamo.py      # Unit tests for DynamoDB helpers
│   └── test_stream_handler.py
├── local/
│   ├── docker-compose.yml      # DynamoDB Local + Admin UI for local development
│   ├── local_server.py         # Flask server for local development and Discord testing
│   └── create_local_table.py   # One-time script to create the local DynamoDB table
├── infrastructure/
│   └── template.yaml       # CloudFormation template (ECS Fargate + ALB + DynamoDB)
├── server.py               # Fargate HTTP server entry point (gunicorn + Flask)
├── stream_poller.py        # Fargate stream poller entry point (polls DynamoDB Streams)
├── Dockerfile              # Container image used for both Fargate services
├── register_commands.py    # One-time script to register slash commands with Discord
└── Pipfile                 # Python dependencies
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

### 4.1 Start the local server

```powershell
make server
```

This builds the Docker image and starts the full stack — the app (gunicorn on port 8080), DynamoDB Local (port 8000), and the DynamoDB admin UI (port 8001). Credentials are loaded automatically from your `.env` file.

You should see gunicorn start:
```
[INFO] Listening at: http://0.0.0.0:8080
```

### 4.2 Start ngrok

Open a **second** PowerShell window:

```powershell
ngrok http 8080
```

ngrok will print a public HTTPS URL:
```
Forwarding  https://xxxx-xx-xx-xx-xx.ngrok-free.app -> http://localhost:8080
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

The bot runs on **AWS ECS Fargate** behind an Application Load Balancer (ALB). The stream poller runs as a daemon thread inside the gunicorn process alongside the HTTP server.

**Prerequisites before deploying:**
- A custom domain with a DNS provider (e.g. Route 53)
- An ACM certificate issued for that domain in the same region as your stack

### 6.1 Prerequisites

Install the AWS CLI and Docker Desktop if you haven't already:

```powershell
winget install Amazon.AWSCLI
```

Configure AWS credentials:
```powershell
aws configure
```

### 6.2 Get an ACM certificate ARN

The ALB needs a TLS certificate issued by AWS Certificate Manager (ACM). This is free.

**Step 1 — request the certificate:**

1. Open the [ACM console](https://console.aws.amazon.com/acm) and make sure you are in **us-east-1** (or whichever region you deploy to)
2. Click **Request a certificate → Request a public certificate → Next**
3. Under **Fully qualified domain name** enter the subdomain you want to use, e.g. `bot.yourdomain.com`
4. Leave **DNS validation** selected (recommended) and click **Request**

**Step 2 — validate ownership:**

After requesting, ACM shows a **CNAME name** and **CNAME value** you must add to your domain's DNS.

- **Route 53 (same AWS account):** click **Create records in Route 53** — ACM does it automatically
- **Other DNS providers (Cloudflare, Namecheap, etc.):** copy the CNAME name/value and add a CNAME record in your DNS provider's dashboard

Validation usually completes within a few minutes. Refresh the ACM console until the status shows **Issued**.

**Step 3 — copy the ARN:**

Once issued, click the certificate and copy the **ARN** at the top. It looks like:
```
arn:aws:acm:us-east-1:123456789012:certificate/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

This is your `CERTIFICATE_ARN` for the deploy command.

---

### 6.3 Deploy the CloudFormation stack (first time)

**Step 1 — create the ECR repository (once):**

```powershell
make ecr-create
```

**Step 2 — build and push the image:**

```powershell
make push
```

**Step 3 — deploy the stack:**

You need four extra values. Find them in the AWS console:
- `VPC_ID` — the VPC to deploy into (default VPC works fine)
- `SUBNET_IDS` — at least two **public** subnets in different AZs, comma-separated
- `CERTIFICATE_ARN` — ARN of an ACM certificate for your domain

```powershell
make deploy-infra `
  DISCORD_PUBLIC_KEY=<your-key> `
  DISCORD_TOKEN=<your-token> `
  VPC_ID=vpc-xxxxxxxx `
  SUBNET_IDS="subnet-aaa,subnet-bbb" `
  CERTIFICATE_ARN=arn:aws:acm:us-east-1:123456789012:certificate/xxxx
```

### 6.4 Point your domain at the ALB

The deploy output prints the ALB DNS name:
```
ALBDnsName: bench-boss-1234567890.us-east-1.elb.amazonaws.com
```

Create a **CNAME** (or Route 53 alias) record pointing your domain to that value:
```
bot.yourdomain.com  →  bench-boss-1234567890.us-east-1.elb.amazonaws.com
```

### 6.5 Update Discord

1. Go to **Discord Developer Portal → General Information**
2. Paste `https://bot.yourdomain.com/interactions` into **Interactions Endpoint URL**
3. Click **Save Changes**

Your bot is now live on AWS.

### 6.6 Subsequent deploys

Push a new image and redeploy the stack to force ECS to pull the latest task definition:

```powershell
make deploy
```