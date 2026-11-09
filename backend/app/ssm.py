"""Secrets from SSM Parameter Store on AWS.

Lambda gets SSM_PREFIX ("/carhaul/api/", set by infra/api.tf); every parameter under it
becomes an environment variable of the same name at startup ("/carhaul/api/LIVEKIT_API_KEY" ->
LIVEKIT_API_KEY), so the rest of the app reads settings the same way locally and on AWS.
Variables already set win. The worker's secrets live under /carhaul/agent/ and ECS injects
them (infra/agent.tf); scripts/set_aws_secrets.py puts both.
"""

import os

import boto3


def load_parameters() -> None:
    prefix = os.environ.get("SSM_PREFIX")
    if not prefix:
        return
    ssm = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    pages = ssm.get_paginator("get_parameters_by_path").paginate(Path=prefix, WithDecryption=True)
    for page in pages:
        for param in page["Parameters"]:
            os.environ.setdefault(param["Name"].removeprefix(prefix), param["Value"])
