#!/usr/bin/env bash
set -euo pipefail

# Start Mosquitto plus the broker container, rebuilding the broker if needed.
docker compose up -d --build

echo "Mosquitto and nttq-broker are running. Waiting for broker output..."
echo "In another terminal, run:"
echo "  cd /home/kenshin/Desktop/DataProject/nttq && bash run_encrypted_mqtt_demo.sh"
echo

docker compose logs -f broker
