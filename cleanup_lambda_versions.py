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

Usage: python cleanup_lambda_versions.py --stack-name bench-boss-qa
"""

import argparse

import boto3
from botocore.exceptions import ClientError


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

    paginator = lambda_client.get_paginator("list_versions_by_function")
    versions = [
        v["Version"]
        for page in paginator.paginate(FunctionName=function_name)
        for v in page["Versions"]
        if v["Version"] not in ("$LATEST", live_version)
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
