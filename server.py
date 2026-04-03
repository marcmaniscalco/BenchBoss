"""
HTTP server entry point for AWS Fargate.
Handles Discord interaction webhook requests.
"""

import json
import logging
import os

from flask import Flask, jsonify, request

from bench_boss.bot import handle_interaction, verify_signature

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

DISCORD_PUBLIC_KEY = os.environ["DISCORD_PUBLIC_KEY"]
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]

app = Flask(__name__)


@app.route("/interactions", methods=["POST"])
def interactions():
    signature = request.headers.get("X-Signature-Ed25519", "")
    timestamp = request.headers.get("X-Signature-Timestamp", "")
    raw_body = request.get_data()

    if not verify_signature(raw_body, signature, timestamp, DISCORD_PUBLIC_KEY):
        logger.warning("Invalid request signature from %s", request.remote_addr)
        return jsonify({"error": "Invalid request signature"}), 401

    body = json.loads(raw_body)
    logger.info("Received interaction type=%s", body.get("type"))
    result = handle_interaction(body, bot_token=DISCORD_TOKEN)
    logger.info("Responding with statusCode=%s", result["statusCode"])
    return jsonify(result["body"]), result["statusCode"]


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200