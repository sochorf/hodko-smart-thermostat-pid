"""Run this fork's pinned offline tests, not the user's HA environment."""
from importlib.metadata import requires, version
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from packaging.requirements import Requirement
from check_release import check

root = Path(__file__).resolve().parents[1]
policy = check(root)
if version("homeassistant") != "2026.11.2" or version("pytest-homeassistant") != "2026.11.1":
    raise SystemExit("Use the reviewed isolated HA 2026.11.2 test environment")
for entry in requires("homeassistant") or []:
    dep = Requirement(entry)
    if dep.marker and not dep.marker.evaluate({"extra": ""}):
        continue
    if version(dep.name) not in dep.specifier:
        raise SystemExit(f"HA dependency mismatch: {dep.name}")
tests = ["tests/" + n for n in policy["regression_files"]]
tests += ["tests/test_marketplace.py", "tests/test_git_handoff.py"]
with tempfile.TemporaryDirectory(prefix="pid-tests-home-") as temp_home:
    env = {k: os.environ[k] for k in ("PATH", "LANG", "TMPDIR", "PYTHONPATH") if k in os.environ}
    env.update(HOME=temp_home, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([
        sys.executable, "-m", "pytest", "-q", "--disable-socket", "--allow-unix-socket",
        "--timeout=30", "-p", "no:cacheprovider", *tests,
    ], cwd=root, env=env)
raise SystemExit(result.returncode)
