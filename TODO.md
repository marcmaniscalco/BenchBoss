# BenchBoss TODO

## Bugs

## Features
- [ ] Support scheduling multiple upcoming events (currently only posts the next one)
- [ ] Edit / reschedule an existing event
- [ ] Reminder notifications before event start

## Infrastructure
- [ ] Add CI pipeline (lint, test, deploy)
- [ ] Environment variable validation on startup

## Chores
- [X] Fix `make server` env vars (each Makefile line runs in a separate shell on Windows — vars don't persist)