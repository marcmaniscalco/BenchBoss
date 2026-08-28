"""
Post-deploy smoke test against the live QA Lambda Function URL.

Runs as the IntegrationTest stage in infrastructure/pipeline.yaml, between
DeployQA and the ApproveProd gate. Discord's own private signing key never
leaves Discord, so nothing can forge a request signed as DISCORD_PUBLIC_KEY —
instead this signs real, Discord-shaped interaction payloads with a second,
QA-only Ed25519 keypair (see conftest.py's `signing_key` fixture) that the QA
Lambda is separately configured to trust via TEST_PUBLIC_KEY (see
lambda_function.py::_signature_is_valid). Prod is never given that
parameter, so this bypass is structurally confined to QA. Only stateless
interactions are exercised here — nothing that writes to the shared QA
DynamoDB table.

Usage: pipenv run pytest tests_integration/ -v
"""

import json
import time
import uuid

import requests
from nacl.signing import SigningKey


def _sign(signing_key: SigningKey, raw_body: bytes) -> tuple[str, str]:
    timestamp = str(int(time.time()))
    signature = signing_key.sign(timestamp.encode() + raw_body).signature.hex()
    return signature, timestamp


def _post(
    url: str, signing_key: SigningKey, body: dict, *, bad_signature: bool = False
) -> requests.Response:
    raw = json.dumps(body).encode()
    if bad_signature:
        signature, timestamp = "00" * 64, str(int(time.time()))
    else:
        signature, timestamp = _sign(signing_key, raw)
    return requests.post(
        url,
        data=raw,
        headers={
            "Content-Type": "application/json",
            "X-Signature-Ed25519": signature,
            "X-Signature-Timestamp": timestamp,
        },
        timeout=10,
    )


def _application_command(name: str) -> dict:
    return {
        "type": 2,
        "id": str(uuid.uuid4()),
        "application_id": "test-app",
        "token": "test-token",
        "guild_id": "test-guild",
        "channel_id": "test-channel",
        "data": {"id": str(uuid.uuid4()), "name": name},
    }


def test_ping_returns_pong(qa_function_url, signing_key):
    resp = _post(qa_function_url, signing_key, {"type": 1})
    assert resp.status_code == 200
    assert resp.json() == {"type": 1}


def test_ping_command_replies_pong(qa_function_url, signing_key):
    resp = _post(qa_function_url, signing_key, _application_command("ping"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == 4
    assert body["data"]["content"] == "Pong!"


def test_bb_help_replies_with_ephemeral_embed(qa_function_url, signing_key):
    resp = _post(qa_function_url, signing_key, _application_command("bb-help"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == 4
    assert body["data"]["embeds"]
    assert body["data"]["flags"] == 64


def test_create_event_opens_modal(qa_function_url, signing_key):
    resp = _post(qa_function_url, signing_key, _application_command("create-event"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == 9
    assert body["data"]["custom_id"] == "create_event_modal"


def test_unknown_command_replies_with_error(qa_function_url, signing_key):
    resp = _post(qa_function_url, signing_key, _application_command("does-not-exist"))
    assert resp.status_code == 200
    assert "Unknown command" in resp.json()["data"]["content"]


def test_invalid_signature_returns_401(qa_function_url, signing_key):
    resp = _post(qa_function_url, signing_key, {"type": 1}, bad_signature=True)
    assert resp.status_code == 401
