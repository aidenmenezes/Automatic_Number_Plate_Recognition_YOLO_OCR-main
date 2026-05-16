# import sqlite3
# from datetime import datetime
# import os

# DB_NAME = "parking_system.db"

# def init_db():
#     conn = sqlite3.connect(DB_NAME)
#     cursor = conn.cursor()
#     cursor.execute('''
#         CREATE TABLE IF NOT EXISTS sessions (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             plate TEXT NOT NULL,
#             owner_name TEXT,
#             category TEXT,
#             entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#             exit_time TIMESTAMP,
#             duration TEXT,
#             amount REAL DEFAULT 0,
#             status TEXT DEFAULT 'parked',
#             image_path TEXT
#         )
#     ''')
#     conn.commit()
#     conn.close()

# def log_entry(plate, owner_name, category, image_path=None):
#     conn = sqlite3.connect(DB_NAME)
#     cursor = conn.cursor()
#     cursor.execute("SELECT id FROM sessions WHERE plate = ? AND status = 'parked'", (plate,))
#     if cursor.fetchone() is None:
#         cursor.execute('''
#             INSERT INTO sessions (plate, owner_name, category, entry_time, status, image_path)
#             VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'parked', ?)
#         ''', (plate, owner_name, category, image_path))
#         conn.commit()
#     conn.close()

# def log_exit(plate):
#     conn = sqlite3.connect(DB_NAME)
#     cursor = conn.cursor()
#     cursor.execute("SELECT id, entry_time FROM sessions WHERE plate = ? AND status = 'parked' ORDER BY entry_time DESC LIMIT 1", (plate,))
#     row = cursor.fetchone()
    
#     if row:
#         session_id, entry_time_str = row
#         entry_time = datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S")
#         exit_time = datetime.now()
        
#         duration_delta = exit_time - entry_time
#         hours = duration_delta.total_seconds() / 3600
#         amount = 20 if hours <= 1 else 20 + (int(hours)) * 10
#         duration_str = str(duration_delta).split(".")[0]
        
#         cursor.execute('''
#             UPDATE sessions 
#             SET exit_time = ?, duration = ?, amount = ?, status = 'unpaid'
#             WHERE id = ?
#         ''', (exit_time.strftime("%Y-%m-%d %H:%M:%S"), duration_str, amount, session_id))
#         conn.commit()
#         conn.close()
#         return {"id": session_id, "amount": amount}
    
#     conn.close()
#     return None

# def mark_as_paid(session_id):
#     conn = sqlite3.connect(DB_NAME)
#     cursor = conn.cursor()
#     cursor.execute("UPDATE sessions SET status = 'paid' WHERE id = ?", (session_id,))
#     conn.commit()
#     conn.close()

# def get_parking_stats():
#     conn = sqlite3.connect(DB_NAME)
#     cursor = conn.cursor()
#     cursor.execute("SELECT COUNT(*) FROM sessions WHERE status = 'parked'")
#     occupied = cursor.fetchone()[0]
#     cursor.execute("SELECT SUM(amount) FROM sessions WHERE status = 'paid'")
#     revenue = cursor.fetchone()[0] or 0
#     conn.close()
#     return occupied, revenue

# def get_all_logs():
#     conn = sqlite3.connect(DB_NAME)
#     cursor = conn.cursor()
#     cursor.execute("SELECT plate, owner_name, entry_time, exit_time, status, amount, duration, image_path, id FROM sessions ORDER BY entry_time DESC")
#     rows = cursor.fetchall()
#     conn.close()
#     return rows

# if not os.path.exists(DB_NAME):
#     init_db()



import os
from datetime import datetime
import psycopg2
from dotenv import load_dotenv

# Load variables from your .env file
load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    """Helper function to cleanly establish a cloud connection to Neon"""
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Automatically creates the sessions table in Neon if it doesn't exist"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # PostgreSQL changes: 'SERIAL PRIMARY KEY' replaces 'INTEGER PRIMARY KEY AUTOINCREMENT'
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
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
    cursor.close()
    conn.close()

def log_entry(plate, owner_name, category, image_path=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # PostgreSQL uses '%s' placeholders instead of '?'
    cursor.execute("SELECT id FROM sessions WHERE plate = %s AND status = 'parked'", (plate,))
    if cursor.fetchone() is None:
        cursor.execute('''
            INSERT INTO sessions (plate, owner_name, category, entry_time, status, image_path)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP, 'parked', %s)
        ''', (plate, owner_name, category, image_path))
        conn.commit()
    cursor.close()
    conn.close()

def log_exit(plate):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, entry_time FROM sessions WHERE plate = %s AND status = 'parked' ORDER BY entry_time DESC LIMIT 1", (plate,))
    row = cursor.fetchone()
    
    if row:
        session_id, entry_time = row
        exit_time = datetime.now()
        
        # Neon/PostgreSQL natively returns 'entry_time' as a datetime object! 
        # No more string parsing (strptime) needed.
        duration_delta = exit_time - entry_time
        hours = duration_delta.total_seconds() / 3600
        amount = 20 if hours <= 1 else 20 + (int(hours)) * 10
        duration_str = str(duration_delta).split(".")[0]
        
        cursor.execute('''
            UPDATE sessions 
            SET exit_time = %s, duration = %s, amount = %s, status = 'unpaid'
            WHERE id = %s
        ''', (exit_time, duration_str, amount, session_id))
        conn.commit()
        cursor.close()
        conn.close()
        return {"id": session_id, "amount": amount}
    
    cursor.close()
    conn.close()
    return None

def mark_as_paid(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE sessions SET status = 'paid' WHERE id = %s", (session_id,))
    conn.commit()
    cursor.close()
    conn.close()

def get_parking_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE status = 'parked'")
    occupied = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(amount) FROM sessions WHERE status = 'paid'")
    revenue = cursor.fetchone()[0] or 0
    
    cursor.close()
    conn.close()
    return occupied, revenue

def get_all_logs():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT plate, owner_name, entry_time, exit_time, status, amount, duration, image_path, id FROM sessions ORDER BY entry_time DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

# This forces the cloud table initialization setup when the script loads
init_db()