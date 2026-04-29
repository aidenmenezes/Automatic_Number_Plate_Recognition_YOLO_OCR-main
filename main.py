import torch
import cv2
import time
import os
import pandas as pd
from datetime import datetime
import threading
from flask import Flask, Response
import re

from ai.ai_model import load_yolov5_model, detection
from ai.ocr_model import easyocr_model_load
from helper.params import Parameters
from helper.general_utils import filter_text
import database

# Load parameters, models, and known vehicle data
params = Parameters()
text_reader = easyocr_model_load()
model, labels = load_yolov5_model()

# Ensure snapshots directory exists
SNAPSHOT_DIR = os.path.join("static", "snapshots")
if not os.path.exists(SNAPSHOT_DIR):
    os.makedirs(SNAPSHOT_DIR)

# Global variables for smooth streaming
latest_frame = None
display_frame = None
last_ocr_result = ""

def is_valid_plate(plate):
    # Basic cleanup: remove spaces and make uppercase
    plate = plate.replace(" ", "").upper()
    
    # 1. Length Validation (Indian plates are 7-10 chars)
    if not (7 <= len(plate) <= 10):
        return False
        
    # 2. Pattern Match (State Code + District + Series + Number)
    # Pattern: 2 Letters, then 1-2 Digits, then 1-2 Letters, then 4 Digits
    # Examples: HR98AA7777, TN01AB1234, DL3C1234
    pattern = r'^[A-Z]{2}[0-9]{1,2}[A-Z]{0,2}[0-9]{4}$'
    
    return bool(re.match(pattern, plate))

def lookup_owner_info(plate):
    normalized_plate = plate.replace(" ", "").upper()
    try:
        v_data = pd.read_csv("known_vehicles.csv")
        v_data['normalized_plate'] = v_data['plate'].str.replace(" ", "").str.upper()
        row = v_data[v_data['normalized_plate'] == normalized_plate]
        if not row.empty:
            return row.iloc[0]['owner_name'], row.iloc[0]['category']
    except:
        pass
    return "Unknown", "visitor"

def camera_loop():
    global latest_frame, display_frame
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    while True:
        ret, frame = cap.read()
        if ret:
            latest_frame = frame.copy()
            temp_frame = frame.copy()
            if last_ocr_result:
                cv2.putText(temp_frame, f"Last: {last_ocr_result}", (20, 40), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            display_frame = temp_frame
        else:
            time.sleep(0.01)

def inference_loop():
    global latest_frame, last_ocr_result
    database.init_db()
    last_event_time = {}

    while True:
        if latest_frame is None:
            time.sleep(0.1)
            continue

        frame_to_process = latest_frame.copy()
        try:
            detected, coords = detection(frame_to_process, model, labels)

            if detected is not None:
                # OCR Processing
                gray = cv2.cvtColor(detected, cv2.COLOR_BGR2GRAY)
                result = text_reader.readtext(gray)
                text = filter_text(params.rect_size, result, params.region_threshold)

                if text:
                    display_plate = text[-1].strip().upper()
                    normalized_plate = display_plate.replace(" ", "")
                    
                    # --- VALIDATION LAYER ---
                    if not is_valid_plate(normalized_plate):
                        print(f"🚫 Ignored invalid plate: {normalized_plate}")
                        continue
                    
                    last_ocr_result = display_plate
                    now = time.time()
                    
                    # Cooldown to avoid multiple logs for the same car
                    if normalized_plate not in last_event_time or (now - last_event_time[normalized_plate]) > 60:
                        
                        # Save Security Snapshot
                        img_name = f"{normalized_plate}_{int(now)}.jpg"
                        img_path = os.path.join(SNAPSHOT_DIR, img_name)
                        cv2.imwrite(img_path, detected)
                        web_path = f"snapshots/{img_name}"

                        owner_name, category = lookup_owner_info(normalized_plate)
                        
                        conn = database.sqlite3.connect(database.DB_NAME)
                        cursor = conn.cursor()
                        cursor.execute("SELECT id FROM sessions WHERE plate = ? AND status = 'parked'", (normalized_plate,))
                        is_parked = cursor.fetchone()
                        conn.close()

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

stream_app = Flask(__name__)

@stream_app.route('/video_feed')
def video_feed():
    def generate():
        while True:
            if display_frame is not None:
                ret, buffer = cv2.imencode('.jpg', display_frame)
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.04)
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == "__main__":
    threading.Thread(target=camera_loop, daemon=True).start()
    threading.Thread(target=inference_loop, daemon=True).start()
    stream_app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)
