from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify
import pandas as pd
import os
from datetime import datetime
import threading
import subprocess
import platform
import sys

app = Flask(__name__)

# Paths
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_PATH, "known_vehicles.csv")

def get_data_paths():
    date_str = datetime.now().strftime("%Y-%m-%d")
    base_filename = f"detected_plates_{date_str}"
    excel_path = os.path.join(BASE_PATH, f"{base_filename}.xlsx")
    csv_path = os.path.join(BASE_PATH, f"{base_filename}.csv")
    return excel_path, csv_path

# Ensure CSV exists
def init_csv():
    if not os.path.exists(CSV_PATH):
        pd.DataFrame(columns=["plate", "owner_name", "category"]).to_csv(CSV_PATH, index=False)

# Load today's data or return empty DataFrame
def load_data():
    excel_path, csv_path = get_data_paths()
    if os.path.exists(csv_path):
        return pd.read_csv(csv_path)
    if os.path.exists(excel_path):
        return pd.read_excel(excel_path)
    return pd.DataFrame(columns=["Vehicle Number", "Plate Number", "Owner Name", "Timestamp", "Category"])

# Save new known vehicle to CSV
def save_to_csv(plate, owner_name, category):
    plate = plate.upper().strip()
    normalized_plate = plate.replace(" ", "")
    df = pd.read_csv(CSV_PATH)
    df['normalized_plate'] = df['plate'].str.replace(" ", "").str.upper()
    df = df[df['normalized_plate'] != normalized_plate]
    df = pd.concat([df, pd.DataFrame([{
        "plate": plate,
        "owner_name": owner_name,
        "category": category
    }])], ignore_index=True)
    df.drop(columns=["normalized_plate"], errors="ignore").to_csv(CSV_PATH, index=False)

# Start detection process
@app.route("/start")
def start_detection():
    def run():
        if platform.system() == "Windows":
            subprocess.Popen([sys.executable, "main.py"])
        else:
            subprocess.Popen([sys.executable, "main.py"])

    threading.Thread(target=run).start()
    return redirect(url_for("index"))

@app.route("/video_feed")
def video_feed():
    return redirect("http://127.0.0.1:5001/video_feed")

@app.route("/download")
def download_excel():
    excel_path, _ = get_data_paths()
    if os.path.exists(excel_path):
        return send_file(excel_path, as_attachment=True)
    return "Excel file not found", 404

@app.route("/add", methods=["POST"])
def add_manual_entry():
    plate = request.form.get("plate")
    owner_name = request.form.get("owner_name")
    category = request.form.get("category")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    df = load_data()
    normalized_input = plate.replace(" ", "").upper()
    df['normalized_check'] = df['Vehicle Number'].astype(str).str.replace(" ", "").str.upper()

    already_exists = ((df["normalized_check"] == normalized_input) & (df["Owner Name"] == owner_name)).any()

    if not already_exists:
        new_row = {
            "Vehicle Number": plate.upper(),
            "Plate Number": plate.upper(),
            "Owner Name": owner_name,
            "Timestamp": timestamp,
            "Category": category
        }
        df = df.drop(columns=["normalized_check"], errors="ignore")
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        
        excel_path, csv_path = get_data_paths()
        df.to_csv(csv_path, index=False)
        df.to_excel(excel_path, index=False)

    save_to_csv(plate, owner_name, category)
    return redirect(url_for("index"))

@app.route("/")
def index():
    init_csv()
    df = load_data()
    stats = {
        "total": len(df),
        "latest": df["Timestamp"].iloc[-1] if not df.empty else "No data yet",
    }
    return render_template("dashboard.html", data=df.to_dict(orient="records"), stats=stats)

if __name__ == "__main__":
    app.run(debug=True,use_reloader=False)
