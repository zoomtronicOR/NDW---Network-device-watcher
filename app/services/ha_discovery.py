from __future__ import annotations

import json

import paho.mqtt.client as mqtt

_DEVICE_INFO = {
    "identifiers": ["networkwatcher"],
    "name": "Network Device Watcher",
    "manufacturer": "Network Device Watcher",
}

_SENSORS = [
    {"object_id": "devices_total", "name": "Network Devices Total", "state_suffix": "stats/total", "icon": "mdi:lan"},
    {
        "object_id": "devices_online",
        "name": "Network Devices Online",
        "state_suffix": "stats/online",
        "icon": "mdi:lan-connect",
    },
    {
        "object_id": "devices_wifi",
        "name": "Network Devices Wi-Fi",
        "state_suffix": "stats/wifi",
        "icon": "mdi:wifi",
    },
    {
        "object_id": "devices_lan",
        "name": "Network Devices LAN",
        "state_suffix": "stats/lan",
        "icon": "mdi:ethernet",
    },
    {
        "object_id": "last_new_device",
        "name": "Network Last New Device",
        "state_suffix": "stats/last_new_device",
        "icon": "mdi:new-box",
    },
]


def publish_discovery(client: mqtt.Client, discovery_prefix: str, base_topic: str, qos: int) -> None:
    """Publish retained HA MQTT discovery config messages (§16).

    Idempotent -- safe to call on every (re)connect. HA only needs to see
    these once per entity, but retained republishing is harmless.
    """
    for sensor in _SENSORS:
        topic = f"{discovery_prefix}/sensor/networkwatcher/{sensor['object_id']}/config"
        payload = {
            "name": sensor["name"],
            "unique_id": f"networkwatcher_{sensor['object_id']}",
            "state_topic": f"{base_topic}/{sensor['state_suffix']}",
            "icon": sensor["icon"],
            "device": _DEVICE_INFO,
        }
        client.publish(topic, json.dumps(payload), qos=qos, retain=True)

    binary_topic = f"{discovery_prefix}/binary_sensor/networkwatcher/new_device/config"
    binary_payload = {
        "name": "Network New Device",
        "unique_id": "networkwatcher_new_device",
        "state_topic": f"{base_topic}/stats/new_device_flag",
        "payload_on": "ON",
        "payload_off": "OFF",
        "device_class": "connectivity",
        "device": _DEVICE_INFO,
    }
    client.publish(binary_topic, json.dumps(binary_payload), qos=qos, retain=True)
