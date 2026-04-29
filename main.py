import torch
import cv2
import time
import os
import pandas as pd
from datetime import datetime
import threading
from flask import Flask, Response

from ai.ai_model import load_yolov5_model, detection
from ai.ocr_model import easyocr_model_load
from helper.params import Parameters
from helper.general_utils import filter_text

# Load parameters, models, and known vehicle data
params = Parameters()
text_reader = easyocr_model_load()
model, labels = load_yolov5_model()
vehicle_data = pd.read_csv("known_vehicles.csv")

# Track detected plates
detected_plates = []
normalized_detected_set = set()  # To avoid duplicates

base_path = os.path.dirname(os.path.abspath(__file__))
base_filename = f"detected_plates_{datetime.now().strftime('%Y-%m-%d')}"
excel_path = os.path.join(base_path, f"{base_filename}.xlsx")
csv_path = os.path.join(base_path, f"{base_filename}.csv")

# Persist results during runtime so dashboard can read updates immediately
def save_detected_results():
    if detected_plates:
        df = pd.DataFrame(detected_plates)
        df.to_csv(csv_path, index=False)
        df.to_excel(excel_path, index=False)
        print(f"💾 Results saved to: {excel_path}")
        print(f"💾 Results saved to: {csv_path}")

# Lookup owner and category from CSV
def lookup_owner_info(plate):
    normalized_plate = plate.replace(" ", "").upper()
    vehicle_data['normalized_plate'] = vehicle_data['plate'].str.replace(" ", "").str.upper()
    row = vehicle_data[vehicle_data['normalized_plate'] == normalized_plate]
    if not row.empty:
        return row.iloc[0]['owner_name'], row.iloc[0]['category']
    return "Unknown", "visitor"

# Improve image quality for OCR
def enhance_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, threshed = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return threshed

# ... [No change in the imports and setup code above]

stream_app = Flask(__name__)
latest_frame = None
current_raw_frame = None

def camera_loop(cap):
    global current_raw_frame
    while True:
        ret, frame = cap.read()
        if ret:
            current_raw_frame = frame
        else:
            time.sleep(0.01)

def inference_loop():
    global latest_frame, current_raw_frame
    print("🚀 Starting ANPR system...")
   
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    if not cap.isOpened():
        print("❌ Error: Could not open webcam. Make sure it's not being used by another app.")
        return

    print("📷 Running in headless mode (no video window). Press Ctrl+C to stop.")

    cam_thread = threading.Thread(target=camera_loop, args=(cap,), daemon=True)
    cam_thread.start()

    try:
        while True:
            if current_raw_frame is None:
                time.sleep(0.05)
                continue

            frame = current_raw_frame

            try:
                detected, coords = detection(frame, model, labels)

                if detected is not None:
                    preprocessed = enhance_image(detected)
                    result = text_reader.readtext(preprocessed)
                    text = filter_text(params.rect_size, result, params.region_threshold)

                    if text:
                        display_plate = text[-1].strip().upper()
                        normalized_plate = display_plate.replace(" ", "")
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        if normalized_plate not in normalized_detected_set:
                            owner_name, category = lookup_owner_info(normalized_plate)

                            detected_plates.append({
                                "Vehicle Number": display_plate,
                                "Plate Number": display_plate,
                                "Owner Name": owner_name,
                                "Timestamp": timestamp,
                                "Category": category
                            })

                            normalized_detected_set.add(normalized_plate)
                            save_detected_results()
                            print(f"✅ Detected: {display_plate} | Owner: {owner_name} | Category: {category}")
                        else:
                            print(f"⏩ Duplicate skipped: {display_plate}")
                    else:
                        print("🔍 No text detected.")
                else:
                    print("📷 No vehicle detected.")

                latest_frame = detected if detected is not None else frame

            except Exception as e:
                print(f"❌ Error: {str(e)}")

            time.sleep(0.05)

    except Exception as e:
        print(f"🛑 Program stopped: {e}")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        file_path = os.path.join(base_path, f"{base_filename}.xlsx")
        csv_file_path = os.path.join(base_path, f"{base_filename}.csv")

        if detected_plates:
            df = pd.DataFrame(detected_plates)
            df.to_csv(csv_file_path, index=False)
            df.to_excel(file_path, index=False)
            print(f"💾 Results saved to: {file_path}")
            print(f"💾 Results saved to: {csv_file_path}")

        print("📴 Camera released.")

@stream_app.route('/video_feed')
def video_feed():
    def generate():
        while True:
            if latest_frame is not None:
                ret, buffer = cv2.imencode('.jpg', latest_frame)
                if ret:
                    frame_bytes = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.05)
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == "__main__":
    t = threading.Thread(target=inference_loop, daemon=True)
    t.start()
    stream_app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)
