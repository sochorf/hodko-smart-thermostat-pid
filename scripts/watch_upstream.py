"""Find upstream PID releases; preview by default, create issues only in Actions."""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

UPSTREAM = "ScratMan/HASmartThermostat"
TARGET = "sochorf/hodko-smart-thermostat-pid"
API = "https://api.github.com"
MAX_PAGES = 100
MAX_NEW_ISSUES = 5
VERSION = re.compile(r"v?([0-9]+)\.([0-9]+)\.([0-9]+)")
PRERELEASE = re.compile(r"v?[0-9]+\.[0-9]+\.[0-9]+-(?:alpha|beta|rc|dev)[0-9A-Za-z.-]*", re.I)


class WatchError(Exception):
    """An incomplete scan must never be interpreted as no update/no issue."""


def version(tag):
    match = VERSION.fullmatch(tag) if isinstance(tag, str) else None
    if not match:
        raise WatchError("Unsupported stable version format; review upstream tags")
    return tuple(int(part) for part in match.groups())


def canonical(tag):
    return ".".join(map(str, version(tag)))


def load_policy(path):
    policy = json.loads(path.read_text())
    if (policy["published_repository"] != TARGET
            or policy["upstream_repository"] != f"https://github.com/{UPSTREAM}"):
        raise WatchError("Unexpected repository in release policy")
    baseline = policy["upstream_tag"]
    version(baseline)
    # A fork-only revision must not accidentally move the upstream baseline.
    if policy["version"].split(".")[:3] != canonical(baseline).split("."):
        raise WatchError("Fork version and reviewed upstream baseline disagree")
    return baseline


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise WatchError("GitHub API redirect refused; review repository identity")


class GitHub:
    def __init__(self, token=""):
        self.token = token
        self.opener = build_opener(NoRedirect())

    def request(self, method, path, body=None):
        # No arbitrary endpoint, remote URL, or redirect can receive the token.
        allowed_get = (
            f"/repos/{UPSTREAM}/releases?per_page=100&page=",
            f"/repos/{TARGET}/issues?state=all&sort=created&direction=asc&per_page=100&page=",
        )
        valid_get = method == "GET" and any(
            path.startswith(prefix) and path[len(prefix):].isdigit()
            for prefix in allowed_get
        )
        valid_post = method == "POST" and path == f"/repos/{TARGET}/issues"
        if not (valid_get or valid_post):
            raise WatchError("API operation is outside the release/issue allowlist")
        headers = {"Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "hodko-pid-upstream-watch"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode() if body is not None else None
        try:
            with self.opener.open(Request(API + path, data=data, headers=headers,
                                          method=method), timeout=30) as response:
                expected = 201 if method == "POST" else 200
                if response.status != expected:
                    raise WatchError("Unexpected GitHub response status")
                return json.load(response)
        except HTTPError as error:
            # Never dump headers, token, or response bodies into logs.
            code = error.code
            error.close()
            raise WatchError(f"GitHub {method} failed: HTTP {code}; no automatic retry") from None
        except (URLError, TimeoutError, OSError, ValueError):
            # A POST timeout may have created the issue. Do NOT repeat the POST.
            raise WatchError(f"GitHub {method} transport/JSON failure; no automatic retry") from None


def scan(api, path):
    rows = []
    for page in range(1, MAX_PAGES + 1):
        separator = "&" if "?" in path else "?"
        batch = api.request("GET", f"{path}{separator}per_page=100&page={page}")
        if not isinstance(batch, list) or not all(isinstance(row, dict) for row in batch):
            raise WatchError("Invalid paginated API response")
        rows.extend(batch)
        if len(batch) < 100:
            return rows
    raise WatchError("Pagination bound reached; refusing an incomplete scan")


def candidates(releases, baseline):
    selected = {}
    for release in releases:
        if type(release.get("draft")) is not bool or type(release.get("prerelease")) is not bool:
            raise WatchError("Release flags missing or malformed")
        if release["draft"] or release["prerelease"]:
            continue
        tag = release.get("tag_name")
        # Historical upstream beta tags sometimes have prerelease=false.
        if isinstance(tag, str) and PRERELEASE.fullmatch(tag):
            continue
        key = version(tag)
        if key > version(baseline):
            # vX.Y.Z and X.Y.Z represent one version, irrespective of API order.
            selected[key] = min(tag, selected.get(key, tag))
    return [selected[key] for key in sorted(selected)]


def marker(tag):
    return f"<!-- hodko-pid-upstream:{UPSTREAM}:{canonical(tag)} -->"


def issue_title(tag):
    return f"Upstream PID {canonical(tag)}: review for Hodko fork"


def existing_issue(issues, tag):
    for issue in issues:
        if "pull_request" in issue:
            continue
        body = issue.get("body") or ""
        # Title fallback survives accidental removal of the marker; a changed
        # title is still recognized by the marker. Closed issues also count.
        if marker(tag) in body or issue.get("title") == issue_title(tag):
            return True
    return False


def issue_payload(tag, baseline):
    return {
        "title": issue_title(tag),
        "assignees": ["sochorf"],
        "body": f"""{marker(tag)}

New stable upstream PID release: **{canonical(tag)}**.
Reviewed upstream baseline in this fork: **{canonical(baseline)}**.

- [Release notes](https://github.com/{UPSTREAM}/releases/tag/{tag})
- [Compare with reviewed baseline](https://github.com/{UPSTREAM}/compare/{baseline}...{tag})

This is a review reminder, not approval to merge, release, or deploy.

- [ ] Review upstream changes, HA compatibility, and known issues.
- [ ] Preserve/reassess Hodko fixes for OFF intervals, target changes,
      repeated temperature reports, and OFF before stall fallback.
- [ ] Prepare a separate branch/PR; run PID and Marketplace regression tests.
- [ ] Review manifest/version, release policy, component/patch hashes and rollback.
- [ ] After approval, publish a separately tested fork release.
- [ ] Plan any HA update separately, preserving heating and DHW configuration.

If accepted, update `upstream_tag` and `upstream_commit` in `release-policy.json`
with the reviewed code. If skipped, close this issue with the reason.
Keep this issue (including its marker) so future runs do not create it again.
""",
    }


def run(api, baseline, *, apply=False):
    # Complete BOTH scans before any write. Never treat a partial/error result
    # as an empty list, and never use eventually indexed GitHub Search for dedup.
    tags = candidates(scan(api, f"/repos/{UPSTREAM}/releases"), baseline)
    issues = scan(api, f"/repos/{TARGET}/issues?state=all&sort=created&direction=asc")
    missing = [tag for tag in tags if not existing_issue(issues, tag)]
    created = []
    if apply:
        for tag in missing[:MAX_NEW_ISSUES]:
            if created:
                time.sleep(1)  # Pace writes when catching up several releases.
            result = api.request("POST", f"/repos/{TARGET}/issues", issue_payload(tag, baseline))
            if not isinstance(result, dict) or type(result.get("number")) is not int:
                raise WatchError("Issue response incomplete; inspect next scan before retrying")
            created.append(result["number"])
    return {"baseline": canonical(baseline), "mode": "apply" if apply else "preview",
            "newer_versions": len(tags), "already_tracked": len(tags) - len(missing),
            "missing_versions": [canonical(tag) for tag in missing],
            "created_issues": created, "remaining": max(0, len(missing) - len(created))}


def require_actions(env):
    if not (env.get("GITHUB_ACTIONS") == "true"
            and env.get("GITHUB_REPOSITORY") == TARGET
            and env.get("GITHUB_REF") == "refs/heads/hodko"
            and env.get("GITHUB_EVENT_NAME") in {"schedule", "workflow_dispatch"}
            and env.get("GH_TOKEN")):
        raise WatchError("Issue creation requires the authorized fork/default-branch Actions context")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Create issues (Actions only)")
    args = parser.parse_args()
    try:
        if args.apply:
            require_actions(os.environ)
        baseline = load_policy(Path(__file__).resolve().parents[1] / "release-policy.json")
        result = run(GitHub(os.environ.get("GH_TOKEN", "")), baseline, apply=args.apply)
        print(json.dumps(result, sort_keys=True))
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a") as stream:
                stream.write("## Upstream PID release check\n\n```json\n"
                             + json.dumps(result, indent=2) + "\n```\n")
    except (WatchError, KeyError, ValueError, OSError) as error:
        # Exception text is deliberately bounded; no API data or credentials.
        print(f"Upstream check failed: {error if isinstance(error, WatchError) else type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
