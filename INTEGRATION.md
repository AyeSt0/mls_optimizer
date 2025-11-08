# GitHub Automation Integration for `mls_optimizer`

## What’s included
- `.github/workflows/` CI + release-drafter
- Issue / PR templates, CODEOWNERS, Dependabot
- Pre-commit, Ruff/Black configs
- CONTRIBUTING, SECURITY

## How to integrate
1. Copy the contents of this bundle into your repo root (merge `.github/`).
2. Commit: `feat(ci): add GitHub automation`
3. (Optional) Enable Release Drafter in repo settings.
4. Push to GitHub. CI will run on PRs + pushes.

## Secrets to set (if needed)
- `OPENAI_API_KEY` and/or `DEEPSEEK_API_KEY` for any action that needs them.
- Or keep secrets local and avoid calling APIs in CI.
