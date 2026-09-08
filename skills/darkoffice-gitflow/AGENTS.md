# DarkOffice Gitflow Skill DOX

## Purpose

- Own the DarkOffice GitHub, Gitflow, Docker deploy, release, and rollback workflow skill.
- Keep the project-specific workflow aligned with Agent Zero fork rules and deployment safety checks.

## Ownership

- `SKILL.md` owns the reusable agent-facing workflow for DarkOffice git, GitHub Actions, Docker image handling, and rollback planning.

## Local Contracts

- Preserve the mandatory DarkOffice fork of Agent Zero repository verification before any change.
- Keep Docker guidance pull-first and base-image aware: do not rebuild `docker/base` unless base files change.
- Do not include server credentials, private IPs, tokens, or real passwords in the skill.

## Work Guidance

- Update this skill when branch policy, CI/CD workflow names, deploy target conventions, image registry choice, or rollback procedure changes.
- Keep commands operational and avoid assuming a fixed local or server port.

## Verification

- Manually read `SKILL.md` after edits for stale paths, hardcoded secrets, and unsupported branch rules.
- Run skill runtime tests when changing skill loader assumptions.

## Child DOX Index

No child DOX files.
