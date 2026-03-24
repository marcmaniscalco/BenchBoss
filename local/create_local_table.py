"""
Creates the BenchBoss DynamoDB table in the local Docker instance.
Run once after starting docker-compose:

    docker-compose -f local/docker-compose.yml up -d
    python local/create_local_table.py
"""

import boto3

TABLE_NAME = "bench-boss-local"

client = boto3.client(
    "dynamodb",
    endpoint_url="http://localhost:8000",
    region_name="us-east-1",
    aws_access_key_id="local",
    aws_secret_access_key="local",
)

existing = client.list_tables()["TableNames"]
if TABLE_NAME in existing:
    print(f"Table '{TABLE_NAME}' already exists.")
else:
    client.create_table(
        TableName=TABLE_NAME,
        AttributeDefinitions=[{"AttributeName": "event_key", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "event_key", "KeyType": "HASH"}],
        BillingMode="PAY_PER_REQUEST",
    )
    print(f"Table '{TABLE_NAME}' created.")