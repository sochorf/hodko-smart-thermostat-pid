# PID fork: offline migration contract

This is preparation, not an instruction to run a live uninstall or update.
No public repository or release is created by the builder. The first candidate
2026.11.2.1 keeps the reviewed control code of 2026.11.2+hodko.bar.1.
Only distribution metadata changes. Upstream history and licenses are retained.

## Ownership transition

1. Review/publish a tested release in a separate public fork, with its own
   documentation/issue URL, matching tag/manifest and regression CI. Keep old
   releases. Marketplace follows fork releases, not upstream releases automatically.
2. Before a separately approved live transition, capture a full HA backup and
   the exact repaired component/configuration, targets, modes and gains. Verify
   the installed Marketplace/HA version and all instances of this domain.
3. Arrange a controlled Git synchronization window. Detach the component from
   the Git index **on the installation host**, preserving the working files;
   ignore its path and remove it from deployment inventory in the same reviewed
   handoff. Commit there and synchronize this commit to the other checkout.
   A deletion commit originating on the workstation instead deletes HA files.
   No future Git pull/reset may reinstall an older component over Marketplace.
4. Standard Marketplace refuses two installed repositories owning the same
   domain. Add/validate the fork first; uninstall the original repository only
   in the approved window, then install the selected fork release. An uninstall
   removes files, so never restart between these operations. A loaded YAML
   integration is not evidence that its files can safely be absent indefinitely.
   Config-entry instances may block uninstall; do not delete their entries to
   bypass this restriction. Reassess migration if such instances are found.
5. Verify file hashes and Marketplace installed version, then perform the agreed
   restart. Check restored entity/target/gains/PID/relay, automatic boiler start,
   command confirmations, the unchanged water limit and DHW automation.

## Updates and return

Normal update and downgrade select a release of the **same fork** through the
standard Marketplace UI. No installed-version edits, skipped update, side-loading
or rewritten live storage. A failed update must restore its previous files and
installed-version record; a failed first install cannot restore files removed
by a preceding separate uninstall. These are different failure cases.

On failure of the initial handoff, stop before restart and use the approved
backup/restore procedure. A full HA backup restores the previous files and
manager metadata together; a Git revert alone does not restore Marketplace
ownership. The offline suite tests file transactions and records, not Supervisor
backup restoration, browser flows, GitHub availability or physical valve behavior.

An interruption between uninstall and install remains a maintenance risk.
There is no promise of a zero-downtime atomic migration. No live migration is
ready until the release is public and that deployment/restore window is approved.

## Evidence boundaries

Tests execute real HA 2026.11.2 Marketplace repository/backup/version/storage
code in temporary configuration directories. Only GitHub discovery/downloads
are replaced by local release contents. No production HA, MQTT or device calls.
The second release is a test fixture changing version metadata only, never a
published release. PID regressions use fake switch services and disabled sockets.

Local preparation and tests do not authorize publication, live Git index edits,
Marketplace install/uninstall, reload or restart. Existing heating/DHW and safety
settings remain unchanged.

Sources: https://www.home-assistant.io/integrations/marketplace/
and https://contributors.home-assistant.io/marketplace/guides/releases/
