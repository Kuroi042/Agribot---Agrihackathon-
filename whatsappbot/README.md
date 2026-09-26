# AgriBot inverter monitor

Two processes cooperate through a small SQLite database:

- `mqtt_ingestor.py` receives telemetry, validates it, and derives faults.
- `bot.py` provides the Telegram status and control menu and publishes commands.

## MQTT contract

The decrypting Mosquitto broker publishes validated JSON to
`agribot/inverter/telemetry` on MQTT port `1883`:

```json
{"inverter_id":1,"dc_voltage_v":378.5,"ac_voltage_v":230,"ac_power_w":2450,"frequency_hz":50,"current_a":10.7,"power_factor":0.95,"battery_percent":82,"temperature_c":34.5,"rotation_rpm":1450,"water_level_percent":62,"status":1,"running":true,"available":true,"faults":[]}
```

Set the fields in `../nttq/inverter_data.txt`. The sender rejects values outside
these input ranges: DC voltage 0–1000 V, AC voltage 0–300 V, frequency 0–60 Hz,
current 0–500 A, power factor 0–1, battery/water 0–100%, temperature −40–125 °C,
and rotation 0–10,000 RPM. These are application validation limits, not a
certification claim for a particular electrical standard.

Device fault codes are comma-separated in `faults`, for example
`OVER_TEMPERATURE,LOW_WATER`. They appear in the Telegram **Show faults** view.

The bot publishes control messages to `agribot/inverter/command`:

```json
{"command":"set_speed","value":47,"unit":"Hz","timestamp":"...","source":"telegram"}
```

Other command values are `start` and `stop`. The inverter/PLC bridge must subscribe
to the command topic, enforce hardware safety limits, and acknowledge commands at
the device level before this is used on a real pump.

## Run on Windows

Copy `.env.example` to `.env`, then add the Telegram token and MQTT details. In two
PowerShell terminals run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe mqtt_ingestor.py
```

```powershell
.\.venv\Scripts\python.exe bot.py
```

The scripts load `.env` automatically; `set -a` and `source` are not needed.
