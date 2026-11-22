"""Offline release integrity and optional publication preflight. No writes."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check(root, *, publication=False, tag=None):
    policy = json.loads((root / "release-policy.json").read_text())
    component = root / "custom_components/smart_thermostat"
    manifest = json.loads((component / "manifest.json").read_text())
    require(manifest["domain"] == "smart_thermostat", "Domain changed")
    require(manifest["version"] == policy["version"], "Version differs from policy")
    metadata = {"version", "documentation", "issue_tracker", "codeowners"}
    require({k: v for k, v in manifest.items() if k not in metadata} == {
        k: v for k, v in policy["original_manifest"].items() if k not in metadata
    }, "Unreviewed manifest behavior/dependency change")
    require(re.fullmatch(r"\d{4}\.\d{1,2}\.\d+\.\d+", manifest["version"]), "Invalid fork version")
    if tag is not None:
        require(tag == manifest["version"], "Tag must match manifest")
    expected = policy["component_hashes_before_manifest_change"]
    actual = {}
    for path in component.rglob("*"):
        require(not path.is_symlink(), "Component symlinks are not allowed")
        if path.is_file() and "__pycache__" not in path.parts:
            actual[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    require(set(actual) == set(expected), "Missing/extra component files")
    for name, sha in expected.items():
        if not name.endswith("/manifest.json"):
            require(actual[name] == sha, f"Unreviewed control change: {name}")
    require(hashlib.sha256((root / "hodko/bar-lifecycle.patch").read_bytes()).hexdigest() == policy["patch_sha256"], "Patch changed")
    require(json.loads((root / "hacs.json").read_text())["homeassistant"] == "2026.11.2", "Minimum HA differs")
    for name in policy["regression_files"]:
        require((root / "tests" / name).is_file(), f"Missing regression: {name}")
    for name, sha in policy["regression_hashes"].items():
        require(hashlib.sha256((root / "tests" / name).read_bytes()).hexdigest() == sha, f"Changed regression: {name}")
    require((root / "LICENSE.MD").is_file(), "License missing")
    if publication:
        repo = policy["published_repository"]
        require(isinstance(repo, str) and re.fullmatch(r"[A-Za-z0-9-]+/hodko-smart-thermostat-pid", repo), "Public owner/repository has not been chosen")
        url = "https://github.com/" + repo
        require(manifest["documentation"] == url, "Documentation must point to fork")
        require(manifest["issue_tracker"] == url + "/issues", "Issues must point to fork")
    return policy


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--for-publication", action="store_true")
    parser.add_argument("--tag")
    args = parser.parse_args()
    result = check(Path(__file__).resolve().parents[1], publication=args.for_publication, tag=args.tag)
    print(f"Verified {result['version']}: unchanged reviewed control bytes; publication={args.for_publication}")
