#!/usr/bin/env python3
"""Explain the inverter fault codes in a telemetry key/value file.

Usage:
  python3 check_inverter_faults.py real_inverter_data.txt
  python3 check_inverter_faults.py real_inverter_data.txt --json

Fault-code meanings vary by inverter manufacturer and model. Update FAULT_CATALOG
from the manual for the installed inverter before using it for field decisions.
"""

import argparse
import json
from pathlib import Path


FAULT_CATALOG = {
    "E056": {
        "title": "Low battery voltage",
        "description": "Battery charge is below the configured safe operating level.",
        "action": "Reduce pump demand and check battery charge, charging source, and terminals.",
    },
    "E065": {
        "title": "Inverter over-temperature",
        "description": "The inverter temperature is above its configured safe limit.",
        "action": "Reduce load or stop the pump; allow cooling and check airflow, fans, and enclosure temperature.",
    },
    "E070": {
        "title": "Low water level",
        "description": "The source-water level is below the configured safe limit.",
        "action": "Stop the pump or keep it stopped until the source-water level has recovered.",
    },
}


def read_fault_codes(path: Path) -> list[str]:
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("faults="):
            value = line.split("=", 1)[1].strip()
            return [] if not value or value.upper() == "NONE" else [code.strip().upper() for code in value.split(",") if code.strip()]
    raise ValueError("No faults= line was found")


def check_faults(codes: list[str]) -> list[dict[str, str]]:
    report = []
    for code in codes:
        details = FAULT_CATALOG.get(code)
        if details:
            report.append({"code": code, **details})
        else:
            report.append({
                "code": code,
                "title": "Unknown inverter fault",
                "description": "This code is not in the local fault catalog.",
                "action": "Check the inverter manufacturer manual and add the verified meaning to FAULT_CATALOG.",
            })
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Explain inverter fault codes.")
    parser.add_argument("input", nargs="?", type=Path, default=Path("real_inverter_data.txt"))
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args()
    report = check_faults(read_fault_codes(args.input))
    if args.json:
        print(json.dumps(report, indent=2))
    elif not report:
        print("No active inverter faults.")
    else:
        for item in report:
            print(f"{item['code']} — {item['title']}\n  {item['description']}\n  Action: {item['action']}")


if __name__ == "__main__":
    main()
