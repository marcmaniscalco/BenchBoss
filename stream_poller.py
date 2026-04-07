"""
DynamoDB stream poller for AWS Fargate.
Runs as a long-lived process, polling for TTL-triggered REMOVE events.
Replaces the BenchBossStreamFunction Lambda.
"""

import logging
import os
import time

import boto3

from bench_boss.logging_config import configure_logging
from bench_boss.stream_handler import handle_stream_records

configure_logging()
logger = logging.getLogger(__name__)

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
DYNAMODB_TABLE = os.environ["DYNAMODB_TABLE"]
POLL_INTERVAL = 1  # seconds between GetRecords calls per shard
SHARD_REFRESH_INTERVAL = 60  # seconds between full shard rediscovery


def _get_stream_arn() -> str:
    client = boto3.client("dynamodb")
    response = client.describe_table(TableName=DYNAMODB_TABLE)
    return response["Table"]["LatestStreamArn"]


def _get_shard_iterators(stream_arn: str) -> list[str]:
    client = boto3.client("dynamodbstreams")
    shards = client.describe_stream(StreamArn=stream_arn)["StreamDescription"]["Shards"]
    iterators = []
    for shard in shards:
        resp = client.get_shard_iterator(
            StreamArn=stream_arn,
            ShardId=shard["ShardId"],
            ShardIteratorType="LATEST",
        )
        iterators.append(resp["ShardIterator"])
    return iterators


def poll_stream() -> None:
    """Poll the DynamoDB stream indefinitely, processing REMOVE events."""
    stream_arn = _get_stream_arn()
    logger.info("Starting stream poller for %s", stream_arn)

    streams_client = boto3.client("dynamodbstreams")
    shard_iterators = _get_shard_iterators(stream_arn)
    last_refresh = time.monotonic()

    while True:
        next_iterators = []
        for iterator in shard_iterators:
            try:
                response = streams_client.get_records(ShardIterator=iterator, Limit=100)
                records = response.get("Records", [])
                if records:
                    handle_stream_records(records, bot_token=DISCORD_TOKEN)
                next_iter = response.get("NextShardIterator")
                if next_iter:
                    next_iterators.append(next_iter)
            except streams_client.exceptions.ExpiredIteratorException:
                logger.warning("Shard iterator expired; will refresh on next cycle")
            except Exception:
                logger.exception("Error reading from shard iterator")

        shard_iterators = next_iterators

        if time.monotonic() - last_refresh > SHARD_REFRESH_INTERVAL:
            try:
                shard_iterators = _get_shard_iterators(stream_arn)
                last_refresh = time.monotonic()
                logger.debug("Refreshed %d shard iterators", len(shard_iterators))
            except Exception:
                logger.exception("Failed to refresh shard iterators")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    poll_stream()