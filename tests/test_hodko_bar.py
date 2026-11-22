"""Local, isolated acceptance probes; no production endpoints or credentials."""
import time
import os
from datetime import timedelta

import pytest
from homeassistant.components.climate import HVACMode


@pytest.mark.parametrize('pause', [1800, 8 * 3600])
async def test_off_is_off_and_resume_does_not_integrate_pause(hass, freezer, bar, pause):
    entity, calls = bar
    freezer.tick(timedelta(seconds=600))
    hass.states.async_set('sensor.bar_temperature', '19.0001')
    await hass.async_block_till_done()
    integral = entity._pid_controller.integral
    assert integral == pytest.approx(6.0, abs=0.01)
    # The baseline deliberately clears I on OFF; it must not integrate OFF either.
    expected_resume_i = 0.0 if os.getenv('PID_BASELINE') else integral
    await entity.async_set_hvac_mode(HVACMode.OFF)
    await hass.async_block_till_done()
    assert hass.states.get('switch.bar_valve').state == 'off'
    calls.clear()
    freezer.tick(timedelta(seconds=pause))
    hass.states.async_set('sensor.bar_temperature', '18.5')
    await hass.async_block_till_done()
    await entity._async_control_heating(calc_pid=True)
    await hass.async_block_till_done()
    assert not any(action == 'turn_on' for action, _ in calls)
    assert entity._pid_controller.integral == pytest.approx(expected_resume_i)
    await entity.async_set_hvac_mode(HVACMode.HEAT)
    await hass.async_block_till_done()
    assert entity._pid_controller.integral == pytest.approx(expected_resume_i)
    assert entity._pid_controller.derivative == 0
    assert 0 <= entity._control_output <= 100


async def test_live_satisfied_room_has_zero_output(hass, bar):
    entity, _ = bar
    hass.states.async_set('sensor.bar_temperature', '23.6')
    await hass.async_block_till_done()
    await entity.async_set_temperature(temperature=18)
    await hass.async_block_till_done()
    assert entity._control_output == 0
    assert hass.states.get('switch.bar_valve').state == 'off'


async def test_setback_does_not_send_extra_old_target_on(hass, freezer, bar):
    entity, calls = bar
    # An OFF PWM phase reaching its next ON boundary as the night target arrives.
    # PID has no new temperature sample in this 15-minute period.
    freezer.tick(timedelta(seconds=900))
    hass.states.async_set('switch.bar_valve', 'off')
    entity._last_heat_cycle_time = (time.time() if os.getenv("PID_BASELINE") else time.monotonic()) - 900
    entity._pid_controller.integral = 0.0
    await hass.async_block_till_done()
    calls.clear()
    await entity.async_set_temperature(temperature=17)
    await hass.async_block_till_done()
    assert entity._control_output == 0
    assert hass.states.get('switch.bar_valve').state == 'off'
    assert not any(action == 'turn_on' for action, _ in calls), calls


async def test_unchanged_reporting_timestamp_is_recognized(hass, freezer, bar):
    entity, _ = bar
    # Recheck the old #339 probe against 2026.11.1: original receipt time,
    # including an unchanged numerical value, must be recognized.
    before = entity._last_sensor_update
    freezer.tick(timedelta(hours=7))
    hass.states.async_set('sensor.bar_temperature', '19.0')
    await hass.async_block_till_done()
    assert hass.states.get('sensor.bar_temperature').last_reported.timestamp() > before
    assert entity._last_sensor_update == hass.states.get('sensor.bar_temperature').last_reported.timestamp()
    await entity._async_control_heating(calc_pid=True)
    assert entity._control_output != 5.0
