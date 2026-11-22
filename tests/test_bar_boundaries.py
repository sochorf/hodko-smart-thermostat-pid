"""Boundary probes for the offline BAR prototype, with no live connections."""
from datetime import timedelta
import pytest
from homeassistant.components.climate import HVACMode


async def test_repeated_heat_does_not_reintegrate_same_sample(hass, freezer, bar):
    entity, calls = bar
    freezer.tick(timedelta(seconds=600))
    hass.states.async_set('sensor.bar_temperature', '19.0001')
    await hass.async_block_till_done()
    before = entity._pid_controller.integral
    await entity.async_set_hvac_mode(HVACMode.HEAT)
    await hass.async_block_till_done()
    assert entity._pid_controller.integral == pytest.approx(before)


async def test_settle_previous_period_is_calculation_only(hass, freezer, bar):
    entity, calls = bar
    freezer.tick(timedelta(seconds=600))
    await hass.async_block_till_done()
    calls.clear()
    await entity._async_close_previous_period()
    assert entity._pid_controller.integral == pytest.approx(6.0, abs=.01)
    assert calls == []
    # Settling twice at the same timestamp must not duplicate integration.
    await entity._async_close_previous_period()
    assert entity._pid_controller.integral == pytest.approx(6.0, abs=.01)


async def test_off_resume_does_not_refresh_source_freshness(hass, freezer, bar):
    entity, calls = bar
    await entity.async_set_hvac_mode(HVACMode.OFF)
    original_at = entity._last_sensor_update
    freezer.tick(timedelta(minutes=30))
    await hass.async_block_till_done()
    await entity.async_set_hvac_mode(HVACMode.HEAT)
    await hass.async_block_till_done()
    assert entity._last_sensor_update == original_at


async def test_target_changed_during_off_does_not_drive_valve(hass, freezer, bar):
    entity, calls = bar
    await entity.async_set_hvac_mode(HVACMode.OFF)
    freezer.tick(timedelta(minutes=30))
    hass.states.async_set('sensor.bar_temperature', '18.5')
    await hass.async_block_till_done()
    calls.clear()
    before = entity._pid_controller.integral
    await entity.async_set_temperature(temperature=21)
    await hass.async_block_till_done()
    assert not any(service == 'turn_on' for service, _ in calls)
    assert entity._pid_controller.integral == pytest.approx(before)
    assert entity.hvac_mode == HVACMode.OFF


async def test_fixed_sampling_stays_fixed_after_same_reports(hass, freezer, bar):
    entity, calls = bar
    entity._sampling_period = timedelta(seconds=60)
    entity._last_pid_calc_time = None
    entity._pid_controller.clear_samples(clear_integral=True)
    await entity.calc_pid()
    for _ in range(10):
        freezer.tick(timedelta(seconds=60))
        hass.states.async_set('sensor.bar_temperature', '19.0')
        await hass.async_block_till_done()
        await entity.calc_pid()
    assert entity._pid_controller.integral == pytest.approx(6.0)
    assert entity._pid_controller.dt == 60


async def test_sensor_stall_while_off_does_not_turn_on_valve(hass, freezer, bar):
    entity, calls = bar
    await entity.async_set_hvac_mode(HVACMode.OFF)
    freezer.tick(timedelta(hours=7))
    await hass.async_block_till_done()
    calls.clear()
    await entity._async_control_heating(calc_pid=True)
    await hass.async_block_till_done()
    assert entity.hvac_mode == HVACMode.OFF
    assert not any(service == 'turn_on' for service, _ in calls)
    assert hass.states.get('switch.bar_valve').state == 'off'


async def test_sensor_stall_while_heat_keeps_safety_output(hass, freezer, bar):
    entity, calls = bar
    freezer.tick(timedelta(hours=7))
    await hass.async_block_till_done()
    await entity._async_control_heating(calc_pid=True)
    await hass.async_block_till_done()
    assert entity.hvac_mode == HVACMode.HEAT
    assert entity._control_output == entity._output_safety == 5
