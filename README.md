Smart Agricultural Supervision System

This project is a low-cost IoT-based agricultural supervision system designed to monitor farm equipment and field conditions remotely through a simple Telegram interface.

The system uses LoRa communication to collect telemetry and sensor data from devices deployed in the field. The collected data is transmitted as MQTT packets through a LoRa gateway to an MQTT broker (Mosquitto).

The MQTT broker acts as the central communication layer, receiving and routing the incoming messages to the monitoring application. The application then authenticates and decrypts the protected payload, validates the received data, processes the telemetry, and converts it into meaningful information.

The processed information is made available through a Telegram bot, allowing the farmer or supervisor to monitor the farm remotely without requiring a dedicated mobile application.

The Telegram bot can provide:

📊 Real-time equipment and sensor telemetry
💧 Irrigation and water-related information
⚡ Equipment operating status
🚨 Fault and abnormal-condition alerts
📈 Statistics and historical measurements
📋 Daily and periodic farm reports
🔧 Equipment fault codes and diagnostic information
📡 Remote monitoring through a simple Telegram interface
System Architecture

Field Sensors / Equipment
↓
LoRa Communication
↓
LoRa Gateway
↓
MQTT Packets
↓
Mosquitto MQTT Broker
↓
Authentication / Decryption / Data Processing
↓
Monitoring Application
↓
Telegram Bot
↓
Farmer / Supervisor

The main objective is to provide farmers and agricultural supervisors with an affordable, lightweight, and easy-to-use monitoring solution that avoids the complexity and cost of traditional farm-management platforms.

Instead of requiring users to continuously access a dedicated dashboard, the system delivers important information directly through Telegram, making farm supervision accessible from a standard smartphone.
