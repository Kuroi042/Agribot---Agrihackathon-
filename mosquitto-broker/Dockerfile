FROM eclipse-mosquitto:2

RUN apk add --no-cache g++ openssl-dev

WORKDIR /opt/mosquitto-broker
COPY mtt_broker.cpp .
RUN g++ -std=c++17 -O2 -Wall -Wextra -Wpedantic mtt_broker.cpp -lcrypto -o mtt_broker

COPY container-entrypoint.sh /usr/local/bin/container-entrypoint.sh
RUN chmod +x /usr/local/bin/container-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/container-entrypoint.sh"]
