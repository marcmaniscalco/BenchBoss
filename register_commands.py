"""
Registers slash commands with Discord. Run once after creating your bot,
and again whenever you add or change a command.

Usage:
    pipenv run python register_commands.py             # reads .env     (prod)
    pipenv run python register_commands.py --env qa    # reads .env.qa  (qa)
"""

import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

parser = argparse.ArgumentParser(description="Register slash commands with Discord.")
parser.add_argument(
    "--env",
    choices=["prod", "qa"],
    default="prod",
    help="Which env file to load: .env for prod (default), .env.qa for qa.",
)
args = parser.parse_args()

env_file = ".env" if args.env == "prod" else ".env.qa"
if not Path(env_file).is_file():
    print(
        f"error: {env_file} not found in current directory. "
        "Create it with DISCORD_TOKEN, DISCORD_APP_ID, and GUILD_ID values "
        f"for the {args.env} Discord app.",
        file=sys.stderr,
    )
    sys.exit(1)

load_dotenv(env_file, override=True)

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
DISCORD_APP_ID = os.environ["DISCORD_APP_ID"]
GUILD_ID = os.environ["GUILD_ID"]

COMMANDS = [
    {
        "name": "ping",
        "description": "Check if the bot is alive.",
    },
    {
        "name": "schedule",
        "description": "Show upcoming calendar events for the next 7 days.",
        "options": [
            {
                "name": "url",
                "description": "The webcal:// or https:// URL of the calendar.",
                "type": 3,  # STRING
                "required": True,
            }
        ],
    },
    {
        "name": "events",
        "description": "DM you a list of all events from a calendar.",
        "options": [
            {
                "name": "url",
                "description": "The webcal:// or https:// URL of the calendar.",
                "type": 3,  # STRING
                "required": True,
            }
        ],
    },
]

url = f"https://discord.com/api/v10/applications/{DISCORD_APP_ID}/guilds/{GUILD_ID}/commands"
headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}

response = requests.put(url, headers=headers, json=COMMANDS)
response.raise_for_status()

print(f"Registered {len(response.json())} command(s) for {args.env}:")
for cmd in response.json():
    print(f"  /{cmd['name']} — {cmd['description']}")
