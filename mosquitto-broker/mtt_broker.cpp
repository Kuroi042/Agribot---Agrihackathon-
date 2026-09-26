#include <array>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <cstdlib>
#include <netdb.h>
#include <stdexcept>
#include <string>
#include <vector>
#include <openssl/evp.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>

constexpr int kPort = 1883; constexpr char kTopic[] = "inv/1/encrypted"; constexpr char kPassphrase[] = "change-this-demo-passphrase";
void appendLength(std::vector<std::uint8_t>& out, std::size_t n) { do { auto b = static_cast<std::uint8_t>(n % 128); n /= 128; if (n) b |= 0x80; out.push_back(b); } while (n); }
void putString(std::vector<std::uint8_t>& out, const std::string& s) { out.push_back(s.size() >> 8); out.push_back(s.size()); out.insert(out.end(), s.begin(), s.end()); }
void sendAll(int fd, const std::vector<std::uint8_t>& b) { for (std::size_t p = 0; p < b.size();) { auto n = send(fd, b.data() + p, b.size() - p, 0); if (n <= 0) throw std::runtime_error("MQTT socket write failed"); p += n; } }
void receiveAll(int fd, std::uint8_t* b, std::size_t n) { for (std::size_t p = 0; p < n;) { auto got = recv(fd, b + p, n - p, 0); if (got <= 0) throw std::runtime_error("MQTT socket read failed"); p += got; } }
std::vector<std::uint8_t> receivePacket(int fd) { std::uint8_t first; receiveAll(fd, &first, 1); std::vector<std::uint8_t> out{first}; std::size_t length = 0, mult = 1; for (int i = 0; i < 4; ++i) { std::uint8_t b; receiveAll(fd, &b, 1); out.push_back(b); length += (b & 127) * mult; if (!(b & 128)) { std::vector<std::uint8_t> body(length); receiveAll(fd, body.data(), length); out.insert(out.end(), body.begin(), body.end()); return out; } mult *= 128; } throw std::runtime_error("Invalid MQTT remaining length"); }
void connectMqtt(int fd) { std::vector<std::uint8_t> body; putString(body, "MQTT"); body.insert(body.end(), {4, 2, 0, 60}); putString(body, "nttq-broker"); std::vector<std::uint8_t> p{0x10}; appendLength(p, body.size()); p.insert(p.end(), body.begin(), body.end()); sendAll(fd, p); const auto reply = receivePacket(fd); if (reply.size() != 4 || reply[0] != 0x20 || reply[3] != 0) throw std::runtime_error("Mosquitto rejected CONNECT"); }
std::array<std::uint8_t, 32> keyFrom(const std::uint8_t* salt) { std::array<std::uint8_t, 32> key{}; if (PKCS5_PBKDF2_HMAC(kPassphrase, -1, salt, 16, 100000, EVP_sha256(), key.size(), key.data()) != 1) throw std::runtime_error("Key derivation failed"); return key; }
std::vector<std::uint8_t> decrypt(const std::vector<std::uint8_t>& record) { if (record.size() < 51) throw std::runtime_error("Encrypted message is too short"); const auto key = keyFrom(record.data()); const auto* iv = record.data() + 16; const auto* tag = record.data() + 28; const auto* cipher = record.data() + 44; const auto size = record.size() - 44; std::vector<std::uint8_t> plain(size); EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new(); if (!ctx) throw std::runtime_error("Decryption context failed"); int n = 0, last = 0; const bool ok = EVP_DecryptInit_ex(ctx, EVP_aes_256_gcm(), nullptr, key.data(), iv) == 1 && EVP_DecryptUpdate(ctx, plain.data(), &n, cipher, size) == 1 && EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_TAG, 16, const_cast<std::uint8_t*>(tag)) == 1 && EVP_DecryptFinal_ex(ctx, plain.data() + n, &last) == 1; EVP_CIPHER_CTX_free(ctx); if (!ok) throw std::runtime_error("Authentication failed: message was altered or key is wrong"); plain.resize(n + last); return plain; }
std::vector<std::uint8_t> publishPayload(const std::vector<std::uint8_t>& p) { std::size_t pos = 1, rem = 0, mult = 1; std::uint8_t b; do { b = p.at(pos++); rem += (b & 127) * mult; mult *= 128; } while (b & 128); if ((p[0] & 0xf0) != 0x30 || pos + rem != p.size()) throw std::runtime_error("Expected MQTT PUBLISH"); const auto topicSize = (p.at(pos) << 8) | p.at(pos + 1); pos += 2; if (pos + topicSize > p.size()) throw std::runtime_error("Malformed MQTT topic"); const std::string topic(p.begin() + pos, p.begin() + pos + topicSize); if (topic != kTopic) throw std::runtime_error("Unexpected MQTT topic"); pos += topicSize; return {p.begin() + pos, p.end()}; }
int main() { try {
    std::cout.setf(std::ios::unitbuf);
    const char* host = std::getenv("MQTT_HOST"); if (!host) host = "127.0.0.1";
    addrinfo hints{}; hints.ai_family = AF_UNSPEC; hints.ai_socktype = SOCK_STREAM; addrinfo* addresses = nullptr;
    if (getaddrinfo(host, "1883", &hints, &addresses) != 0) throw std::runtime_error("Cannot resolve MQTT_HOST");
    const int fd = socket(addresses->ai_family, addresses->ai_socktype, addresses->ai_protocol);
    if (fd < 0 || connect(fd, addresses->ai_addr, addresses->ai_addrlen) != 0) { freeaddrinfo(addresses); throw std::runtime_error("Cannot connect to Mosquitto on port 1883"); }
    freeaddrinfo(addresses); connectMqtt(fd); std::vector<std::uint8_t> body{0, 1}; putString(body, kTopic); body.push_back(0); std::vector<std::uint8_t> sub{0x82}; appendLength(sub, body.size()); sub.insert(sub.end(), body.begin(), body.end()); sendAll(fd, sub); receivePacket(fd);
    std::cout << "[receiver] Listening for encrypted MQTT data on " << kTopic << "...\n";
    for (;;) {
        const auto packet = receivePacket(fd);
        if ((packet.front() & 0xf0) != 0x30) continue;
        try {
            const auto encryptedRecord = publishPayload(packet);
            std::cout << "[receiver] Received encrypted MQTT payload (" << encryptedRecord.size() << " bytes). Starting decryption...\n";
            const auto plain = decrypt(encryptedRecord);
            if (plain.size() != 7) throw std::runtime_error("Invalid decrypted inverter payload");
            const auto voltage = static_cast<std::uint16_t>((plain[1] << 8) | plain[2]);
            const auto power = static_cast<std::uint16_t>((plain[3] << 8) | plain[4]);
            std::cout << std::fixed << std::setprecision(1)
                      << "Decrypted inverter data:\nInverter ID: " << static_cast<int>(plain[0])
                      << "\nDC voltage: " << voltage / 10.0 << " V\nAC power: " << power
                      << " W\nBattery: " << static_cast<int>(plain[5]) << " %\nStatus: "
                      << static_cast<int>(plain[6]) << "\n";
        } catch (const std::exception& e) {
            std::cerr << "[receiver] Ignoring invalid encrypted MQTT payload: " << e.what() << '\n';
        }
    }
} catch (const std::exception& e) { std::cerr << "Broker error: " << e.what() << '\n'; return 1; } }
