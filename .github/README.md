# GitHub Actions CI/CD Pipeline

This directory contains the GitHub Actions workflows that power our continuous integration and deployment processes.

## 📋 Workflows Overview

### 🔍 CI Workflow (`ci.yml`)

**Triggers:** Pull requests and pushes to `main` and `develop` branches

Runs comprehensive quality checks across the entire codebase:

#### Python Jobs
- **Lint Python Code**: Ruff linting + Black formatting
- **Type Check Python**: mypy static type analysis
- **Test Backend**: Backend tests with PostgreSQL + Redis (>80% coverage required)
- **Test Bot**: Bot tests with Redis (>80% coverage required)

#### Frontend Jobs
- **Lint Frontend**: ESLint + Stylelint + Prettier
- **Type Check Frontend**: TypeScript/Vue type checking
- **Test Frontend**: Vitest unit tests (>80% coverage required)

#### Coverage
- Combined coverage report aggregating all test results
- Uploads to Codecov
- Fails if any component is below 80% coverage

### 🐳 Docker Build & Security (`docker.yml`)

**Triggers:** PRs, pushes to main/develop, version tags, manual dispatch

Builds and scans all container images:

- **Backend Image**: FastAPI application
- **Bot Image**: Telegram bot (aiogram)
- **Worker Image**: Celery worker
- **Frontend Image**: Vue.js SPA

Features:
- Multi-stage builds with dependency caching
- GitHub Actions cache for faster builds
- Automatic push to GitHub Container Registry (non-PR events)
- Trivy vulnerability scanning (CRITICAL + HIGH severities)
- SARIF reports uploaded to GitHub Security tab

### 🔖 Semantic PR Validation (`semantic-pr.yml`)

**Triggers:** PR open, edit, synchronize, reopen

Enforces [Conventional Commits](https://www.conventionalcommits.org/):

- Validates PR title format: `<type>[optional scope]: <description>`
- Validates all commit messages in the PR
- Accepted types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`
- Accepted scopes: `backend`, `bot`, `frontend`, `worker`, `ci`, `deps`, `api`, `db`, `auth`, `docs`

Examples:
```
✅ feat(backend): add user authentication
✅ fix(api): resolve race condition in websocket handler
✅ docs: update deployment guide
✅ chore(deps): upgrade fastapi to 0.104.1
❌ Added user authentication (missing type prefix)
❌ FEAT: new feature (type must be lowercase)
```

### 🚀 Deployment Workflow (`deploy.yml`)

**Triggers:** Manual workflow dispatch only

Implements safe deployment process with quality gates:

**Inputs:**
- `environment`: staging or production
- `tag`: Release tag to deploy (e.g., v1.0.0)
- `skip_tests`: Skip pre-deployment tests (default: false)

**Process:**
1. Validate tag exists and follows semantic versioning
2. Run pre-deployment smoke tests (unless skipped)
3. Verify all container images exist and are pullable
4. Run Trivy security scans on images
5. Deploy to selected environment
6. Run post-deployment health checks
7. Automatic rollback on failure

**Environment Protection:**
- Staging: No additional approvals required
- Production: Requires manual approval (configure in repository settings)

### 📦 Release Workflow (`release.yml`)

**Triggers:** Pushes to version tags (`v*`), manual dispatch

Automates release creation:

- Generates changelog from commit messages
- Creates GitHub release with notes
- Includes Docker image pull instructions
- Optional workflow dispatch to bump version in `pyproject.toml`

## 🔐 Branch Protection Rules

See [`BRANCH_PROTECTION.md`](./BRANCH_PROTECTION.md) for recommended settings.

### Required Status Checks

All PRs to `main` and `develop` must pass:

**Quality Gates:**
- ✅ Lint Python Code
- ✅ Type Check Python
- ✅ Test Backend (>80% coverage)
- ✅ Test Bot (>80% coverage)
- ✅ Lint Frontend
- ✅ Type Check Frontend
- ✅ Test Frontend (>80% coverage)

**Container Builds:**
- ✅ Build Backend Image
- ✅ Build Worker Image
- ✅ Build Frontend Image
- ✅ Build Bot Image (if Dockerfile exists)

**Semantic Validation:**
- ✅ Validate PR Title
- ✅ Validate Commit Messages

## 🎯 Pull Request Template

Use the [PR template](./pull_request_template.md) for consistent PR descriptions.

## 👥 Code Owners

The [`CODEOWNERS`](./CODEOWNERS) file defines automatic review assignments:

- Backend: `@backend-team`
- Bot: `@bot-team`
- Frontend: `@frontend-team`
- DevOps/CI: `@devops-team`
- Everything else: `@team-leads`

## 📊 Monitoring & Reporting

### Coverage Reports
- Backend/Bot: XML + HTML reports uploaded as artifacts
- Frontend: JSON + HTML reports uploaded as artifacts
- Combined summary in GitHub Actions job output

### Security Scanning
- Trivy SARIF reports in **Security** → **Code scanning** tab
- Scans run on every image build
- Configured for CRITICAL and HIGH severities

### Container Registry
Images are pushed to GitHub Container Registry:
```bash
ghcr.io/{owner}/{repo}/backend:tag
ghcr.io/{owner}/{repo}/bot:tag
ghcr.io/{owner}/{repo}/worker:tag
ghcr.io/{owner}/{repo}/frontend:tag
```

## 🚦 Getting Started

### For Developers

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/my-new-feature
   ```

2. **Make commits following Conventional Commits:**
   ```bash
   git commit -m "feat(backend): add email verification"
   ```

3. **Push and create a PR:**
   ```bash
   git push origin feature/my-new-feature
   ```

4. **Ensure all checks pass:**
   - Fix any linting/formatting issues
   - Add tests to maintain >80% coverage
   - Ensure PR title follows semantic format

### For Maintainers

1. **Review PR** ensuring all checks are green
2. **Merge to develop** for integration testing
3. **Create release** when ready to deploy:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
4. **Deploy to staging** via workflow dispatch
5. **Verify in staging** environment
6. **Deploy to production** via workflow dispatch

## 🔧 Local Development

Run checks locally before pushing:

```bash
# Python linting and formatting
ruff check apps/backend apps/bot src tests
ruff format apps/backend apps/bot src tests
black --check apps/backend apps/bot src tests

# Python type checking
mypy apps/backend/src apps/bot/src src

# Python tests
pytest apps/backend/tests --cov=backend --cov-fail-under=80
pytest apps/bot/tests --cov=bot --cov-fail-under=80

# Frontend checks
cd frontend/spa
pnpm lint
pnpm typecheck
pnpm test:coverage

# Docker builds
docker build -f apps/backend/Dockerfile -t backend:local .
docker build -f apps/bot/Dockerfile -t bot:local .
docker build -f worker/Dockerfile -t worker:local .
docker build -f frontend/Dockerfile -t frontend:local .

# Security scanning
trivy image backend:local
```

## 🐛 Troubleshooting

### CI Failures

**Linting errors:**
```bash
# Auto-fix with ruff
ruff check --fix apps/backend apps/bot src tests

# Auto-format with black
black apps/backend apps/bot src tests

# Frontend auto-fix
cd frontend/spa && pnpm lint --fix && pnpm format
```

**Test failures:**
- Check logs in GitHub Actions for specific test failures
- Run tests locally to debug
- Ensure all required services are running (postgres, redis)

**Coverage below threshold:**
- Add tests for uncovered code paths
- Run `pytest --cov-report=html` to see coverage report locally

**Semantic commit validation:**
- Update PR title to follow format: `type(scope): description`
- Amend commit messages if needed

### Docker Build Failures

**Context issues:**
- Ensure Dockerfiles use correct COPY paths
- Build from repository root: `docker build -f apps/backend/Dockerfile .`

**Dependency issues:**
- Update `pyproject.toml` or `package.json`
- Clear cache: `docker buildx prune -af`

### Deployment Issues

**Tag doesn't exist:**
- Ensure tag is pushed: `git push origin v1.0.0`

**Image pull failures:**
- Verify images were pushed to registry
- Check `docker.yml` workflow ran successfully

## 📚 Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Conventional Commits Specification](https://www.conventionalcommits.org/)
- [Semantic Versioning](https://semver.org/)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Trivy Documentation](https://aquasecurity.github.io/trivy/)

## 🤝 Contributing

Before submitting a PR:

1. Read this document
2. Follow conventional commit format
3. Ensure all tests pass locally
4. Maintain >80% code coverage
5. Update documentation if needed

## 📝 License

See [LICENSE](../LICENSE) for details.
