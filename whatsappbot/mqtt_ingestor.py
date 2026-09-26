import json
import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
import paho.mqtt.client as mqtt

from storage import initialize_database, replace_faults, save_state

load_dotenv()

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TELEMETRY_TOPIC = os.getenv("MQTT_TELEMETRY_TOPIC", "agribot/inverter/telemetry")
MIN_CURRENT_A = float(os.getenv("MIN_CURRENT_A", "2"))
MAX_CURRENT_A = float(os.getenv("MAX_CURRENT_A", "40"))
MIN_SOLAR_VOLTAGE_V = float(os.getenv("MIN_SOLAR_VOLTAGE_V", "500"))


def number(data: dict[str, Any], key: str, minimum: float, maximum: float) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    value = float(value)
    if not minimum <= value <= maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}")
    return value


def boolean(data: dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.lower() in {"true", "false", "1", "0"}:
        return value.lower() in {"true", "1"}
    raise ValueError(f"{key} must be a boolean")


def normalize(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "frequency_hz": number(data, "frequency_hz", 0, 50),
        "dc_voltage_v": number(data, "dc_voltage_v", 0, 2000),
        "current_a": number(data, "current_a", 0, 500),
        "running": boolean(data, "running", False),
        "available": boolean(data, "available", True),
        "rotation_rpm": number(data, "rotation_rpm", 0, 10000),
        "water_level_percent": number(data, "water_level_percent", 0, 100),
    }


def derive_faults(state: dict[str, Any], device_faults: list[Any]) -> list[dict[str, str]]:
    faults: dict[str, str] = {}
    current = state.get("current_a")
    voltage = state.get("dc_voltage_v")
    if state["running"] and current is not None and current < MIN_CURRENT_A:
        faults["LOW_CURRENT"] = "Pump current is below the configured safe limit."
    if current is not None and current > MAX_CURRENT_A:
        faults["HIGH_CURRENT"] = "Pump current is above the configured safe limit."
    if voltage is not None and voltage < MIN_SOLAR_VOLTAGE_V:
        faults["LOW_SOLAR"] = "Solar DC voltage is too low."
    if not state["available"]:
        faults["INVERTER_OFFLINE"] = "The inverter reports that it is unavailable."
    for item in device_faults:
        if isinstance(item, str):
            faults[item.upper().replace(" ", "_")] = item
        elif isinstance(item, dict) and item.get("code"):
            faults[str(item["code"])] = str(item.get("message", item["code"]))
    return [{"code": code, "message": message} for code, message in faults.items()]


def on_connect(client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
    if reason_code == 0:
        client.subscribe(MQTT_TELEMETRY_TOPIC, qos=1)
        print(f"Connected. Listening on {MQTT_TELEMETRY_TOPIC}")
    else:
        print(f"MQTT connection failed: {reason_code}")


def on_message(client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
    try:
        raw = json.loads(message.payload.decode("utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("payload must be a JSON object")
        state = normalize(raw)
        timestamp = datetime.now(timezone.utc).isoformat()
        save_state(state, timestamp)
        replace_faults(derive_faults(state, raw.get("faults", [])), timestamp)
        print(f"Stored telemetry packet at {timestamp}")
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"Rejected invalid packet: {exc}")


def main() -> None:
    initialize_database()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    username = os.getenv("MQTT_USERNAME")
    if username:
        client.username_pw_set(username, os.getenv("MQTT_PASSWORD"))
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    print(f"MQTT collector starting for {MQTT_HOST}:{MQTT_PORT}")
    client.loop_forever()


if __name__ == "__main__":
    main()
