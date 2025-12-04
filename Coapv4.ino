#include <ESP8266WiFi.h>
#include <WiFiUdp.h>
#include <coap-simple.h>
#include <Crypto.h>
#include <SHA256.h>
#include <string.h>
#include <AES.h>
#include <AESLib.h>
#include <base64.h>


const char* ssid     = "Galaxy A52s 5GA70C";
const char* password = "isqf5725";

IPAddress serverIP(10, 17, 253, 229);   // Edge Computer
const int serverPort = 5683;         // CoAP port

// Creates secrete AES key
byte aes_key[16] = {
  0x30, 0x31, 0x32, 0x33,
  0x34, 0x35, 0x36, 0x37,
  0x38, 0x39, 0x61, 0x62,
  0x63, 0x64, 0x65, 0x66
};

byte aes_iv[16] = {  0x30, 0x31, 0x32, 0x33,
  0x34, 0x35, 0x36, 0x37,
  0x38, 0x39, 0x61, 0x62,
  0x63, 0x64, 0x65, 0x66 };


// Creates HMAC secret key
const char* SECRET_KEY = "super_secret_key";

WiFiUDP udp;
Coap coap(udp);

void generateIV(byte *iv) {
  for (int i = 0; i < 16; i++) {
      iv[i] = random(0, 256);
  }
}


String hmacSHA256(const char* key, const char* message) {
    uint8_t keyBlock[64];
    memset(keyBlock, 0, 64);

    size_t keyLen = strlen(key);

    // If the key is longer than 64 bytes hash
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

String aesEncrypt(String plaintext) {
  AES aes;

  int len = plaintext.length();
  int paddedLen = len + (16 - (len % 16));  // PKCS7 padding

  byte plain[paddedLen];
  memcpy(plain, plaintext.c_str(), len);

  // PKCS7
  byte padValue = paddedLen - len;
  for (int i = len; i < paddedLen; i++) {
      plain[i] = padValue;
  }

  byte iv[16];
  generateIV(iv);

  byte cipher[paddedLen];
  aes.do_aes_encrypt(plain, paddedLen, cipher, aes_key, 128, iv);

  // Concatena IV + ciphertext → il server deve usarlo
  byte finalBuffer[paddedLen + 16];
  memcpy(finalBuffer, iv, 16);
  memcpy(finalBuffer + 16, cipher, paddedLen);

  return base64::encode(finalBuffer, paddedLen + 16);
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

  String mac = calculateHMAC(temperature);

  char payload[120];
  sprintf(payload, "{\"Temperature\": %d, \"mac\": \"%s\"}", temperature, mac.c_str());

  String encrypted = aesEncrypt(payload);
Serial.println(encrypted.c_str());
  coap.put(serverIP, serverPort, "temperature", encrypted.c_str());

  Serial.println("Plaintext: " + String(payload));
  Serial.println("Encrypted: " + encrypted);

  delay(2000);
}