"""Git ownership handoff in disposable local clones, never in a real HA repo."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "custom_components/smart_thermostat"


def git(root, *args):
    return subprocess.check_output([
        "git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
        "-c", "user.name=Offline PID fixture", "-c", "user.email=offline@example.invalid",
        "-C", str(root), *args,
    ], text=True, stderr=subprocess.PIPE).strip()


@pytest.fixture
def clones(tmp_path):
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    mac, ha = tmp_path / "workstation", tmp_path / "installation"
    git(tmp_path, "clone", str(origin), str(mac))
    shutil.copytree(ROOT / PREFIX, mac / PREFIX, ignore=shutil.ignore_patterns("__pycache__"))
    (mac / ".gitignore").write_text("__pycache__/\n")
    (mac / "configuration.yaml").write_text("# unchanged user config\n")
    git(mac, "add", ".")
    git(mac, "commit", "-m", "Original Git-owned patched PID")
    git(mac, "push", "origin", "main")
    git(tmp_path, "clone", str(origin), str(ha))
    return mac, ha


def detach(root):
    # Only the temporary installation clone. Never execute this on a real HA.
    (root / ".gitignore").write_text("__pycache__/\n/" + PREFIX + "/\n")
    git(root, "rm", "-r", "--cached", "--", PREFIX)
    git(root, "add", ".gitignore")
    git(root, "commit", "-m", "Hand PID ownership to Marketplace")
    git(root, "push", "origin", "main")


def test_installation_origin_handoff_preserves_files_and_future_updates(clones):
    mac, ha = clones
    path = ha / PREFIX / "climate.py"
    original = path.read_bytes()
    detach(ha)
    assert path.read_bytes() == original
    assert git(ha, "ls-files", "--", PREFIX) == ""
    git(mac, "pull", "--no-rebase", "--no-edit", "origin", "main")
    assert not (mac / PREFIX).exists()  # Expected for the non-serving clone.
    path.write_bytes(original + b"\n# local newer-release fixture\n")
    (mac / "notes.md").write_text("Unrelated next deploy\n")
    git(mac, "add", "notes.md")
    git(mac, "commit", "-m", "Unrelated change")
    git(mac, "push", "origin", "main")
    pre_pull = git(ha, "rev-parse", "HEAD")
    git(ha, "pull", "--no-rebase", "--no-edit", "origin", "main")
    # Simulate git-ha-ppens failed validation only after the handoff is complete.
    git(ha, "reset", "--hard", pre_pull)
    assert path.read_bytes() == original + b"\n# local newer-release fixture\n"
    assert git(ha, "status", "--porcelain") == ""
    assert (ha / "configuration.yaml").read_text() == "# unchanged user config\n"


def test_workstation_origin_detach_deletes_serving_files(clones):
    mac, ha = clones
    detach(mac)
    git(ha, "pull", "--no-rebase", "--no-edit", "origin", "main")
    assert not (ha / PREFIX).exists()  # Negative control; never recommend this route.


def test_unrelated_pending_edit_is_not_lost_by_detach(clones):
    mac, ha = clones
    (ha / "configuration.yaml").write_text("# unrelated pending user change\n")
    detach(ha)
    assert (ha / "configuration.yaml").read_text() == "# unrelated pending user change\n"
    assert git(ha, "status", "--porcelain").strip() == "M configuration.yaml"
    assert git(ha, "show", "HEAD:configuration.yaml") == "# unchanged user config"
