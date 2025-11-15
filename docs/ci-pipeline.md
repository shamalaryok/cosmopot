# Continuous Integration and Delivery Playbook

This document describes the CI/CD workflows configured in this repository.

## Overview

The pipeline is powered by GitHub Actions and consists of the following workflows:

- **CI (`.github/workflows/ci.yml`)**: Runs linting, type checking, and automated tests for backend, bot, and frontend code with coverage enforced at >80%.
- **Task Runner (`.github/workflows/task-runner.yml`)**: Provides a self-service workflow that provisions the task runner VM and executes the full Python and frontend quality gate suite on demand.
- **Docker Build & Security Scan (`.github/workflows/docker.yml`)**: Builds container images, caches build artifacts, and runs Trivy vulnerability scans.
- **Semantic PR (`.github/workflows/semantic-pr.yml`)**: Enforces Conventional Commit semantics on pull request titles and commit messages.
- **Release (`.github/workflows/release.yml`)**: Creates tagged releases and generates changelogs. Provides an optional workflow dispatch to bump versions.
- **Deploy (`.github/workflows/deploy.yml`)**: Implements manual deployment gates for staging and production tied to release tags.

## CI Workflow Details

### Python

- `Lint Python Code`: Runs Ruff linting and Black formatting checks.
- `Type Check Python`: Runs mypy with strict settings.
- `Test Backend`: Executes backend pytest suite with PostgreSQL and Redis services, generating coverage reports.
- `Test Bot`: Executes bot pytest suite (Redis-backed), generating coverage reports.

### Frontend

- `Lint Frontend`: Runs ESLint, Stylelint, and Prettier checks using pnpm 8.15.8 with cached dependencies.
- `Type Check Frontend`: Runs TypeScript/Vue type checks via `pnpm typecheck`.
- `Test Frontend`: Runs Vitest with coverage enforcement (>80%).

### Coverage Reporting

Coverage artifacts are uploaded for backend, bot, and frontend components. The combined coverage summary is appended to the GitHub Actions job summary.

## Task Runner Workflow

The Task Runner workflow (`.github/workflows/task-runner.yml`) is triggered via `workflow_dispatch` and provides a self-service environment for contributors and maintainers to execute the same quality gates as CI in an isolated VM.

### Features

- **Manual Trigger**: Maintainers can trigger the Task Runner manually from the GitHub Actions tab by selecting the "Task Runner" workflow and clicking "Run workflow".
- **Customizable**: Optionally specify Python and Node.js versions via workflow inputs (defaults to Python 3.11 and Node.js 20).
- **Comprehensive Validation**: Runs the full validation matrix identical to the CI workflow:
  - Python linting (Ruff, Black)
  - Python type checking (mypy)
  - Backend tests with PostgreSQL and Redis services
  - Bot tests with Redis
  - Frontend linting (ESLint, Stylelint, Prettier)
  - Frontend type checking (TypeScript/Vue)
  - Frontend tests (Vitest)
- **Bootstrap Script**: Uses `scripts/task_runner_setup.sh` to install backend and frontend dependencies efficiently with caching.
- **Artifacts**: Produces coverage artifacts for backend, bot, and frontend code, retained for 7 days.

### Triggering the Task Runner

1. Navigate to the **Actions** tab in the GitHub repository.
2. Select the **Task Runner** workflow from the left sidebar.
3. Click **Run workflow** on the right.
4. (Optional) Customize Python/Node versions or leave defaults.
5. Click **Run workflow** to launch the VM.

### Interpreting Results

- **Logs**: View detailed logs for each step (lint, type check, test) under the workflow run page.
- **Artifacts**: Coverage reports and HTML summaries are available in the *Artifacts* section at the bottom of the workflow run page. Download them to review line coverage.
- **Summary**: A summary is displayed in the *Summary* tab showing which artifacts were produced.

### Use Cases

- **Pre-Commit Review**: Before opening a pull request, maintainers can run the Task Runner to validate changes against the full test suite.
- **Debugging CI Failures**: If CI fails on a specific Python or Node version, contributors can reproduce the issue using workflow inputs.
- **Documentation Testing**: Verify that instructions in the README remain accurate by executing them in a fresh VM.

## Docker and Security

- Builds backend, bot (if Dockerfile exists), worker, and frontend images using Buildx with GitHub Actions cache storage (`type=gha`).
- Pushes images to GitHub Container Registry on non-PR events.
- Runs Trivy scans on each image and uploads SARIF reports to GitHub Security tab.

## Semantic Commits

- Validates PR titles using `amannn/action-semantic-pull-request`.
- Validates commit messages using a custom Git script that enforces Conventional Commits format.
- Produces a summary in the PR checks for easy visibility.

## Release Management

- Automatically generates changelog entries based on commit history between tags.
- Publishes GitHub releases with instructions for pulling Docker images.
- Optional workflow dispatch to bump versions and tag releases.

## Deployment Process

- Manual workflow dispatch that requires selecting environment (staging/production) and release tag.
- Validates that release tags exist and follow semantic versioning.
- Optionally runs pre-deployment smoke tests.
- Pulls container images, runs Trivy scans, and simulates deployment steps (placeholder commands to be replaced with real deployment automation).
- Provides rollback and notification steps.

## Branch Policies

Refer to [`.github/BRANCH_PROTECTION.md`](../.github/BRANCH_PROTECTION.md) for recommended branch protection and naming rules.

## Required Secrets

The workflows assume the following GitHub Secrets are available:

- `GITHUB_TOKEN` (provided automatically by GitHub Actions)
- `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` (optional if pushing to Docker Hub)

## Local Development

- Use `pre-commit run --all-files` to mirror linting and test checks locally.
- Use `make` targets from `Makefile` for Docker-based workflows.
- Frontend SPA requires pnpm 8.15.8. The `packageManager` field in `frontend/spa/package.json` pins the version to ensure consistency between local development and CI.

## Troubleshooting

- **Missing Coverage Summary**: Ensure tests generate coverage artifacts (`coverage-*` files in backend/bot and `coverage/` directory in frontend).
- **Semantic Check Failures**: Update PR titles and commit messages to match Conventional Commit format.
- **Docker Build Failures**: Confirm Dockerfiles exist and build locally with `docker build`.
- **Trivy Alerts**: Review SARIF reports in the Security tab and patch vulnerabilities promptly.

## Future Enhancements

- Integrate automated database migrations during deployments.
- Add dynamic application security testing (DAST) stage.
- Push release notes to external communication channels (Slack, Teams).
