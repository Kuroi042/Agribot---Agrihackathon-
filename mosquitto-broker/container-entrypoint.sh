#!/bin/sh
set -eu

# Mosquitto receives the MQTT packets.  The subscriber below runs in this same
# container and decrypts each encrypted nttq message as it arrives.
mosquitto -c /mosquitto/config/mosquitto.conf &
mosquitto_pid=$!

cleanup() {
    kill "$mosquitto_pid" 2>/dev/null || true
    wait "$mosquitto_pid" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# Mosquitto needs a moment to bind port 1883.  If it is restarting, retry the
# local subscriber until the daemon is available again.
while kill -0 "$mosquitto_pid" 2>/dev/null; do
    /opt/mosquitto-broker/mtt_broker && exit 0
    echo "[receiver] MQTT connection closed; reconnecting in 1 second..." >&2
    sleep 1
done

wait "$mosquitto_pid"
