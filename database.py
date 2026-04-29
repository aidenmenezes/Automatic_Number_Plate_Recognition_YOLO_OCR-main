import sqlite3
from datetime import datetime
import os

DB_NAME = "parking_system.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate TEXT NOT NULL,
            owner_name TEXT,
            category TEXT,
            entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            exit_time TIMESTAMP,
            duration TEXT,
            amount REAL DEFAULT 0,
            status TEXT DEFAULT 'parked',
            image_path TEXT
        )
    ''')
    conn.commit()
    conn.close()

def log_entry(plate, owner_name, category, image_path=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM sessions WHERE plate = ? AND status = 'parked'", (plate,))
    if cursor.fetchone() is None:
        cursor.execute('''
            INSERT INTO sessions (plate, owner_name, category, entry_time, status, image_path)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'parked', ?)
        ''', (plate, owner_name, category, image_path))
        conn.commit()
    conn.close()

def log_exit(plate):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, entry_time FROM sessions WHERE plate = ? AND status = 'parked' ORDER BY entry_time DESC LIMIT 1", (plate,))
    row = cursor.fetchone()
    
    if row:
        session_id, entry_time_str = row
        entry_time = datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S")
        exit_time = datetime.now()
        
        duration_delta = exit_time - entry_time
        hours = duration_delta.total_seconds() / 3600
        amount = 20 if hours <= 1 else 20 + (int(hours)) * 10
        duration_str = str(duration_delta).split(".")[0]
        
        cursor.execute('''
            UPDATE sessions 
            SET exit_time = ?, duration = ?, amount = ?, status = 'unpaid'
            WHERE id = ?
        ''', (exit_time.strftime("%Y-%m-%d %H:%M:%S"), duration_str, amount, session_id))
        conn.commit()
        conn.close()
        return {"id": session_id, "amount": amount}
    
    conn.close()
    return None

def mark_as_paid(session_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE sessions SET status = 'paid' WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()

def get_parking_stats():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE status = 'parked'")
    occupied = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(amount) FROM sessions WHERE status = 'paid'")
    revenue = cursor.fetchone()[0] or 0
    conn.close()
    return occupied, revenue

def get_all_logs():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT plate, owner_name, entry_time, exit_time, status, amount, duration, image_path, id FROM sessions ORDER BY entry_time DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

if not os.path.exists(DB_NAME):
    init_db()
