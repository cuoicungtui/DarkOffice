---
name: darkoffice-development
description: Repository-local development workflow for DarkOffice. Use when changing this fork, adding project-specific skills, creating branches or release tags, or preparing a GitHub Actions deployment.
---

# DarkOffice development

Use this skill for work that belongs to the current DarkOffice repository. The root `AGENTS.md` remains the upstream Agent Zero DOX and is the source of upstream-compatible engineering rules.

## Skill boundary

- Repository-local development skills live under `.agents/skills/`.
- Do not place DarkOffice-only guidance in the upstream bundled `skills/` tree or in system-level skill directories.
- Keep the root `AGENTS.md` byte-for-byte aligned with the upstream Agent Zero source when upstream changes are intentionally synchronized.
- Preserve upstream imports, package names, protocol identifiers, URLs, and legacy data compatibility unless the task explicitly asks for a product-facing change.

## Git and release flow

1. Start from a clean checkout and inspect `git status --short --branch`, remotes, branches, and tags.
2. Integrate ongoing work on `develop`; branch feature or fix work from `develop`.
3. Run the focused tests for the change, then commit an atomic change with a descriptive message.
4. Push the source branch and wait for its GitHub Actions checks.
5. Cut an annotated semantic-version release tag from the tested commit, push that tag, and verify the remote ref.
6. For a server deploy, dispatch `Deploy DarkOffice Server` with the exact branch or tag, using the existing `agent0ai/agent-zero:latest` pull-mount image, and verify the workflow smoke test.

Never force-push shared branches or move an existing release tag. Keep secrets and generated runtime state out of commits.

## Validation

- Run `git diff --check`.
- Run the focused pytest command required by the changed area.
- For workflow or Docker changes, validate `docker/run/docker-compose.darkoffice.yml` and run the runtime-image tests required by `.github/AGENTS.md`.
- After pushing, verify the branch/tag with `git ls-remote` and inspect the GitHub Actions run result.
