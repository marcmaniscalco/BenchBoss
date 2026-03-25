# BenchBoss TODO

## Bugs
- [ ] Commands button not sending help DM to users

## Features
- [ ] Support scheduling multiple upcoming events (currently only posts the next one)
- [ ] Edit / reschedule an existing event
- [ ] Reminder notifications before event start

## Infrastructure
- [ ] Add CI pipeline (lint, test, deploy)
- [ ] Environment variable validation on startup

## Chores
- [ ] Fix `make server` env vars (each Makefile line runs in a separate shell on Windows — vars don't persist)