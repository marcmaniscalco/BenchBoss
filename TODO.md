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
- [ ] Stop exposing Discord tokens via CodePipeline execution history — `pipeline.yaml` (DeployQA `infrastructure/pipeline.yaml:262-263`, DeployProd `infrastructure/pipeline.yaml:295-296`) and `pr-pipeline.yaml` (DeployQA `infrastructure/pr-pipeline.yaml:370-371`) all resolve `{{resolve:secretsmanager:...}}` in the deploy action's `ParameterOverrides`, so every deploy's resolved token is visible in plaintext via `ListActionExecutions`/`GetPipelineExecution` to anyone with pipeline read access.
  - Fix: change `template.yaml`'s `DiscordPublicKey`/`DiscordToken` Parameters (`infrastructure/template.yaml:12-19`) to a single `DiscordSecretName` Parameter, and have the template build `!Sub "{{resolve:secretsmanager:${DiscordSecretName}:SecretString:DiscordToken}}"` itself for `BenchBossFunction`'s `DISCORD_PUBLIC_KEY`/`DISCORD_TOKEN` env vars (`infrastructure/template.yaml:52-53`) and `BenchBossStreamFunction`'s `DISCORD_TOKEN` (`infrastructure/template.yaml:73`). Both pipeline templates' `ParameterOverrides` then just pass the (non-sensitive) secret name instead of resolving it themselves.
  - **Does not fully close the exposure** — whatever value ends up in the Lambda's env var is still readable in plaintext via `lambda:GetFunctionConfiguration`/`GetFunction` to anyone with that IAM permission on the function, same as today. This fix only removes the CodePipeline-specific avenue on top of that pre-existing one; fully closing it would mean not using env vars for secrets at all (Lambda fetching from Secrets Manager at runtime instead).
  - **Breaks the manual deploy path if not handled**: `make deploy` (`Makefile:91-97`, README Part 6) passes `DiscordPublicKey`/`DiscordToken` as plain values from local `.env`, with no Secrets Manager involved — switching `template.yaml` to require `DiscordSecretName` would break this unless the template supports both shapes (e.g. `Fn::If`) or manual/local deploys are also required to have a Secrets Manager secret.

## Chores
- [X] Fix `make server` env vars (each Makefile line runs in a separate shell on Windows — vars don't persist)
