"""Tests for the Lambda interactions handler entry point."""

import base64
import json
import os
import time
from unittest.mock import patch

from nacl.signing import SigningKey

# Module under test reads these at import time.
_signing_key = SigningKey.generate()
_public_key_hex = bytes(_signing_key.verify_key).hex()
os.environ["DISCORD_PUBLIC_KEY"] = _public_key_hex
os.environ["DISCORD_TOKEN"] = "test-bot-token"

import lambda_function  # noqa: E402


def _signed(body_bytes: bytes) -> tuple[str, str]:
    timestamp = str(int(time.time()))
    signature = _signing_key.sign(timestamp.encode() + body_bytes).signature.hex()
    return signature, timestamp


def _ping_event(*, b64: bool = False) -> dict:
    raw = json.dumps({"type": 1}).encode()
    signature, timestamp = _signed(raw)
    body = base64.b64encode(raw).decode() if b64 else raw.decode()
    return {
        "headers": {
            "x-signature-ed25519": signature,
            "x-signature-timestamp": timestamp,
        },
        "body": body,
        "isBase64Encoded": b64,
    }


def test_ping_returns_pong():
    response = lambda_function.lambda_handler(_ping_event(), context=None)
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"type": 1}


def test_base64_encoded_body_is_decoded():
    response = lambda_function.lambda_handler(_ping_event(b64=True), context=None)
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"type": 1}


def test_invalid_signature_returns_401():
    raw = json.dumps({"type": 1}).encode()
    event = {
        "headers": {
            "x-signature-ed25519": "00" * 64,
            "x-signature-timestamp": str(int(time.time())),
        },
        "body": raw.decode(),
        "isBase64Encoded": False,
    }
    response = lambda_function.lambda_handler(event, context=None)
    assert response["statusCode"] == 401
    assert json.loads(response["body"]) == {"error": "Invalid request signature"}


def test_uppercase_headers_are_normalized():
    raw = json.dumps({"type": 1}).encode()
    signature, timestamp = _signed(raw)
    event = {
        "headers": {
            "X-Signature-Ed25519": signature,
            "X-Signature-Timestamp": timestamp,
        },
        "body": raw.decode(),
        "isBase64Encoded": False,
    }
    response = lambda_function.lambda_handler(event, context=None)
    assert response["statusCode"] == 200


def test_application_command_dispatches_to_bot():
    body = {"type": 2, "data": {"name": "ping"}}
    raw = json.dumps(body).encode()
    signature, timestamp = _signed(raw)
    event = {
        "headers": {
            "x-signature-ed25519": signature,
            "x-signature-timestamp": timestamp,
        },
        "body": raw.decode(),
        "isBase64Encoded": False,
    }

    with patch("lambda_function.handle_interaction") as mock_handle:
        mock_handle.return_value = {
            "statusCode": 200,
            "body": {"type": 4, "data": {"content": "Pong!"}},
        }
        response = lambda_function.lambda_handler(event, context=None)

    mock_handle.assert_called_once()
    assert mock_handle.call_args.kwargs["bot_token"] == "test-bot-token"
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"type": 4, "data": {"content": "Pong!"}}
