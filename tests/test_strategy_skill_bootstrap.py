from pathlib import Path

import pytest

from plugins._strategy import bootstrap_skills


def test_bootstrap_installs_and_preserves_locally_modified_skill(tmp_path: Path) -> None:
    target = bootstrap_skills.install(tmp_path)

    assert (target / "SKILL.md").is_file()
    assert (target / ".bootstrap.json").is_file()

    (target / "SKILL.md").write_text("local edit", encoding="utf-8")
    with pytest.raises(RuntimeError, match="modified locally"):
        bootstrap_skills.install(tmp_path)


def test_bootstrap_force_replaces_modified_skill(tmp_path: Path) -> None:
    target = bootstrap_skills.install(tmp_path)
    (target / "SKILL.md").write_text("local edit", encoding="utf-8")

    bootstrap_skills.install(tmp_path, force=True)

    assert "Thực thi Chiến lược" in (target / "SKILL.md").read_text(encoding="utf-8")
