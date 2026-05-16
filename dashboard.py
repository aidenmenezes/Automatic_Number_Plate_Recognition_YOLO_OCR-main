import streamlit as st
import pandas as pd
import os
from datetime import datetime
import threading
import subprocess
import platform
import sys

# Detect the file under project root for reliable refresh
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
def get_data_paths():
    date_str = datetime.now().strftime("%Y-%m-%d")
    base_filename = f"detected_plates_{date_str}"
    excel_path = os.path.join(BASE_PATH, f"{base_filename}.xlsx")
    csv_path = os.path.join(BASE_PATH, f"{base_filename}.csv")
    return excel_path, csv_path

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
st.set_page_config(page_title="Smart Parking Dashboard", layout="wide")
st.title("🚗 Smart Parking Dashboard")

# Tabs layout according to streamlit documentation
tab1, tab2 = st.tabs(["📷 Detection", "📋 Detected Vehicles"])

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
