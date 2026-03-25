"""
Registers slash commands with Discord. Run once after creating your bot.

Usage:
    set DISCORD_TOKEN=<your-bot-token>
    set DISCORD_APP_ID=<your-application-id>
    python register_commands.py
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

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
]

url = f"https://discord.com/api/v10/applications/{DISCORD_APP_ID}/guilds/{GUILD_ID}/commands"
headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}

response = requests.put(url, headers=headers, json=COMMANDS)
response.raise_for_status()

print(f"Registered {len(response.json())} command(s):")
for cmd in response.json():
    print(f"  /{cmd['name']} — {cmd['description']}")