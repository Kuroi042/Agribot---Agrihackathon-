#include <array>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>
#include <openssl/evp.h>
#include <openssl/rand.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <sys/socket.h>
#include <unistd.h>

constexpr int kPort = 1883;
constexpr char kTopic[] = "inv/1/encrypted";
constexpr char kPassphrase[] = "change-this-demo-passphrase"; // Change in both programs.

struct Inverter { std::uint8_t id, battery, status; std::uint16_t voltageTenths, power; };

std::map<std::string, std::string> readValues(const std::string& path) {
    std::ifstream in(path); if (!in) throw std::runtime_error("Cannot open " + path);
    std::map<std::string, std::string> values; std::string line;
    while (std::getline(in, line)) { if (line.empty() || line[0] == '#') continue; const auto eq = line.find('='); if (eq != std::string::npos) values[line.substr(0, eq)] = line.substr(eq + 1); }
    return values;
}
Inverter loadInverter(const std::string& path) {
    const auto v = readValues(path); auto get = [&](const char* key) -> const std::string& { const auto it = v.find(key); if (it == v.end()) throw std::runtime_error(std::string("Missing ") + key); return it->second; };
    const double volts = std::stod(get("dc_voltage_v")); const auto power = std::stoul(get("ac_power_w")); const auto battery = std::stoul(get("battery_percent"));
    if (volts < 0 || volts > 6553.5 || power > 65535 || battery > 100) throw std::runtime_error("Inverter value is outside supported range");
    return {static_cast<std::uint8_t>(std::stoul(get("inverter_id"))), static_cast<std::uint8_t>(battery), static_cast<std::uint8_t>(std::stoul(get("status"))), static_cast<std::uint16_t>(volts * 10 + .5), static_cast<std::uint16_t>(power)};
}
std::vector<std::uint8_t> pack(const Inverter& d) { return {d.id, static_cast<std::uint8_t>(d.voltageTenths >> 8), static_cast<std::uint8_t>(d.voltageTenths), static_cast<std::uint8_t>(d.power >> 8), static_cast<std::uint8_t>(d.power), d.battery, d.status}; }
void appendLength(std::vector<std::uint8_t>& out, std::size_t n) { do { auto b = static_cast<std::uint8_t>(n % 128); n /= 128; if (n) b |= 0x80; out.push_back(b); } while (n); }
void putString(std::vector<std::uint8_t>& out, const std::string& s) { out.push_back(s.size() >> 8); out.push_back(s.size()); out.insert(out.end(), s.begin(), s.end()); }
void sendAll(int fd, const std::vector<std::uint8_t>& bytes) { for (std::size_t sent = 0; sent < bytes.size();) { const auto n = send(fd, bytes.data() + sent, bytes.size() - sent, 0); if (n <= 0) throw std::runtime_error("MQTT socket write failed"); sent += n; } }
void receiveAll(int fd, std::uint8_t* bytes, std::size_t size) { for (std::size_t got = 0; got < size;) { const auto n = recv(fd, bytes + got, size - got, 0); if (n <= 0) throw std::runtime_error("MQTT socket read failed"); got += n; } }
void connectMqtt(int fd) {
    std::vector<std::uint8_t> body; putString(body, "MQTT"); body.insert(body.end(), {4, 2, 0, 60}); putString(body, "nttq-producer");
    std::vector<std::uint8_t> packet{0x10}; appendLength(packet, body.size()); packet.insert(packet.end(), body.begin(), body.end()); sendAll(fd, packet);
    std::uint8_t reply[4]; receiveAll(fd, reply, 4); if (reply[0] != 0x20 || reply[1] != 2 || reply[3] != 0) throw std::runtime_error("Mosquitto rejected CONNECT");
}
std::array<std::uint8_t, 32> keyFrom(const std::array<std::uint8_t, 16>& salt) { std::array<std::uint8_t, 32> key{}; if (PKCS5_PBKDF2_HMAC(kPassphrase, -1, salt.data(), salt.size(), 100000, EVP_sha256(), key.size(), key.data()) != 1) throw std::runtime_error("Key derivation failed"); return key; }
std::vector<std::uint8_t> encrypt(const std::vector<std::uint8_t>& plain) {
    std::array<std::uint8_t, 16> salt{}; std::array<std::uint8_t, 12> iv{}; std::array<std::uint8_t, 16> tag{};
    if (RAND_bytes(salt.data(), salt.size()) != 1 || RAND_bytes(iv.data(), iv.size()) != 1) throw std::runtime_error("Secure random generation failed");
    const auto key = keyFrom(salt); std::vector<std::uint8_t> cipher(plain.size()); EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new(); if (!ctx) throw std::runtime_error("Encryption context failed"); int n = 0, last = 0;
    const bool ok = EVP_EncryptInit_ex(ctx, EVP_aes_256_gcm(), nullptr, key.data(), iv.data()) == 1 && EVP_EncryptUpdate(ctx, cipher.data(), &n, plain.data(), plain.size()) == 1 && EVP_EncryptFinal_ex(ctx, cipher.data() + n, &last) == 1 && EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_GET_TAG, tag.size(), tag.data()) == 1;
    EVP_CIPHER_CTX_free(ctx); if (!ok) throw std::runtime_error("Encryption failed"); cipher.resize(n + last);
    std::vector<std::uint8_t> result; result.insert(result.end(), salt.begin(), salt.end()); result.insert(result.end(), iv.begin(), iv.end()); result.insert(result.end(), tag.begin(), tag.end()); result.insert(result.end(), cipher.begin(), cipher.end()); return result;
}
void printHex(const std::vector<std::uint8_t>& bytes) {
    for (const auto byte : bytes)
        std::cout << std::hex << std::setw(2) << std::setfill('0') << static_cast<unsigned>(byte) << ' ';
    std::cout << std::dec << std::setfill(' ') << '\n';
}
int main(int argc, char** argv) {
    try {
        const auto inverter = loadInverter(argc > 1 ? argv[1] : "inverter_data.txt"); const auto encrypted = encrypt(pack(inverter));
        const char* host = std::getenv("MQTT_HOST"); if (!host) host = "127.0.0.1";
        addrinfo hints{}; hints.ai_family = AF_UNSPEC; hints.ai_socktype = SOCK_STREAM; addrinfo* addresses = nullptr;
        if (getaddrinfo(host, "1883", &hints, &addresses) != 0) throw std::runtime_error("Cannot resolve MQTT_HOST");
        const int fd = socket(addresses->ai_family, addresses->ai_socktype, addresses->ai_protocol);
        std::cout << "[debug] Connecting to Mosquitto at " << host << ':' << kPort << "...\n";
        if (fd < 0 || connect(fd, addresses->ai_addr, addresses->ai_addrlen) != 0) {
            freeaddrinfo(addresses);
            throw std::runtime_error("Cannot connect to Mosquitto on port 1883");
        }
        freeaddrinfo(addresses);
        connectMqtt(fd);
        std::cout << "[debug] MQTT CONNECT accepted by Mosquitto.\n";
        std::vector<std::uint8_t> body; putString(body, kTopic); body.insert(body.end(), encrypted.begin(), encrypted.end());
        std::vector<std::uint8_t> publish{0x30}; appendLength(publish, body.size()); publish.insert(publish.end(), body.begin(), body.end());
        std::cout << "[debug] Sending MQTT PUBLISH to topic '" << kTopic << "' (" << publish.size() << " bytes): "; printHex(publish);
        std::cout << "[debug] Encrypted payload (" << encrypted.size() << " bytes): "; printHex(encrypted);
        sendAll(fd, publish);
        std::cout << "[debug] MQTT PUBLISH socket write completed.\n";
        close(fd);
        std::cout << "Published encrypted inverter data to " << kTopic << ".\n";
    } catch (const std::exception& e) { std::cerr << "Producer error: " << e.what() << '\n'; return 1; }
}
