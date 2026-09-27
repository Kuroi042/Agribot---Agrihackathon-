# 🌱 Smart Agricultural Supervision System

A **low-cost IoT agricultural monitoring system** developed for **AgriHackathon Morocco 2026** under the **AgriNovators** team, with contributions from **[hafidara](https://github.com/hafidara)** and **[Nabil](https://github.com/theswoord)**.

The system allows farmers and supervisors to monitor farm equipment remotely through a **Telegram bot**. Field telemetry is collected using **LoRa**, transmitted through **MQTT** to a **Mosquitto broker**, then authenticated, decrypted, and processed before being delivered to Telegram [link](https://t.me/Theswoord_bot).

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

### 👥 Team

**AgriNovators**
AgriHackathon Morocco 2026
