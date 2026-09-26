#include <array>
#include <cstdint>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <cstdlib>
#include <netdb.h>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <openssl/evp.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>

constexpr int kPort = 1883; constexpr char kTopic[] = "inv/1/encrypted"; constexpr char kTelemetryTopic[] = "agribot/inverter/telemetry"; constexpr char kPassphrase[] = "change-this-demo-passphrase";
void appendLength(std::vector<std::uint8_t>& out, std::size_t n) { do { auto b = static_cast<std::uint8_t>(n % 128); n /= 128; if (n) b |= 0x80; out.push_back(b); } while (n); }
void putString(std::vector<std::uint8_t>& out, const std::string& s) { out.push_back(s.size() >> 8); out.push_back(s.size()); out.insert(out.end(), s.begin(), s.end()); }
void sendAll(int fd, const std::vector<std::uint8_t>& b) { for (std::size_t p = 0; p < b.size();) { auto n = send(fd, b.data() + p, b.size() - p, 0); if (n <= 0) throw std::runtime_error("MQTT socket write failed"); p += n; } }
void receiveAll(int fd, std::uint8_t* b, std::size_t n) { for (std::size_t p = 0; p < n;) { auto got = recv(fd, b + p, n - p, 0); if (got <= 0) throw std::runtime_error("MQTT socket read failed"); p += got; } }
std::vector<std::uint8_t> receivePacket(int fd) { std::uint8_t first; receiveAll(fd, &first, 1); std::vector<std::uint8_t> out{first}; std::size_t length = 0, mult = 1; for (int i = 0; i < 4; ++i) { std::uint8_t b; receiveAll(fd, &b, 1); out.push_back(b); length += (b & 127) * mult; if (!(b & 128)) { std::vector<std::uint8_t> body(length); receiveAll(fd, body.data(), length); out.insert(out.end(), body.begin(), body.end()); return out; } mult *= 128; } throw std::runtime_error("Invalid MQTT remaining length"); }
void connectMqtt(int fd) { std::vector<std::uint8_t> body; putString(body, "MQTT"); body.insert(body.end(), {4, 2, 0, 60}); putString(body, "nttq-broker"); std::vector<std::uint8_t> p{0x10}; appendLength(p, body.size()); p.insert(p.end(), body.begin(), body.end()); sendAll(fd, p); const auto reply = receivePacket(fd); if (reply.size() != 4 || reply[0] != 0x20 || reply[3] != 0) throw std::runtime_error("Mosquitto rejected CONNECT"); }
std::array<std::uint8_t, 32> keyFrom(const std::uint8_t* salt) { std::array<std::uint8_t, 32> key{}; if (PKCS5_PBKDF2_HMAC(kPassphrase, -1, salt, 16, 100000, EVP_sha256(), key.size(), key.data()) != 1) throw std::runtime_error("Key derivation failed"); return key; }
std::vector<std::uint8_t> decrypt(const std::vector<std::uint8_t>& record) { if (record.size() < 51) throw std::runtime_error("Encrypted message is too short"); const auto key = keyFrom(record.data()); const auto* iv = record.data() + 16; const auto* tag = record.data() + 28; const auto* cipher = record.data() + 44; const auto size = record.size() - 44; std::vector<std::uint8_t> plain(size); EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new(); if (!ctx) throw std::runtime_error("Decryption context failed"); int n = 0, last = 0; const bool ok = EVP_DecryptInit_ex(ctx, EVP_aes_256_gcm(), nullptr, key.data(), iv) == 1 && EVP_DecryptUpdate(ctx, plain.data(), &n, cipher, size) == 1 && EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_TAG, 16, const_cast<std::uint8_t*>(tag)) == 1 && EVP_DecryptFinal_ex(ctx, plain.data() + n, &last) == 1; EVP_CIPHER_CTX_free(ctx); if (!ok) throw std::runtime_error("Authentication failed: message was altered or key is wrong"); plain.resize(n + last); return plain; }
std::vector<std::uint8_t> publishPayload(const std::vector<std::uint8_t>& p) { std::size_t pos = 1, rem = 0, mult = 1; std::uint8_t b; do { b = p.at(pos++); rem += (b & 127) * mult; mult *= 128; } while (b & 128); if ((p[0] & 0xf0) != 0x30 || pos + rem != p.size()) throw std::runtime_error("Expected MQTT PUBLISH"); const auto topicSize = (p.at(pos) << 8) | p.at(pos + 1); pos += 2; if (pos + topicSize > p.size()) throw std::runtime_error("Malformed MQTT topic"); const std::string topic(p.begin() + pos, p.begin() + pos + topicSize); if (topic != kTopic) throw std::runtime_error("Unexpected MQTT topic"); pos += topicSize; return {p.begin() + pos, p.end()}; }
void publishTelemetry(int fd, const std::vector<std::uint8_t>& plain) {
    std::vector<std::uint8_t> body;
    putString(body, kTelemetryTopic);
    body.insert(body.end(), plain.begin(), plain.end());
    std::vector<std::uint8_t> packet{0x30};
    appendLength(packet, body.size());
    packet.insert(packet.end(), body.begin(), body.end());
    sendAll(fd, packet);
}
std::string progressBar(int percent) {
    constexpr int width = 24;
    const int filled = percent * width / 100;
    return "[" + std::string(filled, '#') + std::string(width - filled, '-') + "] " + std::to_string(percent) + "%";
}
std::string currentTime() {
    const std::time_t now = std::time(nullptr); std::tm local{};
    localtime_r(&now, &local);
    char text[32]; std::strftime(text, sizeof(text), "%Y-%m-%d %H:%M:%S", &local);
    return text;
}
void showDashboard(std::size_t processed, std::size_t encryptedSize, std::size_t telemetrySize,
                   int progress, const std::string& updatedAt, const std::string& status) {
    constexpr int width = 54;
    const auto row = [](const std::string& text) {
        std::cout << "| " << std::left << std::setw(width - 2) << text << "|\n";
    };
    std::cout << "\033[2J\033[H+" << std::string(width, '-') << "+\n";
    row("📥 MOSQUITTO BROKER DASHBOARD");
    std::cout << "+" << std::string(width, '-') << "+\n";
    row("🔐 Last encrypted packet: " + std::to_string(encryptedSize) + " bytes");
    row("📡 Last telemetry packet: " + std::to_string(telemetrySize) + " bytes");
    row("📦 Packets processed: " + std::to_string(processed));
    std::cout << "+" << std::string(width, '-') << "+\n";
    row("🚀 Forwarded: " + progressBar(progress));
    row("🕒 Last update: " + updatedAt);
    row(status);
    std::cout << "+" << std::string(width, '-') << "+\n" << std::flush;
}
int main() { try {
    std::cout.setf(std::ios::unitbuf);
    const char* host = std::getenv("MQTT_HOST"); if (!host) host = "127.0.0.1";
    addrinfo hints{}; hints.ai_family = AF_UNSPEC; hints.ai_socktype = SOCK_STREAM; addrinfo* addresses = nullptr;
    if (getaddrinfo(host, "1883", &hints, &addresses) != 0) throw std::runtime_error("Cannot resolve MQTT_HOST");
    const int fd = socket(addresses->ai_family, addresses->ai_socktype, addresses->ai_protocol);
    if (fd < 0 || connect(fd, addresses->ai_addr, addresses->ai_addrlen) != 0) { freeaddrinfo(addresses); throw std::runtime_error("Cannot connect to Mosquitto on port 1883"); }
    freeaddrinfo(addresses); connectMqtt(fd); std::vector<std::uint8_t> body{0, 1}; putString(body, kTopic); body.push_back(0); std::vector<std::uint8_t> sub{0x82}; appendLength(sub, body.size()); sub.insert(sub.end(), body.begin(), body.end()); sendAll(fd, sub); receivePacket(fd);
    std::size_t processed = 0, encryptedSize = 0, telemetrySize = 0;
    std::string lastUpdate = "--";
    showDashboard(processed, encryptedSize, telemetrySize, 0, lastUpdate, "🟡 Status: Waiting for data");
    for (;;) {
        const auto packet = receivePacket(fd);
        if ((packet.front() & 0xf0) != 0x30) continue;
        try {
            const auto encryptedRecord = publishPayload(packet);
            showDashboard(processed, encryptedRecord.size(), telemetrySize, 0, lastUpdate, "🟡 Status: Processing");
            const auto plain = decrypt(encryptedRecord);
            if (plain.size() < 2 || plain.size() > 4096 || plain.front() != '{' || plain.back() != '}') throw std::runtime_error("Invalid decrypted telemetry JSON");
            publishTelemetry(fd, plain);
            ++processed;
            encryptedSize = encryptedRecord.size();
            telemetrySize = plain.size();
            lastUpdate = currentTime();
            showDashboard(processed, encryptedSize, telemetrySize, 100, lastUpdate, "🟢 Status: Normal");
        } catch (const std::exception& e) {
            showDashboard(processed, encryptedSize, telemetrySize, 0, currentTime(), "🔴 Status: Invalid packet");
        }
    }
} catch (const std::exception& e) { std::cerr << "Broker error: " << e.what() << '\n'; return 1; } }
