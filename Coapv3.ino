#include <ESP8266WiFi.h>
#include <WiFiUdp.h>
#include <coap-simple.h>
#include <Crypto.h>
#include <SHA256.h>
#include <string.h>

const char* ssid     = "Galaxy A52s 5GA70C";
const char* password = "isqf5725";

IPAddress serverIP(10, 17, 253, 229);   // Raspberry Pi
const int serverPort = 5683;         // CoAP port

// Chiave segreta condivisa (deve corrispondere al server)
const char* SECRET_KEY = "super_secret_key";

WiFiUDP udp;
Coap coap(udp);



String hmacSHA256(const char* key, const char* message) {
    uint8_t keyBlock[64];
    memset(keyBlock, 0, 64);

    size_t keyLen = strlen(key);

    // Se la chiave è più lunga di 64 byte → prima hash
    if (keyLen > 64) {
        SHA256 sha;
        sha.reset();
        sha.update((const uint8_t*)key, keyLen);
        sha.finalize(keyBlock, 32);
    } else {
        memcpy(keyBlock, key, keyLen);
    }

    uint8_t o_key_pad[64];
    uint8_t i_key_pad[64];

    for (int i = 0; i < 64; i++) {
        o_key_pad[i] = keyBlock[i] ^ 0x5c;
        i_key_pad[i] = keyBlock[i] ^ 0x36;
    }

    // Inner hash
    SHA256 shaInner;
    shaInner.reset();
    shaInner.update(i_key_pad, 64);
    shaInner.update((const uint8_t*)message, strlen(message));

    uint8_t innerHash[32];
    shaInner.finalize(innerHash, 32);

    // Outer hash
    SHA256 shaOuter;
    shaOuter.reset();
    shaOuter.update(o_key_pad, 64);
    shaOuter.update(innerHash, 32);

    uint8_t hmacResult[32];
    shaOuter.finalize(hmacResult, 32);

    // Converti in hex
    String mac = "";
    for (int i = 0; i < 32; i++) {
        if (hmacResult[i] < 0x10) mac += "0";
        mac += String(hmacResult[i], HEX);
    }
    mac.toLowerCase();
    return mac;
}

String calculateHMAC(int value){
  String message = String(value);
  return hmacSHA256(SECRET_KEY, message.c_str());
}

void setup() {
  Serial.begin(9600);

  WiFi.begin(ssid, password);
  Serial.print("Connecting");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nConnected!");
  Serial.println(WiFi.localIP());

  randomSeed(analogRead(A0));  // randomness to generate temperature
  coap.start();
}

void loop() {
  int temperature = random(70, 90);

  // Calcola il MAC per il valore della temperatura
  String mac = calculateHMAC(temperature);

  // Crea il payload JSON con temperatura e MAC
  char payload[120];
  sprintf(payload, "{\"Temperature\": %d, \"mac\": \"%s\"}", temperature, mac.c_str());

  coap.put(serverIP, serverPort, "temperature", payload);

  Serial.print("Sent: ");
  Serial.println(payload);

  delay(2000);
}