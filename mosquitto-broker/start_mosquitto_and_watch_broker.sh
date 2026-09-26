#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

# Start Mosquitto; its image also contains the decrypting nttq broker.
docker compose up -d --build

echo "Mosquitto and its embedded nttq broker are running. Waiting for output..."
echo "In another terminal, run:"
echo "  bash \"$script_dir/../nttq/run_encrypted_mqtt_demo.sh\""
echo

docker compose logs -f mosquitto
