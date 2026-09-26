#include <array>
#include <algorithm>
#include <cctype>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <stdexcept>
#include <sstream>
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

std::map<std::string, std::string> readValues(const std::string& path) {
    std::ifstream in(path); if (!in) throw std::runtime_error("Cannot open " + path);
    std::map<std::string, std::string> values; std::string line;
    while (std::getline(in, line)) { if (line.empty() || line[0] == '#') continue; const auto eq = line.find('='); if (eq != std::string::npos) values[line.substr(0, eq)] = line.substr(eq + 1); }
    return values;
}
const std::string& required(const std::map<std::string, std::string>& values, const char* key) {
    const auto it = values.find(key);
    if (it == values.end()) throw std::runtime_error(std::string("Missing ") + key);
    return it->second;
}
double measurement(const std::map<std::string, std::string>& values, const char* key, double minimum, double maximum) {
    const double value = std::stod(required(values, key));
    if (value < minimum || value > maximum) throw std::runtime_error(std::string(key) + " is outside its permitted range");
    return value;
}
bool flag(const std::map<std::string, std::string>& values, const char* key, bool fallback) {
    const auto it = values.find(key); if (it == values.end()) return fallback;
    if (it->second == "true" || it->second == "1") return true;
    if (it->second == "false" || it->second == "0") return false;
    throw std::runtime_error(std::string(key) + " must be true or false");
}
std::string faultsJson(const std::map<std::string, std::string>& values) {
    const auto it = values.find("faults"); if (it == values.end() || it->second.empty() || it->second == "NONE") return "[]";
    std::stringstream source(it->second); std::string fault, output = "["; bool first = true;
    while (std::getline(source, fault, ',')) {
        fault.erase(std::remove_if(fault.begin(), fault.end(), [](unsigned char c) { return std::isspace(c); }), fault.end());
        if (fault.empty() || !std::all_of(fault.begin(), fault.end(), [](unsigned char c) { return std::isalnum(c) || c == '_'; })) throw std::runtime_error("faults must be comma-separated error codes");
        if (!first) output += ',';
        output += '"' + fault + '"';
        first = false;
    }
    return output + ']';
}
std::vector<std::uint8_t> loadTelemetry(const std::string& path) {
    const auto values = readValues(path);
    const auto id = static_cast<unsigned>(measurement(values, "inverter_id", 1, 255));
    const auto voltage = measurement(values, "dc_voltage_v", 0, 1000);
    const auto acVoltage = measurement(values, "ac_voltage_v", 0, 300);
    const auto power = measurement(values, "ac_power_w", 0, 65535);
    const auto frequency = measurement(values, "frequency_hz", 0, 60);
    const auto current = measurement(values, "current_a", 0, 500);
    const auto factor = measurement(values, "power_factor", 0, 1);
    const auto battery = measurement(values, "battery_percent", 0, 100);
    const auto temperature = measurement(values, "temperature_c", -40, 125);
    const auto rpm = measurement(values, "rotation_rpm", 0, 10000);
    const auto water = measurement(values, "water_level_percent", 0, 100);
    const auto status = static_cast<unsigned>(measurement(values, "status", 0, 255));
    const bool running = flag(values, "running", status != 0); const bool available = flag(values, "available", true);
    std::ostringstream json; json << std::fixed << std::setprecision(1)
        << "{\"inverter_id\":" << id << ",\"dc_voltage_v\":" << voltage << ",\"ac_voltage_v\":" << acVoltage
        << ",\"ac_power_w\":" << power << ",\"frequency_hz\":" << frequency << ",\"current_a\":" << current
        << ",\"power_factor\":" << factor << ",\"battery_percent\":" << battery << ",\"temperature_c\":" << temperature
        << ",\"rotation_rpm\":" << rpm << ",\"water_level_percent\":" << water << ",\"status\":" << status
        << ",\"running\":" << (running ? "true" : "false") << ",\"available\":" << (available ? "true" : "false")
        << ",\"faults\":" << faultsJson(values) << '}';
    const auto text = json.str(); return {text.begin(), text.end()};
}
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
        const auto telemetry = loadTelemetry(argc > 1 ? argv[1] : "inverter_data.txt"); const auto encrypted = encrypt(telemetry);
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
