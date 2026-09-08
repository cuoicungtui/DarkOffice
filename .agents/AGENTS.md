# DarkOffice Development DOX

## Purpose

- Keep repository-specific development guidance separate from the upstream Agent Zero root `AGENTS.md`.
- Define how DarkOffice changes, repository-local skills, branches, releases, and deployment handoffs are maintained.

## Ownership

- `.agents/skills/` contains skills written for this DarkOffice development workspace.
- The upstream-compatible application source remains in the tracked project directories and keeps its existing Agent Zero compatibility contracts.

## Local Contracts

- Load development skills from the repository path `.agents/skills/`; do not add current-project guidance to the bundled/system `skills/` locations.
- Keep `AGENTS.md` at the repository root aligned with the upstream Agent Zero source. Put DarkOffice-only development guidance here and in `.agents/skills/`.
- Preserve upstream package names, protocol identifiers, attribution, and compatibility data unless a task explicitly requires a product-facing change.
- Keep secrets, `.env` files, runtime state, and generated data out of commits.
- Use `develop` for integration work. Create feature/fix branches from `develop`, and cut release tags from the tested release commit.
- A server deployment is complete only after the source is committed, pushed, and the corresponding GitHub Actions workflow succeeds.
- Use the existing runtime image `agent0ai/agent-zero:latest` with the pull-mount deployment workflow; do not build a replacement image unless explicitly requested.

## Work Guidance

- Read the closest applicable `AGENTS.md` before editing a tracked subtree.
- Add or update a repository skill under `.agents/skills/<skill-name>/SKILL.md` when the guidance is specific to current DarkOffice development.
- Keep release tags immutable and use annotated semantic-version tags. Verify the remote branch/tag and workflow run after pushing.
- Run focused tests for changed behavior and `git diff --check` before committing.

## Verification

- Confirm `git status --short --branch` is clean after the release operation.
- Confirm `develop` and the release tag resolve to the intended commit on `origin`.
- Confirm the relevant GitHub Actions run completes successfully before calling a deployment or release complete.

## Child DOX Index

| Child | Scope |
| --- | --- |
| [skills/](skills/) | Repository-local skills for current DarkOffice development. |
