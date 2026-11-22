# Hodko Smart Thermostat PID

Maintenance fork of [HASmartThermostat](https://github.com/ScratMan/HASmartThermostat).
See [upstream documentation](README.upstream.md) and [migration notes](MIGRATION.md).

This first release preserves the reviewed PID lifecycle fixes: no integration
over an OFF interval, no obsolete actuator write while lowering a target,
correct elapsed time across repeated temperature reports, OFF before stall fallback.
The PID kernel is unchanged from upstream 2026.11.2. Entity domain and identity stay unchanged.

Version 2026.11.2.1 uses upstream version plus fork revision. The +build suffix
must not be used for sequential updates. Releases need matching manifest/tag.
Fork repository: [sochorf/hodko-smart-thermostat-pid](https://github.com/sochorf/hodko-smart-thermostat-pid).
No fork release has been published yet. Repository publication does not install
or migrate an existing Home Assistant integration. Follow the separately approved
migration plan before installing the first release.

Run `python scripts/check_release.py` and `python scripts/run_tests.py` in the pinned CI environment.
Tests use fake switches and disabled sockets, never a production HA.
MIT and embedded PID licenses are retained. No HA configuration or credentials are included.
