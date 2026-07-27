# Gauntlet — the runner the checks hang off.
#
# Before this file, eval/check.sh existed but nothing ever fired it: no CI, no hook, no
# target. A gate no automation runs is a gate that reports PASS the day it stops being true.
#
#   make check         everything deterministic (no LLM, no network, no quota) — the gate
#   make eval-live     the real scored review (needs codex + quota) — opt-in
#
.DEFAULT_GOAL := check
SHELL := /usr/bin/env bash

.PHONY: check routing-lint contract-check qc-selftest preflight-selftest launcher-smoke \
        score-selftest eval-live install hooks help

## check: full deterministic gate — structural sync, routing contract, all behavioral tiers
check:
	@bash eval/check.sh

## routing-lint: report every stale model name against config/routing.env (file:line)
routing-lint:
	@bash scripts/routing_lint.sh

## contract-check: verify the external codex launcher still honors Gauntlet's env contract
contract-check:
	@bash scripts/run_review.sh --contract-check

## qc-selftest: Stage-2 QC gate behavior (score parsing, ticker echo, table rows, stubs)
qc-selftest:
	@bash eval/qc_selftest.sh

## preflight-selftest: codex preflight outcome mapping (healthy / quota-limited / dead)
preflight-selftest:
	@bash eval/preflight_selftest.sh

## launcher-smoke: external vs gauntlet launcher artifact equivalence + contract drift
launcher-smoke:
	@bash eval/launcher_smoke.sh

## score-selftest: offline reviewer-scoring regression harness (canned reviews)
score-selftest:
	@bash eval/score_selftest.sh

## eval-live: feed the planted-fraud fixture through a REAL review and score it (quota-heavy)
eval-live:
	@echo "This spends one full codex review call against your plan limits."
	@bash eval/live_review.sh

## install: install gauntlet + companion skills into the Claude (and codex) skill trees
install:
	@bash install.sh

## hooks: point git at .githooks so `make check` runs before every commit
hooks:
	@git config core.hooksPath .githooks
	@echo "git hooks enabled: .githooks (pre-commit runs 'make check')"

## help: list targets
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## /  /'
