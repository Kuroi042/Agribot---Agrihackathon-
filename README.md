# 🌱 Smart Agricultural Supervision System

A **low-cost IoT agricultural monitoring system** that allows farmers and supervisors to monitor farm equipment remotely through a **Telegram bot**.

The system collects telemetry from field devices using **LoRa**, forwards the data through **MQTT** to a **Mosquitto broker**, then authenticates, decrypts, and processes the data before sending useful information to Telegram.

### 🚀 Features

* 📡 LoRa-based field communication
* 📦 MQTT & Mosquitto messaging
* 🔐 Data authentication and decryption
* 📊 Real-time telemetry and statistics
* 💧 Irrigation monitoring
* ⚡ Equipment status
* 🚨 Fault detection and alerts
* 📋 Automated reports
* 🤖 Telegram-based supervision

### 🏗️ Architecture

```text
Sensors / Equipment
        ↓
      LoRa
        ↓
   LoRa Gateway
        ↓
      MQTT
        ↓
Mosquitto Broker
        ↓
Authentication
& Decryption
        ↓
 Data Processing
        ↓
   Telegram Bot
        ↓
Farmer / Supervisor
```

### 🎯 Objective

Provide farmers with a **simple, affordable, and accessible farm supervision system** without requiring a dedicated mobile application.

**LoRa → MQTT → Mosquitto → Processing → Telegram**
