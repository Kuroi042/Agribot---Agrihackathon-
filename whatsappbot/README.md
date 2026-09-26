# AgriBot inverter monitor

Two processes cooperate through a small SQLite database:

- `mqtt_ingestor.py` receives telemetry, validates it, and derives faults.
- `bot.py` provides the Telegram status and control menu and publishes commands.

## MQTT contract

Publish compact JSON to `agribot/inverter/telemetry`:

```json
{"frequency_hz":50,"dc_voltage_v":750,"current_a":35,"running":true,"available":true,"rotation_rpm":1450,"water_level_percent":62,"faults":[]}
```

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
