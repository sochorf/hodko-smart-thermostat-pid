"""Isolated HA fixture: only a fake BAR switch; no production connections."""
import pytest
from homeassistant.setup import async_setup_component
from homeassistant.components.climate import HVACMode

@pytest.fixture(autouse=True)
def expected_lingering_timers():
    # The integration owns a keep_alive subscription, as in upstream tests.
    return True

@pytest.fixture
async def bar(hass):
    calls = []
    await async_setup_component(hass, 'switch', {})
    await async_setup_component(hass, 'sensor', {})
    async def record(call):
        entities = call.data.get('entity_id', [])
        if isinstance(entities, str):
            entities = [entities]
        for eid in entities:
            calls.append((call.service, eid))
            hass.states.async_set(eid, 'on' if call.service == 'turn_on' else 'off')
    hass.services.async_register('switch', 'turn_on', record)
    hass.services.async_register('switch', 'turn_off', record)
    hass.states.async_set('switch.bar_valve', 'off')
    hass.states.async_set('sensor.bar_temperature', '19.0')
    config = {'climate': {
        'platform': 'smart_thermostat', 'name': 'Bathroom Suteren PID',
        'unique_id': 'bathroom_suteren_pid', 'heater': 'switch.bar_valve',
        'target_sensor': 'sensor.bar_temperature', 'min_temp': 7, 'max_temp': 28,
        'ac_mode': False, 'target_temp': 20, 'away_temp': 16,
        'keep_alive': {'seconds': 60}, 'kp': 5, 'ki': 0.01, 'kd': 500,
        'pwm': '00:15:00', 'initial_hvac_mode': HVACMode.HEAT,
    }}
    assert await async_setup_component(hass, 'climate', config)
    await hass.async_block_till_done()
    await hass.async_start()
    await hass.async_block_till_done()
    entity = hass.data['climate'].get_entity('climate.bathroom_suteren_pid')
    assert entity is not None
    assert entity._pwm == 900
    return entity, calls
