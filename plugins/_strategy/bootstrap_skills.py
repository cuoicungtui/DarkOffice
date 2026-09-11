"""Install the versioned Strategy execution skill into user-owned runtime state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path


SKILL_NAME = "darkoffice-strategy-delivery"
LEGACY_SKILL_NAME = "darkoffice-strategy-execution"
SOURCE_ROOT = Path(__file__).resolve().parent / "skills" / SKILL_NAME


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _files(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)).replace("\\", "/"): _digest(path) for path in root.rglob("*") if path.is_file()}


def install(target_root: str | Path | None = None, *, force: bool = False) -> Path:
    """Install or upgrade only files unchanged since the prior bootstrap."""
    target_base = Path(target_root or os.environ.get("DARKOFFICE_SKILLS_ROOT", "usr/skills"))
    _retire_managed_legacy_skill(target_base)
    target = target_base / SKILL_NAME
    marker = target / ".bootstrap.json"
    source_files = _files(SOURCE_ROOT)
    prior: dict[str, str] = {}
    if marker.exists():
        prior = json.loads(marker.read_text(encoding="utf-8")).get("files", {})
    elif target.exists() and any(target.iterdir()) and not force:
        raise RuntimeError(f"{target} exists without a bootstrap marker; refusing to overwrite it")

    for relative, source_hash in source_files.items():
        destination = target / relative
        if destination.exists() and not force:
            previous_hash = prior.get(relative)
            if previous_hash is None or _digest(destination) != previous_hash:
                raise RuntimeError(f"{destination} was modified locally; rerun with --force to replace it")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((SOURCE_ROOT / relative).read_bytes())

    marker.write_text(json.dumps({"skill": SKILL_NAME, "version": "2.0.0", "files": source_files}, indent=2) + "\n", encoding="utf-8")
    return target


def _retire_managed_legacy_skill(target_base: Path) -> None:
    legacy = target_base / LEGACY_SKILL_NAME
    marker = legacy / ".bootstrap.json"
    if not marker.exists():
        return
    try:
        expected = json.loads(marker.read_text(encoding="utf-8")).get("files", {})
    except (OSError, json.JSONDecodeError):
        return
    if expected and all((legacy / relative).is_file() and _digest(legacy / relative) == digest for relative, digest in expected.items()):
        shutil.rmtree(legacy)


def main() -> None:
    parser = argparse.ArgumentParser(description="Install the DarkOffice Strategy delivery skill")
    parser.add_argument("--target-root", default=None)
    parser.add_argument("--force", action="store_true")
    arguments = parser.parse_args()
    print(install(arguments.target_root, force=arguments.force))


if __name__ == "__main__":
    main()
