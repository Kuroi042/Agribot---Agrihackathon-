#!/usr/bin/env python3
"""Turn inverter key/value telemetry into bot-ready JSON or a readable summary.

Examples:
  python3 format_inverter_data.py real_inverter_data.txt
  python3 format_inverter_data.py real_inverter_data.txt --summary
"""

import argparse
import json
from pathlib import Path
from typing import Any


NUMERIC_FIELDS = {
    "inverter_id": int,
    "dc_voltage_v": float,
    "ac_voltage_v": float,
    "ac_power_w": float,
    "frequency_hz": float,
    "current_a": float,
    "power_factor": float,
    "battery_percent": float,
    "temperature_c": float,
    "rotation_rpm": float,
    "water_level_percent": float,
    "status": int,
    "solar_power_w": float,
    "daily_energy_kwh": float,
    "total_energy_kwh": float,
    "pump_flow_m3h": float,
    "pump_pressure_bar": float,
    "runtime_hours": float,
}
REQUIRED_FIELDS = set(NUMERIC_FIELDS) | {"running", "available", "operating_mode", "faults"}


def read_key_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"line {line_number}: expected key=value")
        key, value = (part.strip() for part in line.split("=", 1))
        if not key or not value:
            raise ValueError(f"line {line_number}: key and value are required")
        values[key] = value
    missing = sorted(REQUIRED_FIELDS - values.keys())
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))
    return values


def as_boolean(value: str, field: str) -> bool:
    if value.lower() in {"true", "1"}:
        return True
    if value.lower() in {"false", "0"}:
        return False
    raise ValueError(f"{field} must be true or false")


def normalize(values: dict[str, str]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for field, converter in NUMERIC_FIELDS.items():
        try:
            data[field] = converter(values[field])
        except ValueError as exc:
            raise ValueError(f"{field} must be a number") from exc
    data["running"] = as_boolean(values["running"], "running")
    data["available"] = as_boolean(values["available"], "available")
    data["operating_mode"] = values["operating_mode"].lower()
    faults = values["faults"].strip()
    data["faults"] = [] if faults.upper() == "NONE" else [item.strip().upper() for item in faults.split(",") if item.strip()]
    return data


def friendly_summary(data: dict[str, Any]) -> str:
    pump = "Running" if data["running"] else "Stopped"
    inverter = "Online" if data["available"] else "Offline"
    power_kw = data["ac_power_w"] / 1000
    faults = ", ".join(data["faults"]) if data["faults"] else "None"
    return "\n".join((
        f"Inverter {data['inverter_id']} — {pump} ({inverter})",
        f"Power: {power_kw:.2f} kW | Output: {data['ac_voltage_v']:.1f} V at {data['frequency_hz']:.1f} Hz",
        f"Solar input: {data['dc_voltage_v']:.1f} V | Current: {data['current_a']:.1f} A",
        f"Battery: {data['battery_percent']:.0f}% | Water level: {data['water_level_percent']:.0f}%",
        f"Temperature: {data['temperature_c']:.1f} °C | Pump speed: {data['rotation_rpm']:.0f} RPM",
        f"Flow: {data['pump_flow_m3h']:.1f} m³/h | Pressure: {data['pump_pressure_bar']:.1f} bar",
        f"Today: {data['daily_energy_kwh']:.1f} kWh | Total: {data['total_energy_kwh']:.1f} kWh",
        f"Faults: {faults}",
    ))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=Path("real_inverter_data.txt"))
    parser.add_argument("--summary", action="store_true", help="print a concise operator/bot preview")
    args = parser.parse_args()
    data = normalize(read_key_values(args.input))
    print(friendly_summary(data) if args.summary else json.dumps(data, separators=(",", ":")))


if __name__ == "__main__":
    main()
