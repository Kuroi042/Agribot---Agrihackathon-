#!/usr/bin/env bash
set -euo pipefail

# Publish the current inverter file every five seconds.  Resolve all paths from
# this script, so it can be launched from any working directory.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
inverter_file="${1:-$script_dir/inverter_data.txt}"
publish_interval_seconds="${PUBLISH_INTERVAL_SECONDS:-5}"

if [[ ! -f "$inverter_file" ]]; then
    echo "Inverter data file not found: $inverter_file" >&2
    exit 1
fi

g++ -std=c++17 -Wall -Wextra -Wpedantic "$script_dir/nttq_data.cpp" -lcrypto -o "$script_dir/nttq_data"

while true; do
    "$script_dir/nttq_data" "$inverter_file"
    for ((remaining = publish_interval_seconds; remaining > 0; remaining--)); do
        elapsed=$((publish_interval_seconds - remaining))
        filled=$((elapsed * 24 / publish_interval_seconds))
        empty=$((24 - filled))
        printf -v completed '%*s' "$filled" ''
        printf -v pending '%*s' "$empty" ''
        printf '\r⏳ Next send in %ds [%s%s] %d%%' \
            "$remaining" "${completed// /#}" "${pending// /-}" "$((elapsed * 100 / publish_interval_seconds))"
        sleep 1
    done
    printf '\r⏳ Next send in 0s  [########################] 100%%\n'
done
