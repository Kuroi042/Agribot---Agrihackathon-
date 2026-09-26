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
MAX_TEMPERATURE_C = float(os.getenv("MAX_TEMPERATURE_C", "75"))
MIN_BATTERY_PERCENT = float(os.getenv("MIN_BATTERY_PERCENT", "20"))
MIN_WATER_LEVEL_PERCENT = float(os.getenv("MIN_WATER_LEVEL_PERCENT", "20"))

DEVICE_FAULT_MESSAGES = {
    "E056": "Low battery voltage: reduce demand and check battery charge, charging source, and terminals.",
    "E065": "Inverter over-temperature: reduce load or stop the pump, allow cooling, and check airflow and fans.",
    "E070": "Low water level: stop the pump or keep it stopped until the source-water level is safely restored.",
    "OVER_CURRENT": "Pump current is above the inverter's permitted limit.",
    "DRY_RUN": "Dry-run protection has tripped; the pump may have lost prime or source water.",
    "OVERLOAD": "The pump or motor is overloaded.",
    "OVER_VOLTAGE": "Input voltage is above the inverter's permitted limit.",
    "UNDER_VOLTAGE": "Input voltage is below the inverter's permitted limit.",
    "PHASE_LOSS": "An input phase is missing or unstable.",
    "GROUND_FAULT": "A ground/insulation fault has been reported.",
    "COMMUNICATION_FAILURE": "Communication with the inverter or controller has failed.",
    "MOTOR_OVERHEAT": "Motor temperature is above its safe limit.",
    "PUMP_BLOCKED": "A pump blockage or mechanical jam has been reported.",
    "SENSOR_FAILURE": "A sensor or its wiring has failed validation.",
}


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
    inverter_id = number(data, "inverter_id", 0, 255)
    status = number(data, "status", 0, 255)
    return {
        "inverter_id": int(inverter_id) if inverter_id is not None else None,
        "frequency_hz": number(data, "frequency_hz", 0, 50),
        "dc_voltage_v": number(data, "dc_voltage_v", 0, 2000),
        "ac_voltage_v": number(data, "ac_voltage_v", 0, 1000),
        "ac_power_w": number(data, "ac_power_w", 0, 65535),
        "power_factor": number(data, "power_factor", 0, 1),
        "battery_percent": number(data, "battery_percent", 0, 100),
        "temperature_c": number(data, "temperature_c", -40, 125),
        "status": int(status) if status is not None else None,
        "current_a": number(data, "current_a", 0, 500),
        "running": boolean(data, "running", False),
        "available": boolean(data, "available", True),
        "rotation_rpm": number(data, "rotation_rpm", 0, 10000),
        "water_level_percent": number(data, "water_level_percent", 0, 100),
        "solar_power_w": number(data, "solar_power_w", 0, 100000),
        "daily_energy_kwh": number(data, "daily_energy_kwh", 0, 100000),
        "total_energy_kwh": number(data, "total_energy_kwh", 0, 10000000),
        "pump_flow_m3h": number(data, "pump_flow_m3h", 0, 10000),
        "pump_pressure_bar": number(data, "pump_pressure_bar", 0, 1000),
        "runtime_hours": number(data, "runtime_hours", 0, 1000000),
        "operating_mode": data.get("operating_mode") if isinstance(data.get("operating_mode"), str) else None,
    }


def derive_faults(state: dict[str, Any], device_faults: list[Any]) -> list[dict[str, str]]:
    faults: dict[str, str] = {}
    reported_codes = {item.upper().replace(" ", "_") for item in device_faults if isinstance(item, str)}
    current = state.get("current_a")
    voltage = state.get("dc_voltage_v")
    temperature = state.get("temperature_c")
    battery = state.get("battery_percent")
    water = state.get("water_level_percent")
    if state["running"] and current is not None and current < MIN_CURRENT_A:
        faults["LOW_CURRENT"] = "Pump current is below the configured safe limit."
    if current is not None and current > MAX_CURRENT_A:
        faults["HIGH_CURRENT"] = "Pump current is above the configured safe limit."
    if voltage is not None and voltage < MIN_SOLAR_VOLTAGE_V:
        faults["LOW_SOLAR"] = "Solar DC voltage is too low."
    if temperature is not None and temperature > MAX_TEMPERATURE_C:
        faults["OVER_TEMPERATURE"] = "Inverter temperature exceeds the configured safe limit."
    if battery is not None and battery < MIN_BATTERY_PERCENT:
        faults["LOW_BATTERY"] = "Battery charge is below the configured safe limit."
    if water is not None and water < MIN_WATER_LEVEL_PERCENT:
        faults["LOW_WATER"] = "Water level is below the configured safe limit."
    if not state["available"]:
        faults["INVERTER_OFFLINE"] = "The inverter reports that it is unavailable."
    for item in device_faults:
        if isinstance(item, str):
            code = item.upper().replace(" ", "_")
            faults[code] = DEVICE_FAULT_MESSAGES.get(code, item)
        elif isinstance(item, dict) and item.get("code"):
            faults[str(item["code"])] = str(item.get("message", item["code"]))
    # Do not show a threshold warning twice when the device supplied its equivalent E-code.
    for device_code, derived_code in {"E056": "LOW_BATTERY", "E065": "OVER_TEMPERATURE", "E070": "LOW_WATER"}.items():
        if device_code in reported_codes:
            faults.pop(derived_code, None)
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
