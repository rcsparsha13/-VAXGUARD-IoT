#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <SPI.h>
#include <MFRC522.h>

// ==========================================
// 1. CONFIGURATION (UPDATE THESE!)
// ==========================================
const char* ssid = "Y58 5G";          
const char* password = "12345678";      
// 🚨 REPLACE WITH YOUR LAPTOP'S IP ADDRESS 🚨
const String serverURL = "http://10.201.147.194:5000/api/hardware_update"; 

// ==========================================
// 2. HARDWARE PINS
// ==========================================
#define TEMP_PIN       5   
#define DHTTYPE        DHT11 
#define BUZZER_PIN     25 

#define PIN_VACCINE    26 
#define PIN_BLOOD      32
#define PIN_INSULIN    27

#define SS_STAFF_PIN   21
#define RST_STAFF_PIN  22

MFRC522 rfidStaff(SS_STAFF_PIN, RST_STAFF_PIN); 
DHT dht(TEMP_PIN, DHTTYPE);

// ==========================================
// 3. SYSTEM STATE MEMORY
// ==========================================
unsigned long lastTelemetryTime = 0;
const unsigned long telemetryInterval = 5000; 

unsigned long lastSerialPrintTime = 0;
const unsigned long serialPrintInterval = 2000; 

unsigned long lastDhtTime = 0;

float baselineTemp = 0.0; // Captured once on startup
float lastTemp = 4.0; 
float lastHum = 50.0;

bool prevVac = LOW;
bool prevBlood = LOW;
bool prevIns = LOW;

void setup() {
  Serial.begin(115200); 
  SPI.begin(); 
  rfidStaff.PCD_Init();
  
  dht.begin();
  delay(2000); // Wait for sensor to wake up
  
  // 🚨 CAPTURE THE EXACT BASELINE ROOM TEMPERATURE 🚨
  baselineTemp = dht.readTemperature();
  if (isnan(baselineTemp)) baselineTemp = 28.0; // Fallback if sensor is slow
  
  pinMode(PIN_VACCINE, INPUT_PULLUP);
  pinMode(PIN_BLOOD, INPUT_PULLUP);
  pinMode(PIN_INSULIN, INPUT_PULLUP);
  
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW); 
  
  prevVac = digitalRead(PIN_VACCINE);
  prevBlood = digitalRead(PIN_BLOOD);
  prevIns = digitalRead(PIN_INSULIN);

  Serial.println("\n=========================================");
  Serial.println("🏥 VaxGuard Edge-Node Booting...");
  Serial.print("Initial Room Baseline Temp: "); Serial.print(baselineTemp); Serial.println("C");
  Serial.println("=========================================");
  Serial.print("Connecting to Wi-Fi...");
  
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  
  Serial.println("\n📶 Connected! ESP32 IP: " + WiFi.localIP().toString());
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) return;

  String scannedTag = "";
  String newlyLiftedItem = "";

  // --- 1. SENSOR CONTINUOUS MATH MAPPING ---
  if (millis() - lastDhtTime >= 2000) {
    lastDhtTime = millis();
    float t = dht.readTemperature();
    float h = dht.readHumidity();
    
    if (!isnan(t)) { 
        // 1. Calculate exact decimal difference from startup
        float diff = t - baselineTemp;
        
        // 2. The Multiplier Formula: 
        // A 0.1C room change = 0.2C fridge change.
        // A 2.0C room change (holding sensor) = 4.0C fridge change (Triggers Alarm!)
        float simFridgeTemp = 4.0 + (diff * 2.0); 
        
        // 3. Keep it within realistic display boundaries (2.0C to 15.0C)
        lastTemp = constrain(simFridgeTemp, 2.0, 15.0); 
        
        lastHum = isnan(h) ? 50.0 : h; 
    }
  }

  // --- 2. JUMPER EDGE DETECTION ---
  bool currVac = digitalRead(PIN_VACCINE);
  bool currBlood = digitalRead(PIN_BLOOD);
  bool currIns = digitalRead(PIN_INSULIN);

  if (currVac == HIGH && prevVac == LOW) newlyLiftedItem = "Hep-B Vaccine";
  else if (currBlood == HIGH && prevBlood == LOW) newlyLiftedItem = "Blood (O-Negative)";
  else if (currIns == HIGH && prevIns == LOW) newlyLiftedItem = "Insulin (Type 1)";

  prevVac = currVac; prevBlood = currBlood; prevIns = currIns;

  // --- 3. RFID SCANNER ---
  if (rfidStaff.PICC_IsNewCardPresent() && rfidStaff.PICC_ReadCardSerial()) {
    for (byte i = 0; i < rfidStaff.uid.size; i++) {
        scannedTag += String(rfidStaff.uid.uidByte[i] < 0x10 ? "0" : "");
        scannedTag += String(rfidStaff.uid.uidByte[i], HEX);
    }
    scannedTag.toUpperCase();
    Serial.println("\n🔔 [EVENT] RFID Scanned: " + scannedTag);
    rfidStaff.PICC_HaltA(); 
  }

  // --- 4. LIVE SERIAL MONITOR CONSOLE ---
  if (millis() - lastSerialPrintTime >= serialPrintInterval) {
    lastSerialPrintTime = millis();
    // Prints Real Temp -> Simulated Fridge Temp
    Serial.printf("[LIVE] Real: %.1fC -> Fridge: %.1fC | Hum: %.1f%% | Vac:%s | Blood:%s | Ins:%s\n", 
                  dht.readTemperature(), lastTemp, lastHum, currVac?"LIFT":"SAFE", currBlood?"LIFT":"SAFE", currIns?"LIFT":"SAFE");
  }

  // --- 5. NETWORK SYNC ---
  bool timeToSend = (millis() - lastTelemetryTime >= telemetryInterval);
  if (scannedTag != "" || newlyLiftedItem != "" || timeToSend) {
    lastTelemetryTime = millis();
    sendDataToDashboard(scannedTag, newlyLiftedItem, lastTemp, lastHum);
  }
  
  delay(50); // Anti-jitter debounce
}

void sendDataToDashboard(String tag, String liftedItem, float temp, float hum) {
  if (liftedItem != "") Serial.println("\n📦 [EVENT] LIFT DETECTED: " + liftedItem);
  
  HTTPClient http;
  http.begin(serverURL);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<256> doc;
  if(tag != "") doc["tag_id"] = tag;
  if(liftedItem != "") doc["lifted_item"] = liftedItem;
  doc["temperature"] = temp;
  doc["humidity"] = hum;

  String jsonString;
  serializeJson(doc, jsonString);
  int httpCode = http.POST(jsonString);
  
  if (httpCode == 200) {
    StaticJsonDocument<256> reply;
    deserializeJson(reply, http.getString());
    int buzzerPattern = reply["buzzer_pattern"];
    triggerBuzzer(buzzerPattern);
  } else {
    Serial.println("❌ [ERROR] Network Sync Failed. HTTP " + String(httpCode));
  }
  http.end();
}

void triggerBuzzer(int pattern) {
  if (pattern == 0) return; 
  
  Serial.print("🔊 [ALARM TRIGGERED] Pattern ID: "); Serial.println(pattern);
  
  switch(pattern) {
    case 1: // SPOILED ASSET
      digitalWrite(BUZZER_PIN, HIGH); delay(3000); digitalWrite(BUZZER_PIN, LOW); break;
    case 2: // LOW STOCK
      for(int i=0; i<2; i++) { digitalWrite(BUZZER_PIN, HIGH); delay(150); digitalWrite(BUZZER_PIN, LOW); delay(150); } break;
    case 3: // UNAUTHENTICATED
      for(int i=0; i<5; i++) { digitalWrite(BUZZER_PIN, HIGH); delay(100); digitalWrite(BUZZER_PIN, LOW); delay(100); } break;
    case 4: // INTRUDER
      for(int i=0; i<3; i++) { digitalWrite(BUZZER_PIN, HIGH); delay(600); digitalWrite(BUZZER_PIN, LOW); delay(400); } break;
    case 5: // MISMATCH
      for(int i=0; i<3; i++) { digitalWrite(BUZZER_PIN, HIGH); delay(300); digitalWrite(BUZZER_PIN, LOW); delay(200); } break;
  }
}