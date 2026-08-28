"""
Post-deploy smoke test against the live QA Lambda Function URL.

Runs as the IntegrationTest stage in infrastructure/pipeline.yaml, between
DeployQA and the ApproveProd gate. Discord's own private signing key never
leaves Discord, so nothing can forge a request signed as DISCORD_PUBLIC_KEY —
instead this signs real, Discord-shaped interaction payloads with a second,
QA-only Ed25519 keypair (infrastructure/pipeline.yaml's
QaTestSigningSecretName) that the QA Lambda is separately configured to
trust via TEST_PUBLIC_KEY (see lambda_function.py::_signature_is_valid).
Prod is never given that parameter, so this bypass is structurally confined
to QA. Only stateless interactions are exercised here — nothing that writes
to the shared QA DynamoDB table.

Usage: pipenv run python tests_integration/qa_smoke_test.py <output.json>
where output.json is the CloudFormation Outputs file CodePipeline writes
for the DeployQA action (see pipeline.yaml's OutputFileName).
"""

import json
import os
import sys
import time
import uuid

import boto3
import requests
from nacl.signing import SigningKey

SECRET_NAME = os.environ.get(
    "QA_TEST_SIGNING_SECRET_NAME", "bench-boss/qa-test-signing-key"
)


def _load_function_url(output_path: str) -> str:
    with open(output_path) as f:
        outputs = json.load(f)
    return outputs["InteractionsUrl"]


def _load_signing_key() -> SigningKey:
    client = boto3.client("secretsmanager")
    secret = json.loads(client.get_secret_value(SecretId=SECRET_NAME)["SecretString"])
    return SigningKey(bytes.fromhex(secret["TestSigningPrivateKey"]))


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


def main() -> int:
    url = _load_function_url(sys.argv[1])
    signing_key = _load_signing_key()
    total = 0
    failures = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        nonlocal total
        total += 1
        print(f"[{'PASS' if condition else 'FAIL'}] {name}")
        if not condition:
            print(f"        {detail}")
            failures.append(name)

    resp = _post(url, signing_key, {"type": 1})
    check(
        "PING returns PONG",
        resp.status_code == 200 and resp.json() == {"type": 1},
        f"status={resp.status_code} body={resp.text}",
    )

    resp = _post(url, signing_key, _application_command("ping"))
    body = resp.json() if resp.ok else {}
    check(
        "/ping replies with Pong!",
        resp.status_code == 200
        and body.get("type") == 4
        and body.get("data", {}).get("content") == "Pong!",
        f"status={resp.status_code} body={resp.text}",
    )

    resp = _post(url, signing_key, _application_command("bb-help"))
    body = resp.json() if resp.ok else {}
    check(
        "/bb-help replies with an ephemeral help embed",
        resp.status_code == 200
        and body.get("type") == 4
        and bool(body.get("data", {}).get("embeds"))
        and body.get("data", {}).get("flags") == 64,
        f"status={resp.status_code} body={resp.text}",
    )

    resp = _post(url, signing_key, _application_command("create-event"))
    body = resp.json() if resp.ok else {}
    check(
        "/create-event opens the create-event modal",
        resp.status_code == 200
        and body.get("type") == 9
        and body.get("data", {}).get("custom_id") == "create_event_modal",
        f"status={resp.status_code} body={resp.text}",
    )

    resp = _post(url, signing_key, _application_command("does-not-exist"))
    body = resp.json() if resp.ok else {}
    check(
        "an unknown command replies with an error message",
        resp.status_code == 200
        and "Unknown command" in body.get("data", {}).get("content", ""),
        f"status={resp.status_code} body={resp.text}",
    )

    resp = _post(url, signing_key, {"type": 1}, bad_signature=True)
    check(
        "an invalid signature is rejected with 401",
        resp.status_code == 401,
        f"status={resp.status_code} body={resp.text}",
    )

    if failures:
        print(f"\n{len(failures)} of {total} check(s) failed: {', '.join(failures)}")
        return 1
    print(f"\nAll {total} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
