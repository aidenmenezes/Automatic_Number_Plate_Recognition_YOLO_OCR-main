from flask import Flask, render_template, request, redirect, url_for, Response, jsonify, send_file
import os
import database
import qrcode
from io import BytesIO

app = Flask(__name__)

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

# --- PRO UPI QR GENERATOR (Fixed) ---
@app.route("/qr/<float:amount>")
def get_qr(amount):
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
    return jsonify({"success": True, "message": "Payment confirmed, gate opening..."})

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
    app.run(debug=True, port=5000, use_reloader=False)
