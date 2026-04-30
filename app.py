from flask import Flask, render_template, request, redirect, url_for, Response, jsonify, send_file
import os
import database
import qrcode
from io import BytesIO

app = Flask(__name__)

# Tracks which session is currently displayed on the mobile kiosk
_active_kiosk_session = {"session_id": None}

TOTAL_SLOTS = 50

@app.route("/start")
def start_detection():
    import subprocess, sys, threading
    def run():
        subprocess.Popen([sys.executable, "main.py"])
    threading.Thread(target=run).start()
    return redirect(url_for("index"))

@app.route("/video_feed")
def video_feed():
    return redirect("http://127.0.0.1:5001/video_feed")

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
    database.mark_as_paid(session_id)
    # Clear kiosk if this session was active
    if _active_kiosk_session["session_id"] == session_id:
        _active_kiosk_session["session_id"] = None
    return jsonify({"success": True, "message": "Payment confirmed, gate opening..."})

# --- Mobile Kiosk: set / get active session ---
@app.route("/api/active_session", methods=["GET"])
def get_active_session():
    """Returns the latest unpaid session for the mobile kiosk to display."""
    logs = database.get_all_logs()
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
                "entry": entry,
                "exit": exit_t or "---",
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
    logs = database.get_all_logs()
    occupied, revenue = database.get_parking_stats()
    
    formatted_data = []
    for log in logs:
        ui_status = "Parked"
        if log[4] == 'unpaid': ui_status = "Awaiting Payment"
        if log[4] == 'paid': ui_status = "Paid"

        formatted_data.append({
            "plate": log[0],
            "owner": log[1],
            "entry": log[2],
            "exit": log[3] or "---",
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
    return render_template("dashboard.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=5000, use_reloader=False)
