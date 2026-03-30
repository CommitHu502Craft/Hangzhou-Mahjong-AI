# CI

This document describes the current CI policy and the intended feedback loop for pull requests.

## Required Checks

The baseline checks for `main` are:

- `Python Tests`
- `Frontend Build`

These checks should stay green before merging user-facing changes.

## Current Workflow Behavior

- CI runs on pushes to `main`
- CI runs on pull requests targeting `main`
- older in-progress runs on the same ref are cancelled to reduce wasted runtime
- Python dependencies are cached through `setup-uv`
- frontend dependencies are cached through `setup-node`

## Why This Exists

The goal is to keep the first feedback loop short for normal documentation, backend, and frontend changes while still covering the project's two most visible surfaces:

- Python regression safety
- frontend build integrity

## Runtime Tracking

Use the GitHub Actions UI to monitor runtime changes over time:

1. open the `Actions` tab
2. compare recent `CI` workflow durations before and after workflow changes
3. watch for regressions in dependency install time or flaky reruns

## Flakiness Policy

- if a job fails intermittently, record the failure pattern before expanding the workflow
- prefer fixing deterministic setup problems before adding more jobs
- avoid adding heavy jobs to the required baseline until they are stable

## Follow-Up Candidates

- split optional heavy checks from required baseline checks
- record runtime snapshots in PR descriptions when touching CI
- promote only stable jobs to the required branch protection set

