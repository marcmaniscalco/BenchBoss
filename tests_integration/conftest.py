"""
Fixtures for the QA integration test suite.

Configuration comes from the environment rather than CLI args, since pytest
fixtures can't take positional arguments — see integration-buildspec.yml for
how QA_STACK_OUTPUT_PATH and QA_TEST_SIGNING_SECRET_NAME are set.
"""

import json
import os

import boto3
import pytest
from nacl.signing import SigningKey

DEFAULT_SECRET_NAME = "bench-boss/qa-test-signing-key"


@pytest.fixture(scope="session")
def qa_function_url() -> str:
    output_path = os.environ["QA_STACK_OUTPUT_PATH"]
    with open(output_path) as f:
        outputs = json.load(f)
    return outputs["InteractionsUrl"]


@pytest.fixture(scope="session")
def signing_key() -> SigningKey:
    """The QA-only Ed25519 test-signing key (private half) — see README 7.2b."""
    secret_name = os.environ.get("QA_TEST_SIGNING_SECRET_NAME", DEFAULT_SECRET_NAME)
    client = boto3.client("secretsmanager")
    secret = json.loads(client.get_secret_value(SecretId=secret_name)["SecretString"])
    return SigningKey(bytes.fromhex(secret["TestSigningPrivateKey"]))
