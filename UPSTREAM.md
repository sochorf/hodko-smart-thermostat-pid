# Upstream PID release monitoring

The Marketplace integration follows **our fork releases**. It does not merge
ScratMan changes or update HA when an upstream issue is opened.

## What the workflow does

`.github/workflows/upstream-watch.yml` checks stable releases of
`ScratMan/HASmartThermostat` daily at **07:17 UTC** (08:17 CET / 09:17 CEST).
It runs only in `sochorf/hodko-smart-thermostat-pid`, on default branch `hodko`.
The explicit reviewed baseline is `upstream_tag` in `release-policy.json`,
initially **2026.11.2**, alongside its existing `upstream_commit`.

Every newer numeric `X.Y.Z` version gets one review issue assigned to `sochorf`,
with release/compare links and a checklist for preserving Hodko fixes and tests.
The watcher scans all release pages, so it catches versions missed between runs.
It ignores drafts, prereleases and historical alpha/beta/rc/dev tags that were
incorrectly marked stable. `vX.Y.Z` and `X.Y.Z` count as the same version.
An unknown stable tag format fails the run visibly instead of silently ignoring
a possible update. No upstream release body is executed or copied into an issue.

Open **and closed** issues are scanned without GitHub Search indexing. The hidden
canonical-version marker survives title edits; the standard title is a fallback
if the marker was removed. PRs do not count as review issues. Do not delete or
transfer tracking issues, or remove both title and marker: the next scan would
no longer have that deduplication record. Closing a skipped release is sufficient;
the watcher does not reopen it, add comments, or resend reminders.

Scheduled and manual runs share one concurrency group, without canceling a
running request. At most five new issues are created per run; a larger backlog
continues next time. All reads/validation complete before writes. API errors,
rate limits, incomplete pagination and ambiguous POST responses fail the run.
POSTs are never automatically retried: the next run first checks whether the
server created the issue despite the lost response. This is practical
deduplication, not a transactional GitHub uniqueness constraint; a concurrent
human-created issue or deleted record remains outside that guarantee.

The token has only `contents: read` and `issues: write`; checkout does not persist
credentials. It is the built-in short-lived `GITHUB_TOKEN`, no new PAT or HA
credential. The script allowlists release listing, issue listing and issue
creation in these exact repositories, and refuses redirects. No branches,
pull requests, merges, releases, Marketplace operations or HA changes are made.

## Offline verification and activation

```sh
python3 scripts/test_watch_upstream.py
python3 scripts/check_release.py
```

Tests use a simulated GitHub API and block network sockets. They cover versions,
pagination, open/closed issue deduplication, reruns, a lost creation response,
read failures, rate limits, bounded catch-up, untrusted metadata and write guards.
They run in normal PR/push CI as well as before each scheduled check.

After a separately approved commit/push to default branch `hodko`:

1. Check Actions is enabled for this fork and this specific workflow.
2. Run **Watch upstream PID releases** manually with `create_issues=false`.
   Review the summary, baseline and candidate versions. Manual dispatch defaults
   to this read-only preview; scheduled runs create missing issues automatically.
3. After approving live issue creation, use `create_issues=true` or allow the
   next daily run. Review the single issue per candidate; repeat the check and
   verify it does not create duplicates. Do not fabricate a release to test this.
4. Enable notifications for assigned issues/failed Actions in your GitHub account.
   Assignment creates the normal GitHub notification; email/mobile delivery still
   depends on personal settings. As a separate fallback, **Watch → Custom →
   Releases** on the upstream repository. Do not assume this subscription was set.

**Publishing the workflow to the default branch enables scheduled issue creation**
once Actions permits it. There is no HA restart or PID release required. Offline
tests are not evidence of a GitHub-hosted run, token permissions or notification
delivery. Public fork scheduled workflows may require enabling; GitHub can disable
schedules after 60 days of repository inactivity, and scheduled runs can be late.
Check workflow health and retain the independent Watch Releases notification.

## Review and adoption

An issue does not mean the update is safe. Review upstream in a separate branch,
preserve/reassess the local lifecycle patch, run PID and Marketplace regressions,
and update `upstream_tag`, `upstream_commit`, fork version and release integrity
policy together **only when the new upstream code has been reviewed and adopted**.
The watcher never advances the baseline. Closing an issue does not advance it.
Publish an approved fork release separately; Marketplace then offers that release.
Live deployment and rollback remain a separate controlled procedure.

## Disable / return

Disable only **Watch upstream PID releases** in GitHub Actions (or revert this
watcher commit). Leave existing review issues in place for future deduplication.
This stops monitoring/issue creation without changing the installed PID, its
version, heating, DHW, targets or any integration setting. Re-enabling catches up
newer releases, bounded to five new issues per run.

## Primary references

- [Release API](https://docs.github.com/en/rest/releases/releases#list-releases)
- [Repository issue API](https://docs.github.com/en/rest/issues/issues#list-repository-issues)
- [Workflow concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
- [Schedule restrictions](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
