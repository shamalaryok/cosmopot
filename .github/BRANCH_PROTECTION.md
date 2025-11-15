# Branch Protection Rules

This document outlines the recommended branch protection rules for this repository.

## Main Branch (`main`)

The `main` branch is the production-ready branch. All code in `main` should be deployable.

### Required Settings

- **Require a pull request before merging**: ✅
  - **Require approvals**: 2 reviewers minimum
  - **Dismiss stale pull request approvals when new commits are pushed**: ✅
  - **Require review from Code Owners**: ✅ (if CODEOWNERS file exists)

- **Require status checks to pass before merging**: ✅
  - **Require branches to be up to date before merging**: ✅
  - **Required status checks**:
    - `Lint Python Code`
    - `Type Check Python`
    - `Test Backend`
    - `Test Bot`
    - `Lint Frontend`
    - `Type Check Frontend`
    - `Test Frontend`
    - `Build Backend Image`
    - `Build Worker Image`
    - `Build Frontend Image`
    - `Validate PR Title`
    - `Validate Commit Messages`

- **Require conversation resolution before merging**: ✅

- **Require signed commits**: ✅ (recommended)

- **Require linear history**: ✅ (prevents merge commits, use squash or rebase)

- **Do not allow bypassing the above settings**: ✅

- **Restrict who can push to matching branches**: 
  - Only allow administrators and specific users/teams

### Additional Settings

- **Allow force pushes**: ❌
- **Allow deletions**: ❌

## Develop Branch (`develop`)

The `develop` branch is the integration branch for features.

### Required Settings

- **Require a pull request before merging**: ✅
  - **Require approvals**: 1 reviewer minimum
  - **Dismiss stale pull request approvals when new commits are pushed**: ✅

- **Require status checks to pass before merging**: ✅
  - **Require branches to be up to date before merging**: ✅
  - **Required status checks**: (same as main)

- **Require conversation resolution before merging**: ✅

### Additional Settings

- **Allow force pushes**: ❌
- **Allow deletions**: ❌

## Feature Branches (`feature/*`)

Feature branches are created from `develop` and merged back into `develop`.

### Naming Convention

- `feature/short-description` - New features
- `fix/issue-number-description` - Bug fixes
- `refactor/component-name` - Code refactoring
- `docs/topic` - Documentation updates
- `test/component-name` - Test additions/updates

### Required Settings

- No branch protection required, but must follow semantic commit conventions
- Must pass all CI checks before merging into `develop`
- Should be deleted after merging

## Release Branches (`release/*`)

Release branches are created from `develop` for preparing production releases.

### Naming Convention

- `release/v1.0.0` - Semantic version format

### Process

1. Create release branch from `develop`
2. Perform final testing and bug fixes
3. Update version numbers and documentation
4. Merge to `main` with a tag
5. Merge back to `develop` if any fixes were made

## Hotfix Branches (`hotfix/*`)

Hotfix branches are created from `main` for urgent production fixes.

### Naming Convention

- `hotfix/v1.0.1-description` - Patch version with description

### Process

1. Create hotfix branch from `main`
2. Fix the critical issue
3. Merge to `main` with a tag
4. Merge back to `develop`

## Setting Up Branch Protection

To configure these rules in GitHub:

1. Go to **Settings** → **Branches**
2. Click **Add rule** for each branch pattern
3. Configure the settings as outlined above
4. Save changes

### GitHub CLI Method

You can also configure branch protection using the GitHub CLI:

```bash
# Main branch
gh api repos/{owner}/{repo}/branches/main/protection \
  --method PUT \
  --field required_status_checks='{"strict":true,"contexts":["Lint Python Code","Type Check Python","Test Backend","Test Bot","Lint Frontend","Type Check Frontend","Test Frontend"]}' \
  --field enforce_admins=true \
  --field required_pull_request_reviews='{"required_approving_review_count":2,"dismiss_stale_reviews":true}' \
  --field restrictions=null

# Develop branch
gh api repos/{owner}/{repo}/branches/develop/protection \
  --method PUT \
  --field required_status_checks='{"strict":true,"contexts":["Lint Python Code","Type Check Python","Test Backend","Test Bot","Lint Frontend","Type Check Frontend","Test Frontend"]}' \
  --field enforce_admins=false \
  --field required_pull_request_reviews='{"required_approving_review_count":1,"dismiss_stale_reviews":true}' \
  --field restrictions=null
```

## Required Status Checks Reference

The following jobs must pass for a PR to be mergeable:

### Python/Backend
- `Lint Python Code` - Ruff and Black formatting
- `Type Check Python` - mypy type checking
- `Test Backend` - Backend unit/integration tests (>80% coverage)
- `Test Bot` - Bot unit/integration tests (>80% coverage)

### Frontend
- `Lint Frontend` - ESLint, Stylelint, Prettier
- `Type Check Frontend` - TypeScript/Vue type checking
- `Test Frontend` - Vitest unit tests (>80% coverage)

### Docker & Security
- `Build Backend Image` - Docker build and Trivy scan
- `Build Bot Image` - Docker build and Trivy scan (if applicable)
- `Build Worker Image` - Docker build and Trivy scan
- `Build Frontend Image` - Docker build and Trivy scan

### Semantic Commits
- `Validate PR Title` - PR title follows conventional commits
- `Validate Commit Messages` - All commits follow conventional commits

## Workflow Diagram

```
feature/* ─┐
           ├─→ develop ─→ release/* ─→ main (tag: v1.0.0)
fix/*    ──┘                          ↑
                                      │
                            hotfix/* ─┘
```

## Emergency Procedures

In case of emergency (production down, critical security issue):

1. Hotfix branches can be created from `main`
2. Administrators can approve their own PRs (but should get review ASAP)
3. Status checks still must pass
4. Document the emergency procedure in PR

## References

- [GitHub Branch Protection Documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/defining-the-mergeability-of-pull-requests/about-protected-branches)
- [Conventional Commits Specification](https://www.conventionalcommits.org/)
- [Semantic Versioning](https://semver.org/)
