"""BAR-specific characterization; genuine integration and fake local switch."""
import os
import time
from datetime import timedelta
import pytest
from homeassistant.components.climate import HVACMode


@pytest.mark.parametrize('duty', [0, 5, 20, 100])
async def test_bar_pwm_with_minute_control_and_manual_off(hass, freezer, bar, duty):
    entity, calls = bar
    hass.states.async_set('switch.bar_valve', 'off')
    await hass.async_block_till_done()
    entity._control_output = duty
    entity._pid_output = duty  # The real keepalive must see the same fixed demand.
    entity._last_heat_cycle_time = (time.time() if os.getenv("PID_BASELINE") else time.monotonic()) - 900
    entity._last_device_state = False
    entity._force_on = entity._force_off = False
    transitions = []
    previous = 'off'
    calls.clear()
    for elapsed in range(0, 1801, 60):
        if elapsed:
            freezer.tick(timedelta(seconds=60))
        await entity.set_control_value()
        await hass.async_block_till_done()
        state = hass.states.get('switch.bar_valve').state
        if state != previous:
            transitions.append([elapsed, state])
            previous = state
    await entity.async_set_hvac_mode(HVACMode.OFF)
    await hass.async_block_till_done()
    assert hass.states.get('switch.bar_valve').state == 'off'
    assert all(eid == 'switch.bar_valve' for _, eid in calls)
    if duty == 0:
        assert transitions == []
    elif duty == 100:
        assert transitions == [[0, 'on']]
    elif duty == 20:
        assert transitions[:4] == [[0, 'on'], [180, 'off'], [900, 'on'], [1080, 'off']]
    else:
        assert transitions[:4] == [[0, 'on'], [60, 'off'], [960, 'on'], [1020, 'off']]


async def test_off_with_regular_temperature_reports_does_not_integrate_off(hass, freezer, bar):
    entity, calls = bar
    freezer.tick(timedelta(seconds=600))
    hass.states.async_set('sensor.bar_temperature', '19.0001')
    await hass.async_block_till_done()
    before = entity._pid_controller.integral
    await entity.async_set_hvac_mode(HVACMode.OFF)
    await hass.async_block_till_done()
    calls.clear()
    for minute in range(1, 31):
        freezer.tick(timedelta(seconds=60))
        hass.states.async_set('sensor.bar_temperature', str(19.0001 - minute * 0.01))
        await hass.async_block_till_done()
        await entity._async_control_heating(calc_pid=True)
        await hass.async_block_till_done()
    assert not any(cmd == 'turn_on' for cmd, _ in calls)
    await entity.async_set_hvac_mode(HVACMode.HEAT)
    await hass.async_block_till_done()
    after = entity._pid_controller.integral
    expected = 0.0 if os.getenv('PID_BASELINE') else before
    assert after == pytest.approx(expected)


async def test_constant_temperature_reports_do_not_erase_elapsed_integral(hass, freezer, bar):
    entity, calls = bar
    for minute in range(1, 11):
        freezer.tick(timedelta(seconds=60))
        hass.states.async_set('sensor.bar_temperature', '19.0' if minute < 10 else '19.0001')
        await hass.async_block_till_done()
        await entity._async_control_heating(calc_pid=False)
        await hass.async_block_till_done()
    # Error ~1 K for 600 seconds at Ki .01; receipt cadence is not lost time.
    assert entity._pid_controller.integral == pytest.approx(6.0, abs=.01)
