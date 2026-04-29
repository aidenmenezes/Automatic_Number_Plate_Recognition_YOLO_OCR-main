import streamlit as st
import pandas as pd
import os
from datetime import datetime
import threading
import subprocess
import platform
import sys

# Constants
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_PATH, "known_vehicles.csv")

# Detect the file under project root for reliable refresh
def get_data_paths():
    date_str = datetime.now().strftime("%Y-%m-%d")
    base_filename = f"detected_plates_{date_str}"
    excel_path = os.path.join(BASE_PATH, f"{base_filename}.xlsx")
    csv_path = os.path.join(BASE_PATH, f"{base_filename}.csv")
    return excel_path, csv_path

# Ensure known vehicles CSV exists
if not os.path.exists(CSV_PATH):
    pd.DataFrame(columns=["plate", "owner_name", "category"]).to_csv(CSV_PATH, index=False)

# Save entry to known vehicles CSV
def save_to_csv(plate, owner_name, category):
    plate = plate.upper()
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

# Load today's Excel file or initialize
def load_data():
    excel_path, csv_path = get_data_paths()
    if os.path.exists(csv_path):
        return pd.read_csv(csv_path), csv_path
    if os.path.exists(excel_path):
        return pd.read_excel(excel_path), excel_path
    alt_csv = os.path.join(os.getcwd(), os.path.basename(csv_path))
    if os.path.exists(alt_csv):
        return pd.read_csv(alt_csv), alt_csv
    alt_excel = os.path.join(os.getcwd(), os.path.basename(excel_path))
    if os.path.exists(alt_excel):
        return pd.read_excel(alt_excel), alt_excel
    return pd.DataFrame(columns=["Vehicle Number", "Plate Number", "Owner Name", "Timestamp", "Category"]), csv_path

# Start detection subprocess (cross-platform)
def run_detection():
    python_exec = sys.executable
    if platform.system() == "Windows":
        if os.path.exists(os.path.join("venv", "Scripts", "python.exe")):
            python_exec = os.path.abspath(os.path.join("venv", "Scripts", "python.exe"))
        subprocess.Popen([python_exec, "main.py"])
    else:
        if os.path.exists(os.path.join("venv", "bin", "python")):
            python_exec = os.path.abspath(os.path.join("venv", "bin", "python"))
        subprocess.Popen([python_exec, "main.py"])

# Streamlit UI Setup 
st.set_page_config(page_title="ANPR Dashboard", layout="wide")
st.title("🚗 Automatic Number Plate Recognition Dashboard")

# Tabs layout accorging to steamlit documentation
tab1, tab2, tab3 = st.tabs(["📷 Detection", "📋 Detected Vehicles", "📝 Manual Entry"])

# --- TAB 1: Detection Control ---
with tab1:
    st.subheader("Start ANPR Detection")
    if st.button("▶️ Start Detection"):
        st.success("Detection system started in background.")
        threading.Thread(target=run_detection).start()
    st.warning("🛑 To stop detection, manually terminate the background Python process.")

# --- TAB 2: Detected Vehicles ---
with tab2:
    st.subheader("Detected Vehicle Records")

    if "refresh_timestamp" not in st.session_state:
        st.session_state.refresh_timestamp = None

    if st.button("🔄 Refresh records", key="refresh_records"):
        st.session_state.refresh_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.rerun()

    data, excel_path = load_data()
    if os.path.exists(excel_path):
        modified_time = datetime.fromtimestamp(os.path.getmtime(excel_path)).strftime("%Y-%m-%d %H:%M:%S")
        st.write(f"Loaded from: `{excel_path}`")
        st.write(f"File last modified: {modified_time}")
    else:
        st.write(f"Excel file not found at `{excel_path}`. It will be created when detection saves results.")

    if st.session_state.refresh_timestamp:
        st.write(f"Last refresh: {st.session_state.refresh_timestamp}")
    else:
        st.write("Click refresh after new detections are saved.")

    st.dataframe(data, use_container_width=True)

    if not data.empty:
        file_label = "⬇️ Download current data file"
        with open(excel_path, "rb") as f:
            st.download_button(file_label, f, file_name=os.path.basename(excel_path))

# --- TAB 3: Manual Entry ---
with tab3:
    st.subheader("Add Unknown Vehicle Entry")
    with st.form("manual_entry_form"):
        plate_input = st.text_input("Plate Number (as detected)")
        owner_name = st.text_input("Owner Name")
        category = st.selectbox("Category", ["visitor", "teacher", "student", "guest"])
        submit = st.form_submit_button("Add Entry")

        if submit and plate_input:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            plate_cleaned = plate_input.upper().strip()
            normalized_input = plate_cleaned.replace(" ", "")

            save_to_csv(plate_cleaned, owner_name, category)

            # Add to Excel if not duplicate
            df, _ = load_data()
            df['normalized_check'] = df['Vehicle Number'].astype(str).str.replace(" ", "").str.upper()

            already_exists = ((df["normalized_check"] == normalized_input) & (df["Owner Name"] == owner_name)).any()

            if not already_exists:
                new_row = {
                    "Vehicle Number": plate_cleaned,
                    "Plate Number": plate_cleaned,
                    "Owner Name": owner_name,
                    "Timestamp": timestamp,
                    "Category": category
                }
                df = df.drop(columns=["normalized_check"], errors="ignore")
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                excel_path, csv_path = get_data_paths()
                df.to_csv(csv_path, index=False)
                df.to_excel(excel_path, index=False)
                st.success(f"✅ Entry saved for {plate_cleaned}")
            else:
                st.info(f"ℹ️ {plate_cleaned} already exists in today’s records.")
