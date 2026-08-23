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

## Chores
- [X] Fix `make server` env vars (each Makefile line runs in a separate shell on Windows — vars don't persist)
- [ ] TEMP: verify PR Checks workflow — this line exists only to trigger a test PR and will not be merged
