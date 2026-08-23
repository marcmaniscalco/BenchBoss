# BenchBoss TODO

## Bugs

## Features
- [ ] Support scheduling multiple upcoming events (currently only posts the next one)
- [X] Edit / reschedule an existing event
- [ ] Reminder notifications before event start
- [ ] Automatically delete expired events and recreate recurring ones without significant cost increase (investigate EventBridge Scheduler or DynamoDB TTL-triggered Lambda)

## Infrastructure
- [X] Migrate from ECS + ALB back to Lambda + Function URL to eliminate ~$28/month in ALB/ECS/NAT costs
- [ ] Add CI pipeline (lint, test, deploy)
- [ ] Environment variable validation on startup
- [ ] Stop exposing Discord tokens via CodePipeline execution history — both `pipeline.yaml` and `pr-pipeline.yaml` resolve `{{resolve:secretsmanager:...}}` in the DeployQA/DeployProd action's `ParameterOverrides`, so every deploy's resolved token is visible in plaintext via `ListActionExecutions`/`GetPipelineExecution` to anyone with pipeline read access. Fix: pass only the secret *name* as a CloudFormation parameter and have `template.yaml` build the `{{resolve:secretsmanager:${DiscordSecretName}:...}}` reference itself for the Lambda's environment variables, so resolution happens inside the stack operation instead of the pipeline action config.

## Chores
- [X] Fix `make server` env vars (each Makefile line runs in a separate shell on Windows — vars don't persist)
