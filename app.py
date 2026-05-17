from flask import Flask, render_template, request, redirect, url_for, Response, jsonify, send_file
import os
import database
import qrcode
from io import BytesIO
from datetime import datetime, timedelta
import socket
import threading
import time
import cv2
import numpy as np
import re

app = Flask(__name__)

# Tracks which session is currently displayed on the mobile kiosk
_active_kiosk_session = {"session_id": None}

TOTAL_SLOTS = 50

# --- Camera & Inference Globals ---
latest_frame = None
display_frame = None
last_ocr_result = ""
automation_active = False
models_loaded = False
text_reader = None
model = None
labels = None

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def to_ist_string(dt_obj):
    if not dt_obj:
        return None
    if isinstance(dt_obj, str):
        try:
            dt_obj = datetime.fromisoformat(dt_obj.replace('Z', '+00:00'))
        except ValueError:
            return dt_obj
    if isinstance(dt_obj, datetime):
        ist_time = dt_obj + timedelta(hours=5, minutes=30)
        return ist_time.strftime("%d %b %Y, %I:%M:%S %p IST")
    return dt_obj

# --- Unified AI and Camera Logic ---

def load_ai_models():
    global text_reader, model, labels, models_loaded
    print("⏳ Loading AI Models in background...")
    from ai.ai_model import load_yolov5_model
    from ai.ocr_model import easyocr_model_load
    text_reader = easyocr_model_load()
    model, labels = load_yolov5_model()
    models_loaded = True
    print("✅ AI Models Loaded successfully!")

# Ensure snapshots directory exists
SNAPSHOT_DIR = os.path.join("static", "snapshots")
if not os.path.exists(SNAPSHOT_DIR):
    os.makedirs(SNAPSHOT_DIR)

def is_valid_plate(plate):
    plate = plate.replace(" ", "").upper()
    if not (7 <= len(plate) <= 10):
        return False
    pattern = r'^[A-Z]{2}[0-9]{1,2}[A-Z]{0,2}[0-9]{4}$'
    return bool(re.match(pattern, plate))

def lookup_owner_info(plate):
    return "Unknown", "guest"

def camera_loop():
    global latest_frame, display_frame
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    while True:
        ret, frame = cap.read()
        if ret:
            latest_frame = frame.copy()
            temp_frame = frame.copy()
            
            if automation_active and not models_loaded:
                cv2.putText(temp_frame, "Loading AI...", (20, 80), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 165, 255), 2)
            elif automation_active and last_ocr_result:
                cv2.putText(temp_frame, f"Last: {last_ocr_result}", (20, 40), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            elif not automation_active:
                cv2.putText(temp_frame, "Automation Paused", (20, 40), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                            
            display_frame = temp_frame
        else:
            time.sleep(0.01)

def inference_loop():
    global latest_frame, last_ocr_result
    database.init_db()
    last_event_time = {}

    while True:
        if not automation_active or not models_loaded or latest_frame is None:
            time.sleep(0.1)
            continue

        frame_to_process = latest_frame.copy()
        try:
            from ai.ai_model import detection
            from helper.params import Parameters
            from helper.general_utils import filter_text
            params = Parameters()
            
            detected, coords = detection(frame_to_process, model, labels)

            if detected is not None:
                # OCR Processing
                gray = cv2.cvtColor(detected, cv2.COLOR_BGR2GRAY)
                result = text_reader.readtext(gray)
                text = filter_text(params.rect_size, result, params.region_threshold)

                if text:
                    display_plate = text[-1].strip().upper()
                    normalized_plate = display_plate.replace(" ", "")
                    
                    if not is_valid_plate(normalized_plate):
                        print(f"🚫 Ignored invalid plate: {normalized_plate}")
                        continue
                    
                    last_ocr_result = display_plate
                    now = time.time()
                    
                    if normalized_plate not in last_event_time or (now - last_event_time[normalized_plate]) > 60:
                        img_name = f"{normalized_plate}_{int(now)}.jpg"
                        img_path = os.path.join(SNAPSHOT_DIR, img_name)
                        cv2.imwrite(img_path, detected)
                        web_path = f"snapshots/{img_name}"

                        owner_name, category = lookup_owner_info(normalized_plate)
                        is_parked = database.is_vehicle_parked(normalized_plate)

                        if not is_parked:
                            database.log_entry(normalized_plate, owner_name, category, web_path)
                            print(f"📥 Check-In: {normalized_plate}")
                        else:
                            database.log_exit(normalized_plate)
                            print(f"📤 Check-Out: {normalized_plate}")
                        
                        last_event_time[normalized_plate] = now
        except Exception as e:
            pass

        time.sleep(0.4)

# Start threads naturally on boot
threading.Thread(target=camera_loop, daemon=True).start()
threading.Thread(target=inference_loop, daemon=True).start()

# --- ROUTES ---

@app.route("/start")
def start_detection():
    global automation_active
    if not automation_active:
        automation_active = True
        if not models_loaded:
            threading.Thread(target=load_ai_models, daemon=True).start()
    return redirect(url_for("index"))

@app.route("/video_feed")
def video_feed():
    def generate():
        while True:
            if display_frame is not None:
                ret, buffer = cv2.imencode('.jpg', display_frame)
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            else:
                loading_img = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(loading_img, "Starting Camera...", (150, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                ret, buffer = cv2.imencode('.jpg', loading_img)
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.04)
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

# --- PRO UPI QR GENERATOR ---
@app.route("/qr/<path:amount>")
def get_qr(amount):
    amount = float(amount)
    YOUR_UPI_ID = os.environ.get("MY_UPI_ID") 
    upi_url = f"upi://pay?pa={YOUR_UPI_ID}&pn=SmartParking&am={amount}&cu=INR"
    
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(upi_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')

@app.route("/api/pay/<int:session_id>", methods=["POST"])
def pay_session(session_id):
    try:
        database.mark_as_paid(session_id)
        # Clear kiosk if this session was active
        if _active_kiosk_session["session_id"] == session_id:
            _active_kiosk_session["session_id"] = None
        return jsonify({"success": True, "message": "Payment confirmed, gate opening..."})
    except Exception as e:
        print(f"[DB ERROR] pay_session: {e}")
        return jsonify({"success": False, "message": "Payment failed: database unavailable."}), 503

# --- Mobile Kiosk: set / get active session ---
@app.route("/api/active_session", methods=["GET"])
def get_active_session():
    """Returns the latest unpaid session for the mobile kiosk to display."""
    try:
        logs = database.get_all_logs()
    except Exception as e:
        print(f"[DB ERROR] get_active_session: {e}")
        return jsonify({"found": False, "error": "Database unavailable."}), 503

    for log in logs:
        plate, owner, entry, exit_t, status, amount, duration, image, sid = log
        if status == 'unpaid':
            YOUR_UPI_ID = os.environ.get("MY_UPI_ID", "yourupi@upi")
            upi_url = f"upi://pay?pa={YOUR_UPI_ID}&pn=SmartParking&am={amount}&cu=INR"
            return jsonify({
                "found": True,
                "session_id": sid,
                "plate": plate,
                "owner": owner or "Guest",
                "entry": to_ist_string(entry),
                "exit": to_ist_string(exit_t) or "---",
                "duration": duration or "---",
                "amount": amount,
                "upi_url": upi_url
            })
    return jsonify({"found": False})

@app.route("/kiosk")
def kiosk():
    """Mobile kiosk page — displays receipt + QR for the current unpaid session."""
    return render_template("kiosk.html")

@app.route("/api/logs")
def api_logs():
    try:
        logs = database.get_all_logs()
        occupied, revenue = database.get_parking_stats()
    except Exception as e:
        print(f"[DB ERROR] api_logs: {e}")
        return jsonify({
            "logs": [],
            "occupied": 0,
            "available": TOTAL_SLOTS,
            "revenue": "₹0",
            "error": "Database unavailable."
        }), 503
    
    formatted_data = []
    for log in logs:
        ui_status = "Parked"
        if log[4] == 'unpaid': ui_status = "Awaiting Payment"
        if log[4] == 'paid': ui_status = "Paid"

        formatted_data.append({
            "plate": log[0],
            "owner": log[1],
            "entry": to_ist_string(log[2]),
            "exit": to_ist_string(log[3]) or "---",
            "status": ui_status,
            "raw_status": log[4],
            "amount": f"₹{log[5]}" if log[5] > 0 else "---",
            "duration": log[6] or "Active",
            "image": log[7] or "",
            "id": log[8],
            "raw_amount": log[5]
        })
        
    return jsonify({
        "logs": formatted_data,
        "occupied": occupied,
        "available": max(0, TOTAL_SLOTS - occupied),
        "revenue": f"₹{revenue}"
    })

@app.route("/")
def index():
    return render_template("dashboard.html", local_ip=get_local_ip(), automation_active=automation_active)

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=5000, use_reloader=False)
