"""Offline API simulation. No GitHub requests, HA imports, or device access."""

import copy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import watch_upstream as watch


def release(tag, **kwargs):
    return dict(tag_name=tag, draft=False, prerelease=False, **kwargs)


def tracked(tag, **kwargs):
    return dict(number=1, title="A manually renamed issue", body=watch.marker(tag), **kwargs)


class API:
    def __init__(self, releases=(), issues=()):
        self.releases = list(releases)
        self.issues = list(issues)
        self.calls = []
        self.fail_page = None
        self.lose_post_response = False

    @property
    def writes(self):
        return [call for call in self.calls if call[0] != "GET"]

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "POST":
            issue = dict(body, number=len(self.issues) + 1, state="open")
            self.issues.append(issue)
            if self.lose_post_response:
                raise watch.WatchError("POST response lost after server creation")
            return copy.deepcopy(issue)
        parsed = urlparse(path)
        query = parse_qs(parsed.query)
        page = int(query["page"][0])
        if self.fail_page == (parsed.path, page):
            raise watch.WatchError("Incomplete API scan")
        rows = self.releases if parsed.path.endswith("/releases") else self.issues
        return copy.deepcopy(rows[(page - 1) * 100:page * 100])


class WatchTests(unittest.TestCase):
    def setUp(self):
        blocker = patch("socket.socket", side_effect=AssertionError("Network forbidden in offline tests"))
        blocker.start()
        self.addCleanup(blocker.stop)
        sleep = patch.object(watch.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def test_current_baseline_produces_no_issue(self):
        api = API([release("2026.11.2"), release("2026.10.2")])
        result = watch.run(api, "2026.11.2", apply=True)
        self.assertEqual(result["newer_versions"], 0)
        self.assertFalse(api.writes)

    def test_numeric_order_aliases_and_all_missed_versions(self):
        rows = [release(tag) for tag in ("2027.1.0", "v2026.11.3", "2026.11.10", "2026.11.3")]
        self.assertEqual(watch.candidates(rows, "2026.11.2"), ["2026.11.3", "2026.11.10", "2027.1.0"])

    def test_prerelease_and_draft_are_never_announced(self):
        rows = [dict(release("2099.1.0"), prerelease=True),
                dict(release("2099.2.0"), draft=True),
                release("2021.11.5-beta1"), release("2099.1.0-rc1")]
        self.assertEqual(watch.candidates(rows, "2026.11.2"), [])

    def test_unsupported_stable_or_bad_schema_stops_before_writes(self):
        for row in [release("$(unsafe)"), release("2027.1.0.1"), {},
                    dict(release("2027.1.0"), prerelease="false")]:
            with self.subTest(row=row):
                api = API([release("2026.11.3"), row])
                with self.assertRaises(watch.WatchError):
                    watch.run(api, "2026.11.2", apply=True)
                self.assertFalse(api.writes)

    def test_closed_open_and_renamed_issues_all_deduplicate(self):
        for state in ["open", "closed"]:
            with self.subTest(state=state):
                api = API([release("v2026.11.3")], [tracked("2026.11.3", state=state)])
                self.assertEqual(watch.run(api, "2026.11.2", apply=True)["already_tracked"], 1)
                self.assertFalse(api.writes)

    def test_title_survives_removed_marker_but_pull_request_does_not_count(self):
        issue = dict(number=1, title=watch.issue_title("2026.11.3"), body=None)
        self.assertTrue(watch.existing_issue([issue], "2026.11.3"))
        issue["pull_request"] = {}
        self.assertFalse(watch.existing_issue([issue], "2026.11.3"))

    def test_preview_never_posts(self):
        api = API([release("2026.11.3")])
        result = watch.run(api, "2026.11.2")
        self.assertEqual(result["missing_versions"], ["2026.11.3"])
        self.assertFalse(api.writes)

    def test_two_runs_create_exactly_one_issue_and_assign_owner(self):
        api = API([release("2026.11.3")])
        watch.run(api, "2026.11.2", apply=True)
        watch.run(api, "2026.11.2", apply=True)
        self.assertEqual(len(api.writes), 1)
        payload = api.writes[0][2]
        self.assertEqual(payload["assignees"], ["sochorf"])
        self.assertIn("2026.11.2...2026.11.3", payload["body"])
        self.assertIn("not approval to merge", payload["body"])

    def test_release_notes_are_not_copied_or_evaluated(self):
        api = API([release("2026.11.3", body="@everyone $(do-bad-things)", html_url="https://evil.invalid")])
        watch.run(api, "2026.11.2", apply=True)
        body = api.writes[0][2]["body"]
        self.assertNotIn("evil.invalid", body)
        self.assertNotIn("@everyone", body)
        self.assertNotIn("do-bad-things", body)

    def test_pagination_covers_late_release_and_closed_issue(self):
        rows = [release("2026.11.2") for _ in range(100)] + [release("2026.11.3")]
        issues = [dict(number=i, title="unrelated", body="") for i in range(100)]
        api = API(rows, issues + [tracked("2026.11.3", state="closed")])
        result = watch.run(api, "2026.11.2", apply=True)
        self.assertEqual(result["already_tracked"], 1)
        self.assertEqual(len(api.calls), 4)
        self.assertFalse(api.writes)
        self.assertTrue(all("state=all" in path for _, path, _ in api.calls if "/issues?" in path))

    def test_partial_issue_scan_never_creates_duplicates(self):
        api = API([release("2026.11.3")], [dict(body="") for _ in range(100)])
        api.fail_page = (f"/repos/{watch.TARGET}/issues", 2)
        with self.assertRaises(watch.WatchError):
            watch.run(api, "2026.11.2", apply=True)
        self.assertFalse(api.writes)

    def test_partial_release_scan_never_writes(self):
        api = API([release("2026.11.3") for _ in range(100)])
        api.fail_page = (f"/repos/{watch.UPSTREAM}/releases", 2)
        with self.assertRaises(watch.WatchError):
            watch.run(api, "2026.11.2", apply=True)
        self.assertFalse(api.writes)

    def test_scan_bounds_and_invalid_response_fail_closed(self):
        api = API([release("2026.11.3") for _ in range(100)])
        with patch.object(watch, "MAX_PAGES", 1), self.assertRaises(watch.WatchError):
            watch.run(api, "2026.11.2", apply=True)
        self.assertFalse(api.writes)
        for bad in [{"message": "rate limited"}, [None]]:
            with self.subTest(bad=bad), self.assertRaises(watch.WatchError):
                watch.scan(Mock(request=Mock(return_value=bad)), f"/repos/{watch.UPSTREAM}/releases")

    def test_lost_post_response_is_not_retried_and_next_run_deduplicates(self):
        api = API([release("2026.11.3")])
        api.lose_post_response = True
        with self.assertRaises(watch.WatchError):
            watch.run(api, "2026.11.2", apply=True)
        self.assertEqual(len(api.writes), 1)
        api.lose_post_response = False
        watch.run(api, "2026.11.2", apply=True)
        self.assertEqual(len(api.writes), 1)

    def test_backlog_is_bounded_and_resumes_next_run(self):
        api = API([release(f"2026.12.{n}") for n in range(7)])
        result = watch.run(api, "2026.11.2", apply=True)
        self.assertEqual(len(api.writes), 5)
        self.assertEqual(result["remaining"], 2)
        watch.run(api, "2026.11.2", apply=True)
        self.assertEqual(len(api.writes), 7)

    def test_incomplete_post_response_stops_without_retry(self):
        api = API([release("2026.11.3"), release("2026.11.4")])
        original = api.request

        def request(method, path, body=None):
            result = original(method, path, body)
            return {} if method == "POST" else result

        api.request = request
        with self.assertRaises(watch.WatchError):
            watch.run(api, "2026.11.2", apply=True)
        self.assertEqual(len(api.writes), 1)

    def test_policy_cannot_point_elsewhere_or_advance_baseline_alone(self):
        base = dict(published_repository=watch.TARGET,
                    upstream_repository=f"https://github.com/{watch.UPSTREAM}",
                    version="2026.11.2.1", upstream_tag="2026.11.2")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(json.dumps(base))
            self.assertEqual(watch.load_policy(path), "2026.11.2")
            for change in [dict(published_repository="someone/else"),
                           dict(upstream_repository="https://evil.invalid"),
                           dict(upstream_tag="2026.11.3")]:
                path.write_text(json.dumps(base | change))
                with self.assertRaises(watch.WatchError):
                    watch.load_policy(path)

    def test_apply_requires_correct_actions_context(self):
        env = dict(GITHUB_ACTIONS="true", GITHUB_REPOSITORY=watch.TARGET,
                   GITHUB_REF="refs/heads/hodko", GITHUB_EVENT_NAME="schedule", GH_TOKEN="test",
                   PID_UPSTREAM_ISSUES_ENABLED="true")
        watch.require_actions(env)
        watch.require_actions(env | {"GITHUB_EVENT_NAME": "workflow_dispatch"})
        for field, value in [("GITHUB_ACTIONS", "false"), ("GITHUB_REPOSITORY", watch.UPSTREAM),
                             ("GITHUB_REF", "refs/heads/test"), ("GITHUB_EVENT_NAME", "pull_request"),
                             ("GH_TOKEN", "")]:
            with self.subTest(field=field), self.assertRaises(watch.WatchError):
                watch.require_actions(env | {field: value})

    def test_schedule_is_read_only_until_enabled_and_manual_apply_is_explicit(self):
        env = dict(GITHUB_ACTIONS="true", GITHUB_REPOSITORY=watch.TARGET,
                   GITHUB_REF="refs/heads/hodko", GITHUB_EVENT_NAME="schedule", GH_TOKEN="test")
        for value in [None, "", "false", "TRUE", "1"]:
            settings = env if value is None else env | {"PID_UPSTREAM_ISSUES_ENABLED": value}
            with self.subTest(value=value), patch.dict(watch.os.environ, settings, clear=True), \
                    patch("sys.argv", ["watch_upstream.py", "--apply"]), \
                    patch.object(watch, "GitHub") as client, \
                    patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(watch.main(), 1)
                client.assert_not_called()
        watch.require_actions(env | {"PID_UPSTREAM_ISSUES_ENABLED": "true"})
        # Explicit manual --apply is permitted for acceptance before arming cron.
        watch.require_actions(env | {"GITHUB_EVENT_NAME": "workflow_dispatch"})

    def test_real_http_adapter_pagination_and_post_contract(self):
        api = watch.GitHub("private-token")
        response = Mock(status=200)
        response.read.return_value = b"[]"
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        api.opener = Mock()
        api.opener.open.return_value = response
        result = watch.run(api, "2026.11.2")
        self.assertEqual(result["newer_versions"], 0)
        urls = [call.args[0].full_url for call in api.opener.open.call_args_list]
        self.assertIn("/releases?per_page=100&page=1", urls[0])
        self.assertIn("/issues?state=all&", urls[1])
        response.status = 201
        response.read.return_value = b'{"number": 123}'
        self.assertEqual(api.request("POST", f"/repos/{watch.TARGET}/issues", {"title": "safe"}), {"number": 123})
        request = api.opener.open.call_args.args[0]
        self.assertEqual(json.loads(request.data), {"title": "safe"})
        self.assertEqual(request.get_method(), "POST")

    def test_http_errors_timeout_and_bad_json_are_bounded_and_redacted(self):
        for error in [HTTPError("url", code, "secret-response", {}, io.BytesIO(b"secret-token"))
                      for code in [403, 404, 429, 500]] + [TimeoutError("secret-token")]:
            api = watch.GitHub("secret-token")
            api.opener = Mock()
            api.opener.open.side_effect = error
            with self.assertRaises(watch.WatchError) as caught:
                api.request("POST", f"/repos/{watch.TARGET}/issues", {})
            self.assertNotIn("secret", str(caught.exception))
            self.assertEqual(api.opener.open.call_count, 1)
        api.opener.open.side_effect = None
        with patch.object(watch, "json") as json_mock:
            json_mock.load.side_effect = ValueError("secret-response")
            api.opener.open.return_value = io.BytesIO(b"not-json")
            api.opener.open.return_value.status = 200
            with self.assertRaises(watch.WatchError):
                api.request("GET", f"/repos/{watch.UPSTREAM}/releases?per_page=100&page=1")

    def test_api_cannot_merge_push_release_or_redirect(self):
        api = watch.GitHub("test")
        for method, path in [("PUT", f"/repos/{watch.TARGET}/pulls/1/merge"),
                             ("POST", f"/repos/{watch.TARGET}/releases"),
                             ("POST", f"/repos/{watch.UPSTREAM}/issues"),
                             ("GET", "https://evil.invalid")]:
            with self.subTest(path=path), self.assertRaises(watch.WatchError):
                api.request(method, path)
        with self.assertRaises(watch.WatchError):
            watch.NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://evil.invalid")


if __name__ == "__main__":
    unittest.main(verbosity=2)
