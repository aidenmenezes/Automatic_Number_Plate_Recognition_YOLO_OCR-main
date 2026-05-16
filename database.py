import psycopg2
from psycopg2 import pool
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get Neon DB connection string from environment
DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set. Please configure your Neon DB connection string.")

# Create connection pool for better performance
try:
    connection_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DATABASE_URL)
except Exception as e:
    raise Exception(f"Failed to create connection pool: {e}")

def get_connection():
    """Get a connection from the pool"""
    return connection_pool.getconn()

def return_connection(conn):
    """Return a connection to the pool"""
    if conn:
        connection_pool.putconn(conn)

def init_db():
    """Initialize the database schema"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
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
    finally:
        return_connection(conn)


def log_entry(plate, owner_name, category, image_path=None):
    """Log a vehicle entry"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM sessions WHERE plate = %s AND status = 'parked'", (plate,))
        if cursor.fetchone() is None:
            cursor.execute('''
                INSERT INTO sessions (plate, owner_name, category, entry_time, status, image_path)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP, 'parked', %s)
            ''', (plate, owner_name, category, image_path))
            conn.commit()
    finally:
        return_connection(conn)


def log_exit(plate):
    """Log a vehicle exit"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, entry_time FROM sessions WHERE plate = %s AND status = 'parked' ORDER BY entry_time DESC LIMIT 1", (plate,))
        row = cursor.fetchone()
        
        if row:
            session_id, entry_time_str = row
            # entry_time_str is already a datetime object from PostgreSQL
            if isinstance(entry_time_str, str):
                entry_time = datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S")
            else:
                entry_time = entry_time_str
            
            exit_time = datetime.utcnow()
            
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
            return {"id": session_id, "amount": amount}
    finally:
        return_connection(conn)
    
    return None


def mark_as_paid(session_id):
    """Mark a parking session as paid"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE sessions SET status = 'paid' WHERE id = %s", (session_id,))
        conn.commit()
    finally:
        return_connection(conn)


def get_parking_stats():
    """Get current parking statistics"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sessions WHERE status = 'parked'")
        occupied = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(amount) FROM sessions WHERE status = 'paid'")
        revenue_result = cursor.fetchone()
        revenue = revenue_result[0] if revenue_result[0] is not None else 0
        return occupied, revenue
    finally:
        return_connection(conn)


def get_all_logs():
    """Get all parking session logs"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT plate, owner_name, entry_time, exit_time, status, amount, duration, image_path, id FROM sessions ORDER BY entry_time DESC")
        rows = cursor.fetchall()
        return rows
    finally:
        return_connection(conn)

def is_vehicle_parked(plate):
    """Check if a vehicle is currently parked"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM sessions WHERE plate = %s AND status = 'parked'", (plate,))
        return cursor.fetchone() is not None
    finally:
        return_connection(conn)
