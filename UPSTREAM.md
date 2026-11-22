# Upstream PID release monitoring

The Marketplace integration follows **our fork releases**. It does not merge
ScratMan changes or update HA when an upstream issue is opened.

## What the workflow does

`.github/workflows/upstream-watch.yml` checks stable releases of
`ScratMan/HASmartThermostat` daily at **07:17 UTC** (08:17 CET / 09:17 CEST).
It runs only in `sochorf/hodko-smart-thermostat-pid`, on default branch `hodko`.
The explicit reviewed baseline is `upstream_tag` in `release-policy.json`,
initially **2026.11.2**, alongside its existing `upstream_commit`.

Scheduled checks are **read-only by default**. Creating issues on a schedule
requires repository Actions variable `PID_UPSTREAM_ISSUES_ENABLED=true` (literal
lowercase). An absent/false variable leaves preview running. Manual dispatch
defaults to preview independently of that variable; `create_issues=true` is an
explicit one-off issue-creation request, useful before enabling the daily writer.

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

### Verified preparation, 22 November 2026

User commit **0498bf48bcdcaf202a8c2880c0b54696d96c4f8f** contains the original
watcher; the additional default-preview guard in this document must be committed
with the workflow/script/tests before the first push. At preparation time the
remote `hodko` was still **27a7292afa95c7c116a26e0fe65bcad16f55b697**, Issues were
enabled, and the watcher was not published. Repository variable settings were
not inspected or changed. Local read-only execution of 0498bf4 against the real
release/issue API succeeded with baseline 2026.11.2, zero newer/missing versions,
zero tracked candidates and zero created issues. This was not a hosted Actions run.

### A. Publish the reviewed watcher, without activating daily writes

1. Commit the default-preview guard. Verify clean branch `hodko`, review the
   whole range from 27a7292, and run the offline watcher and release checks above.
   PID runtime files/manifest/patch must still be unchanged. Record the final SHA.
2. Before push, inspect **Settings → Secrets and variables → Actions → Variables**.
   `PID_UPSTREAM_ISSUES_ENABLED` must be absent or `false`. If already `true`,
   stop and disable that daily-write permission as part of the approved launch.
3. User pushes only `hodko` to this fork. No tag, release, HA pull, restart or
   Marketplace install is needed. Check remote SHA equals the reviewed SHA and
   ordinary regression CI passes. Check Actions is enabled for this fork and
   **Watch upstream PID releases**; no need to modify other workflows.

### B. First GitHub-hosted read-only run

In **Actions → Watch upstream PID releases → Run workflow**, select branch
`hodko` and leave **create_issues=false**. Record run URL/ID, `head_sha`, event
`workflow_dispatch`, conclusion, and JSON summary. Require:

- offline watcher tests pass; the job ran, rather than being skipped;
- `mode=preview`, `baseline=2026.11.2`, `created_issues=[]`;
- every candidate links to a genuine newer stable upstream release;
- no issue was created or modified by this run.

Expected at preparation time: `newer_versions=0`, `missing_versions=[]`,
`already_tracked=0`, `remaining=0`. Re-check current upstream data; these are not
fixed assertions for a later day. On errors/skipped jobs keep daily writes off.

### C. Controlled issue creation and duplicate acceptance

Only after approving the preview, manually run the same workflow on the reviewed
SHA with **create_issues=true**, while leaving scheduled writes off. This is a
GitHub-only mutation. If there is a genuine new release, require one issue per
missing canonical version (up to five in one run), assigned to `sochorf`, with
the expected hidden marker, release/compare links and review checklist.

After that run finishes, repeat the same explicit manual run. For unchanged
upstream data with no remaining backlog, require **no new issue numbers**,
`created_issues=[]`, `missing_versions=[]`, and `already_tracked` increased by
the number created in the first run. Existing issue numbers, state, title, body,
comments and `updated_at` must not change merely because the watcher ran again.
If the upstream changed or backlog remains, only those newly untracked versions
may get new issues. Wait for the first run to finish rather than launching a race.

If there are no newer releases, both runs may succeed with zero writes. That
validates the hosted no-op path, **not** live POST permissions, assignment,
notification delivery, or duplicate handling after a real create. Record those
as pending until the first genuine release. Closed-issue and lost-response
deduplication have offline coverage; do not fabricate releases, lower the
baseline, or create synthetic production issues just to exercise them.

After acceptance, set repository Actions variable
**PID_UPSTREAM_ISSUES_ENABLED=true**. Verify the next scheduled run reports
`mode=apply`, event `schedule`, reviewed `head_sha` and a successful summary.
Daily check is 07:17 UTC, subject to GitHub scheduling delays. This variable
does not authorize merging code or installing an update.

Enable notifications for assigned issues/failed Actions in your GitHub account.
Email/mobile delivery depends on personal settings. As an independent fallback,
use **Watch → Custom → Releases** on upstream; do not assume it was configured.
Public fork schedules may require enabling; GitHub can disable schedules after
60 days of repository inactivity. Check workflow health periodically.

## Review and adoption

An issue does not mean the update is safe. Review upstream in a separate branch,
preserve/reassess the local lifecycle patch, run PID and Marketplace regressions,
and update `upstream_tag`, `upstream_commit`, fork version and release integrity
policy together **only when the new upstream code has been reviewed and adopted**.
The watcher never advances the baseline. Closing an issue does not advance it.
Publish an approved fork release separately; Marketplace then offers that release.
Live deployment and rollback remain a separate controlled procedure.

## Disable / return

For a pause of **scheduled issue creation**, set
`PID_UPSTREAM_ISSUES_ENABLED=false` (or delete it); future scheduled runs remain
read-only. An explicit manual `create_issues=true` can still write, so this is
not a total shutdown. Changing a variable does not stop a run already in progress.

For a **full stop**, Actions → **Watch upstream PID releases** → menu →
**Disable workflow**. Inspect queued/running jobs: disabling prevents new
triggers but does not cancel existing runs. Cancel those runs too if an immediate
stop is needed, and then read issues to check whether any in-flight POST completed.
Never repeat a possibly completed POST blindly. Keep all existing review issues
and their markers for future deduplication. No deletion of the fork, release,
Marketplace record or installed component is required.

For re-entry, leave the variable absent/false, enable only this workflow, repeat
the read-only acceptance, then explicitly authorize daily writes. The workflow
catches up missed releases, capped at five new issues per run. A reviewed revert
of the watcher changes is an alternative code rollback, not an HA rollback.
Neither option changes PID, heating, DHW, room targets or Spook.

## Primary references

- [Release API](https://docs.github.com/en/rest/releases/releases#list-releases)
- [Repository issue API](https://docs.github.com/en/rest/issues/issues#list-repository-issues)
- [Workflow concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
- [Schedule restrictions](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [Variables context](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#vars-context)
- [Manual dispatch](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
- [Disabling a workflow and existing runs](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows)
