#!/usr/bin/env bash
set -euo pipefail

# Publish the current inverter file every five seconds.  Resolve all paths from
# this script, so it can be launched from any working directory.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
inverter_file="${1:-$script_dir/inverter_data.txt}"

if [[ ! -f "$inverter_file" ]]; then
    echo "Inverter data file not found: $inverter_file" >&2
    exit 1
fi

g++ -std=c++17 -Wall -Wextra -Wpedantic "$script_dir/nttq_data.cpp" -lcrypto -o "$script_dir/nttq_data"

echo "Publishing $inverter_file to MQTT every 5 seconds (Ctrl-C to stop)."
while true; do
    "$script_dir/nttq_data" "$inverter_file"
    sleep 5
done
