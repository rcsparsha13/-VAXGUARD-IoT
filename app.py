import sqlite3
import time
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# --- GLOBAL MEMORY ---
active_patient = {"name": None, "required_item": None}
active_staff = {"name": None, "uid": None, "login_time": 0}
latest_temp = 4.0
latest_hum = 50.0
SESSION_SECONDS = 30

# The Auto-Learn Magic Hooks
VALID_STAFF_UID = "AUTO"  
INTRUDER_UID = "AUTO_INTRUDER"     

def get_db():
    conn = sqlite3.connect("hospital.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, quantity INTEGER, expiry_date TEXT, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY, timestamp DATETIME DEFAULT (datetime('now', 'localtime')), patient_name TEXT, expected_item TEXT, dispensed_item TEXT, dispensed_by TEXT, result TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY, timestamp DATETIME DEFAULT (datetime('now', 'localtime')), type TEXT, message TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sensor_logs (id INTEGER PRIMARY KEY, timestamp DATETIME DEFAULT (datetime('now', 'localtime')), temp_value REAL)''')

    if c.execute("SELECT COUNT(*) FROM inventory").fetchone()[0] == 0:
        c.execute("INSERT INTO inventory (name, quantity, expiry_date, status) VALUES ('Hep-B Vaccine', 15, '2028-12-01', 'NOMINAL')")
        c.execute("INSERT INTO inventory (name, quantity, expiry_date, status) VALUES ('Blood (O-Negative)', 10, '2026-12-30', 'NOMINAL')")
        c.execute("INSERT INTO inventory (name, quantity, expiry_date, status) VALUES ('Insulin (Type 1)', 5, '2027-05-15', 'NOMINAL')")
        conn.commit()
    conn.close()

init_db()

@app.route("/")
def home():
    return render_template("dashboard.html")

@app.route("/prescribe", methods=["POST"])
def prescribe():
    global active_patient
    data = request.get_json(silent=True) or {}
    mapping = {
        "Hepatitis B": "Hep-B Vaccine", 
        "Trauma / Hemorrhage": "Blood (O-Negative)", 
        "Type 1 Diabetes": "Insulin (Type 1)"
    }
    req_item = mapping.get(data.get("disease"))
    if req_item:
        active_patient = {"name": data.get("name"), "required_item": req_item}
    return jsonify({"status": "Prescribed", "item": req_item})

@app.route("/api/scan", methods=["POST"])
def sim_scan():
    data = request.get_json(silent=True) or {}
    return process_hardware_logic({"tag_id": data.get("tag", ""), "lifted_item": data.get("lifted_item", ""), "temperature": latest_temp, "humidity": latest_hum})

@app.route("/api/telemetry")
def telemetry():
    global latest_temp
    temp_val = request.args.get("temp")
    if temp_val: latest_temp = round(float(temp_val), 1)
    return jsonify({"status": "ok"})

@app.route("/api/hardware_update", methods=["POST"])
def hardware_update():
    return process_hardware_logic(request.get_json(silent=True) or {})

def process_hardware_logic(data):
    global active_patient, active_staff, latest_temp, latest_hum, VALID_STAFF_UID, INTRUDER_UID
    conn = get_db()
    
    scanned_tag = str(data.get("tag_id", "")).strip().upper()
    lifted_item = str(data.get("lifted_item", "")).strip()
    latest_temp = round(float(data.get("temperature", latest_temp)), 1)
    latest_hum = round(float(data.get("humidity", latest_hum)), 1)
    
    buzzer_pattern = 0 
    
    conn.execute("INSERT INTO sensor_logs (temp_value) VALUES (?)", (latest_temp,))

    # 1. AUTO-LEARN MAGIC 
    if scanned_tag:
        if VALID_STAFF_UID == "AUTO":
            VALID_STAFF_UID = scanned_tag
            print(f"🪄 SYSTEM CALIBRATED: {scanned_tag} is Valid Staff.")
        elif INTRUDER_UID == "AUTO_INTRUDER" and scanned_tag != VALID_STAFF_UID:
            INTRUDER_UID = scanned_tag
            print(f"🪄 SYSTEM CALIBRATED: {scanned_tag} is Intruder.")

    # 2. CLIMATE INTEGRITY CHECK (WITH DEMO AUTO-RECOVERY)
    if latest_temp > 8.0 or latest_temp < 2.0:
        conn.execute("UPDATE inventory SET status = 'SPOILED'")
    else:
        # 🚨 PRESENTATION FIX: Automatically heals the matrix when temp is safe
        conn.execute("UPDATE inventory SET status = 'NOMINAL'")

    # 3. AUTHENTICATION LOGIC (RFID SCAN)
    if scanned_tag:
        if scanned_tag == INTRUDER_UID:
            conn.execute("INSERT INTO alerts (type, message) VALUES ('CRITICAL', 'INTRUDER DETECTED! Invalid ID.')")
            buzzer_pattern = 4 
        else:
            active_staff = {"name": "Nurse Sarah", "uid": scanned_tag, "login_time": time.time()}
            conn.execute("INSERT INTO alerts (type, message) VALUES ('INFO', 'Staff Authenticated. Vault Unlocked.')")
        
        conn.commit()
        return jsonify({"buzzer_pattern": buzzer_pattern}), 200

    # 4. ASSET DISPENSING LOGIC (WIRE LIFTED)
    if lifted_item:
        item_data = conn.execute("SELECT quantity, status FROM inventory WHERE name=?", (lifted_item,)).fetchone()
        
        # Rule A: Unauthenticated Lift
        if not active_staff["name"] or time.time() - active_staff["login_time"] > SESSION_SECONDS:
            active_staff = {"name": None, "uid": None, "login_time": 0}
            conn.execute("INSERT INTO alerts (type, message) VALUES ('SECURITY', 'UNVERIFIED LIFT! System Locked.')")
            buzzer_pattern = 3 

        # Rule B: Spoiled Item Picked
        elif item_data and item_data["status"] == "SPOILED":
            conn.execute("INSERT INTO alerts (type, message) VALUES ('DANGER', 'SPOILED ASSET LIFTED! Do not administer.')")
            buzzer_pattern = 1 
            
        # Rule C: No Patient Assigned
        elif not active_patient["name"]:
            conn.execute("INSERT INTO alerts (type, message) VALUES ('SECURITY', 'Lift blocked: No active patient.')")
            buzzer_pattern = 3 

        # Rule D: Fatal Patient Mismatch
        elif lifted_item != active_patient["required_item"]:
            conn.execute("INSERT INTO transactions (patient_name, expected_item, dispensed_item, dispensed_by, result) VALUES (?, ?, ?, ?, 'FATAL MISMATCH')",
                         (active_patient["name"], active_patient["required_item"], lifted_item, active_staff["name"]))
            conn.execute("INSERT INTO alerts (type, message) VALUES ('SECURITY', ?)", (f"MISMATCH! Expected {active_patient['required_item']}, got {lifted_item}",))
            buzzer_pattern = 5 

        # Rule E: Success & Stock Check
        else:
            new_qty = item_data["quantity"] - 1
            conn.execute("UPDATE inventory SET quantity = ? WHERE name=?", (new_qty, lifted_item))
            conn.execute("INSERT INTO transactions (patient_name, expected_item, dispensed_item, dispensed_by, result) VALUES (?, ?, ?, ?, 'CORRECT')",
                         (active_patient["name"], active_patient["required_item"], lifted_item, active_staff["name"]))
            
            if new_qty <= 3:
                conn.execute("INSERT INTO alerts (type, message) VALUES ('WARNING', ?)", (f"Low Stock Alert: {lifted_item} ({new_qty} left)",))
                buzzer_pattern = 2 
            
            active_patient, active_staff = {"name": None, "required_item": None}, {"name": None, "uid": None, "login_time": 0}

    conn.commit()
    conn.close()
    return jsonify({"buzzer_pattern": buzzer_pattern}), 200

@app.route("/api/dashboard_data")
def dashboard_data():
    conn = get_db()
    inv = conn.execute("SELECT name, quantity, expiry_date, status FROM inventory").fetchall()
    alerts = conn.execute("SELECT timestamp, type, message FROM alerts ORDER BY id DESC LIMIT 5").fetchall()
    tx = conn.execute("SELECT timestamp, patient_name, expected_item, dispensed_item, dispensed_by, result FROM transactions ORDER BY id DESC LIMIT 6").fetchall()
    temps = conn.execute("SELECT timestamp, temp_value FROM sensor_logs ORDER BY id DESC LIMIT 12").fetchall()
    conn.close()
    
    temps.reverse() 

    time_left = max(0, int(SESSION_SECONDS - (time.time() - active_staff["login_time"]))) if active_staff["login_time"] > 0 else 0

    return jsonify({
        "temp": latest_temp,
        "hum": latest_hum,
        "active_patient": active_patient["name"] if active_patient["name"] else "None",
        "expected_item": active_patient["required_item"] if active_patient["required_item"] else "Waiting...",
        "active_staff": active_staff["name"] if active_staff["name"] else "LOCKED",
        "timeout_seconds": time_left,
        "inventory": [{"name": i["name"], "qty": i["quantity"], "expiry": i["expiry_date"], "status": i["status"]} for i in inv],
        "alerts": [{"time": a["timestamp"][11:19], "type": a["type"], "msg": a["message"]} for a in alerts],
        "transactions": [{"time": t["timestamp"][11:19], "patient": t["patient_name"], "expected": t["expected_item"], "dispensed": t["dispensed_item"], "staff": t["dispensed_by"], "result": t["result"]} for t in tx],
        "temp_history": [{"time": t["timestamp"][11:19], "val": t["temp_value"]} for t in temps]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)