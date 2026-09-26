#!/usr/bin/env bash
set -euo pipefail

# Start the Mosquitto and broker containers manually before running this script.
# Example: cd ../mosquitto-broker && docker compose up -d
g++ -std=c++17 -Wall -Wextra -Wpedantic nttq_data.cpp -lcrypto -o nttq_data

./nttq_data inverter_data.txt
