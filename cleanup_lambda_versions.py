"""
Deletes unused Lambda versions to stop paying for their SnapStart cache.

SnapStart bills Lambda-SnapStart-Cached-GB-S for every published version
that has SnapStart applied, for as long as that version exists -- not just
the one currently live. AutoPublishAlias (infrastructure/template.yaml)
publishes a new version on every deploy that changes a function, and
nothing prunes old ones, so this grows unbounded. Both the Function URL and
the DynamoDB Streams trigger point at the `live` alias, not a specific
version, so every other version is safe to delete.

Run after every deploy (see the CleanupQA/CleanupProd pipeline stages in
infrastructure/pipeline.yaml) to delete every version except the one `live`
currently points to.

CodePipeline only serializes a single *stage* at a time -- it does not wait
for one execution to clear every later stage before starting the next
execution's earlier stages. Two Prod-bound executions approved close
together can therefore have this script's CleanupProd run (for execution A)
while a separate DeployProd (execution B) is still publishing a new version
on the same function. That new version isn't live yet -- the alias update
is one of the last steps of a deploy -- so without a grace period this
script deletes it as "not live", and the deploy that's still using it then
fails with "Function not found" on the version CloudFormation just created.
GRACE_PERIOD guards against exactly that: skip anything new enough that it
might belong to a deploy that's still in flight. A skipped version isn't
lost -- it's just not live, so the next run's "not live" check catches it
again.

Usage: python cleanup_lambda_versions.py --stack-name bench-boss-qa
"""

import argparse
from datetime import UTC, datetime, timedelta

import boto3
from botocore.exceptions import ClientError

GRACE_PERIOD = timedelta(minutes=10)


def _function_names_in_stack(cfn, stack_name: str) -> list[str]:
    resources = cfn.describe_stack_resources(StackName=stack_name)["StackResources"]
    return [
        r["PhysicalResourceId"]
        for r in resources
        if r["ResourceType"] == "AWS::Lambda::Function"
    ]


def _cleanup_function(lambda_client, function_name: str) -> None:
    live_version = lambda_client.get_alias(FunctionName=function_name, Name="live")[
        "FunctionVersion"
    ]

    now = datetime.now(UTC)
    paginator = lambda_client.get_paginator("list_versions_by_function")
    versions = [
        v["Version"]
        for page in paginator.paginate(FunctionName=function_name)
        for v in page["Versions"]
        if v["Version"] not in ("$LATEST", live_version)
        and now - datetime.fromisoformat(v["LastModified"]) > GRACE_PERIOD
    ]

    deleted = 0
    for version in versions:
        try:
            lambda_client.delete_function(FunctionName=function_name, Qualifier=version)
            deleted += 1
        except ClientError as e:
            print(f"  skipped {function_name}:{version} -- {e}")

    print(f"{function_name}: kept live version {live_version}, deleted {deleted}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack-name", required=True)
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    cfn = boto3.client("cloudformation", region_name=args.region)
    lambda_client = boto3.client("lambda", region_name=args.region)

    for function_name in _function_names_in_stack(cfn, args.stack_name):
        _cleanup_function(lambda_client, function_name)


if __name__ == "__main__":
    main()
