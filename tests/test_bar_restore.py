"""Restart/rollback acceptance with real HA restore, fake local relay only."""
import os

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import State
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import mock_restore_cache


@pytest.mark.parametrize("mode", [HVACMode.HEAT, HVACMode.OFF])
@pytest.mark.parametrize("integral", [0.0, 6.0])
async def test_restore_keeps_bar_identity_target_gains_and_mode(hass, mode, integral):
    """Both candidate and rollback can consume the existing restored attributes."""
    entity_id = "climate.bathroom_suteren_pid"
    # Target 21 deliberately differs from YAML 20. A restart must not revert it.
    mock_restore_cache(hass, [State(entity_id, mode, attributes={
        "temperature": 21.0, "pid_i": integral, "pid_mode": "auto",
        "kp": 5.0, "ki": 0.01, "kd": 500.0, "ke": 0.0,
    })])
    await async_setup_component(hass, "switch", {})
    await async_setup_component(hass, "sensor", {})
    calls = []

    async def record(call):
        entities = call.data.get("entity_id", [])
        if isinstance(entities, str):
            entities = [entities]
        for entity in entities:
            assert entity == "switch.bar_valve"
            calls.append(call.service)
            hass.states.async_set(entity, "on" if call.service == "turn_on" else "off")

    for service in ("turn_on", "turn_off"):
        hass.services.async_register("switch", service, record)
    hass.states.async_set("switch.bar_valve", "off")
    hass.states.async_set("sensor.bar_temperature", "20.0")
    original_report = hass.states.get("sensor.bar_temperature").last_reported.timestamp()
    config = {"climate": {
        "platform": "smart_thermostat", "name": "Bathroom Suteren PID",
        "unique_id": "bathroom_suteren_pid", "heater": "switch.bar_valve",
        "target_sensor": "sensor.bar_temperature", "min_temp": 7, "max_temp": 28,
        "ac_mode": False, "target_temp": 20, "away_temp": 16,
        "keep_alive": {"seconds": 60}, "pwm": "00:15:00",
        "kp": 5, "ki": 0.01, "kd": 500,
    }}
    assert await async_setup_component(hass, "climate", config)
    await hass.async_block_till_done()
    await hass.async_start()
    await hass.async_block_till_done()
    entity = hass.data["climate"].get_entity(entity_id)
    assert entity.unique_id == "bathroom_suteren_pid"
    assert entity._target_temp == 21
    assert entity.hvac_mode == mode
    assert (entity._kp, entity._ki, entity._kd, entity._ke) == (5, .01, 500, 0)
    assert entity._pwm == 900
    assert entity._keep_alive.total_seconds() == 60
    # .10.2 intentionally clears I in OFF, including a restored OFF. Rollback
    # restores the old policy; it is not supposed to preserve the new memory.
    expected_i = 0.0 if os.getenv("PID_BASELINE") and mode == HVACMode.OFF else integral
    assert entity._pid_controller.integral == pytest.approx(expected_i)
    if mode == HVACMode.OFF:
        assert "turn_on" not in calls
        assert hass.states.get("switch.bar_valve").state == "off"
    else:
        assert 0 <= entity._control_output <= 100
    # Restored mode/target must not fabricate another temperature report.
    assert hass.states.get("sensor.bar_temperature").last_reported.timestamp() == original_report
