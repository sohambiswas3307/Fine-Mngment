"""
E Parivahan — Flask Backend with SQLite Database
AI-Based Smart Traffic Violation Detection & Fine Management System
"""

import sqlite3
import os
import uuid
import threading
import sys
import time
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import cv2
from ultralytics import YOLO

# Fix for Windows Unicode printing issues
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trafficai.db')

# Demo map coordinates (Bengaluru metro–style layout for fine / traffic hotspot UI)
CAMERA_COORDS = {
    'CAM-001': (12.9756, 77.6074),
    'CAM-002': (12.9352, 77.6245),
    'CAM-003': (12.9719, 77.5946),
    'CAM-004': (12.9901, 77.5734),
    'CAM-005': (12.9468, 77.6062),
}
CITY_MAP_DEFAULT = {'name': 'City operations', 'center': [12.9716, 77.5946], 'defaultZoom': 12}

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
PROCESSED_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'processed')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

# Initialize YOLO model
print("Loading YOLOv8 model...")
try:
    import torch
    import ultralytics.nn.tasks
    torch.serialization.add_safe_globals([ultralytics.nn.tasks.DetectionModel])
except Exception as e:
    pass
model = YOLO('yolov8n.pt') # Lightweight model for quick processing
print("Model loaded.")

# ============================================
# Database Helpers
# ============================================

def get_db():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def dict_row(row):
    """Convert sqlite3.Row to dict."""
    return dict(row) if row else None


def dict_rows(rows):
    """Convert list of sqlite3.Row to list of dicts."""
    return [dict(r) for r in rows]


def next_id(table, prefix):
    """Generate the next sequential ID for a table."""
    conn = get_db()
    cursor = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}")
    row = cursor.fetchone()
    count = row['cnt'] if row else 0
    # Find the max numeric suffix
    cursor2 = conn.execute(f"SELECT {table[:-1]}_id FROM {table}")
    all_rows = cursor2.fetchall()
    nums = []
    for r in all_rows:
        val = list(r)[0]
        try:
            nums.append(int(val.replace(prefix + '-', '')))
        except:
            nums.append(0)
    conn.close()
    next_num = max(nums, default=0) + 1
    return f"{prefix}-{str(next_num).zfill(3)}"


# ============================================
# Database Initialization
# ============================================

def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cameras (
            camera_id TEXT PRIMARY KEY,
            location TEXT NOT NULL,
            status TEXT DEFAULT 'Active',
            latitude REAL,
            longitude REAL
        );

        CREATE TABLE IF NOT EXISTS owners (
            owner_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            license_no TEXT NOT NULL,
            phone TEXT,
            email TEXT
        );

        CREATE TABLE IF NOT EXISTS vehicles (
            vehicle_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            reg_no TEXT NOT NULL,
            type TEXT NOT NULL,
            color TEXT,
            FOREIGN KEY (owner_id) REFERENCES owners(owner_id)
        );

        CREATE TABLE IF NOT EXISTS violations (
            violation_id TEXT PRIMARY KEY,
            vehicle_id TEXT NOT NULL,
            camera_id TEXT NOT NULL,
            type TEXT NOT NULL,
            date TEXT NOT NULL,
            confidence INTEGER DEFAULT 0,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
            FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
        );

        CREATE TABLE IF NOT EXISTS fines (
            fine_id TEXT PRIMARY KEY,
            violation_id TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'Unpaid',
            FOREIGN KEY (violation_id) REFERENCES violations(violation_id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            payment_id TEXT PRIMARY KEY,
            fine_id TEXT NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            mode TEXT NOT NULL,
            FOREIGN KEY (fine_id) REFERENCES fines(fine_id)
        );

        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL, -- 'Admin' or 'User'
            owner_id TEXT, -- Linked to owners table for 'User' role
            FOREIGN KEY (owner_id) REFERENCES owners(owner_id)
        );
    """)
    conn.commit()
    conn.close()


def migrate_schema():
    """Add camera coordinates for map features; backfill demo pins."""
    conn = get_db()
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(cameras)").fetchall()]
        if 'latitude' not in cols:
            conn.execute("ALTER TABLE cameras ADD COLUMN latitude REAL")
        if 'longitude' not in cols:
            conn.execute("ALTER TABLE cameras ADD COLUMN longitude REAL")
        conn.commit()
        for cam_id, (lat, lng) in CAMERA_COORDS.items():
            conn.execute(
                """UPDATE cameras SET latitude = COALESCE(latitude, ?), longitude = COALESCE(longitude, ?)
                   WHERE camera_id = ?""",
                (lat, lng, cam_id),
            )
        conn.commit()
    finally:
        conn.close()


def seed_data():
    """Insert demo data if tables are empty."""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM cameras").fetchone()[0]
    if count > 0:
        conn.close()
        return

    # Cameras
    cam_rows = [
        ('CAM-001', 'MG Road Junction', 'Active', *CAMERA_COORDS['CAM-001']),
        ('CAM-002', 'Highway Toll Plaza', 'Active', *CAMERA_COORDS['CAM-002']),
        ('CAM-003', 'City Center Signal', 'Active', *CAMERA_COORDS['CAM-003']),
        ('CAM-004', 'Ring Road Flyover', 'Active', *CAMERA_COORDS['CAM-004']),
        ('CAM-005', 'School Zone - Park Street', 'Active', *CAMERA_COORDS['CAM-005']),
    ]
    conn.executemany(
        "INSERT INTO cameras (camera_id, location, status, latitude, longitude) VALUES (?, ?, ?, ?, ?)",
        cam_rows,
    )

    # Owners
    conn.executemany("INSERT INTO owners VALUES (?, ?, ?, ?, ?)", [
        ('OWN-001', 'Rahul Sharma', 'DL-1420110012345', '9876543210', 'rahul.sharma@email.com'),
        ('OWN-002', 'Priya Patel', 'MH-0220090054321', '9876543211', 'priya.patel@email.com'),
        ('OWN-003', 'Amit Kumar', 'KA-0520150098765', '9876543212', 'amit.kumar@email.com'),
        ('OWN-004', 'Sneha Reddy', 'TN-0920180034567', '9876543213', 'sneha.reddy@email.com'),
        ('OWN-005', 'Vikram Singh', 'UP-8020170045678', '9876543214', 'vikram.singh@email.com'),
    ])

    # Vehicles
    conn.executemany("INSERT INTO vehicles VALUES (?, ?, ?, ?, ?)", [
        ('VEH-001', 'OWN-001', 'DL-14-AB-1234', 'Car', 'White'),
        ('VEH-002', 'OWN-002', 'MH-02-CD-5678', 'Motorcycle', 'Black'),
        ('VEH-003', 'OWN-003', 'KA-05-EF-9012', 'Car', 'Silver'),
        ('VEH-004', 'OWN-004', 'TN-09-GH-3456', 'Motorcycle', 'Red'),
        ('VEH-005', 'OWN-005', 'UP-80-IJ-7890', 'Truck', 'Blue'),
        ('VEH-006', 'OWN-001', 'DL-14-KL-4567', 'Motorcycle', 'Black'),
    ])

    # Violations
    conn.executemany("INSERT INTO violations VALUES (?, ?, ?, ?, ?, ?)", [
        ('VIO-001', 'VEH-002', 'CAM-001', 'Helmetless Riding', '2026-04-26', 94),
        ('VIO-002', 'VEH-003', 'CAM-002', 'Overspeeding', '2026-04-27', 97),
        ('VIO-003', 'VEH-001', 'CAM-003', 'Signal Jumping', '2026-04-28', 92),
        ('VIO-004', 'VEH-004', 'CAM-001', 'Helmetless Riding', '2026-04-29', 96),
        ('VIO-005', 'VEH-005', 'CAM-004', 'Lane Violation', '2026-04-30', 89),
        ('VIO-006', 'VEH-006', 'CAM-005', 'Overspeeding', '2026-04-30', 95),
        ('VIO-007', 'VEH-001', 'CAM-002', 'Illegal Parking', '2026-05-01', 91),
    ])

    # Fines
    conn.executemany("INSERT INTO fines VALUES (?, ?, ?, ?)", [
        ('FIN-001', 'VIO-001', 500, 'Paid'),
        ('FIN-002', 'VIO-002', 2000, 'Paid'),
        ('FIN-003', 'VIO-003', 1000, 'Unpaid'),
        ('FIN-004', 'VIO-004', 500, 'Unpaid'),
        ('FIN-005', 'VIO-005', 1000, 'Unpaid'),
        ('FIN-006', 'VIO-006', 2000, 'Unpaid'),
        ('FIN-007', 'VIO-007', 500, 'Unpaid'),
    ])

    # Payments
    conn.executemany("INSERT INTO payments VALUES (?, ?, ?, ?, ?)", [
        ('PAY-001', 'FIN-001', 500, '2026-04-28', 'UPI'),
        ('PAY-002', 'FIN-002', 2000, '2026-04-29', 'Credit Card'),
    ])

    # Users
    conn.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?)", [
        ('USR-001', 'admin', 'admin123', 'Admin', None),
        ('USR-002', 'rahul', 'rahul123', 'User', 'OWN-001'),
        ('USR-003', 'priya', 'priya123', 'User', 'OWN-002'),
        ('USR-004', 'amit', 'amit123', 'User', 'OWN-003'),
    ])

    conn.commit()
    conn.close()
    print("✓ Database seeded with demo data (including RBAC users)")


# ============================================
# Serve Frontend
# ============================================

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')


# ============================================
# API: Authentication
# ============================================

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password)).fetchone()
    conn.close()

    if user:
        u = dict_row(user)
        # In a real app, we'd return a JWT. Here we return user info for simplicity.
        return jsonify({
            'success': True,
            'user': {
                'username': u['username'],
                'role': u['role'],
                'owner_id': u['owner_id']
            }
        })
    return jsonify({'success': False, 'message': 'Invalid username or password'}), 401


# ============================================
# API: Dashboard Stats
# ============================================

@app.route('/api/stats')
def get_stats():
    owner_id = request.args.get('owner_id')
    conn = get_db()
    
    if owner_id:
        # User-specific stats
        total_violations = conn.execute("""
            SELECT COUNT(*) FROM violations v
            JOIN vehicles veh ON v.vehicle_id = veh.vehicle_id
            WHERE veh.owner_id = ?
        """, (owner_id,)).fetchone()[0]
        
        total_cameras = conn.execute("SELECT COUNT(*) FROM cameras WHERE status = 'Active'").fetchone()[0]
        
        collected = 0
        
        pending = conn.execute("""
            SELECT COALESCE(SUM(f.amount), 0) FROM fines f
            JOIN violations v ON f.violation_id = v.violation_id
            JOIN vehicles veh ON v.vehicle_id = veh.vehicle_id
            WHERE f.status = 'Unpaid' AND veh.owner_id = ?
        """, (owner_id,)).fetchone()[0]

        recent_query = """
            SELECT v.violation_id, v.type, v.date, v.confidence,
                   veh.reg_no as vehicle_reg,
                   c.location as camera_location,
                   COALESCE(f.status, 'N/A') as fine_status
            FROM violations v
            JOIN vehicles veh ON v.vehicle_id = veh.vehicle_id
            LEFT JOIN cameras c ON v.camera_id = c.camera_id
            LEFT JOIN fines f ON f.violation_id = v.violation_id
            WHERE veh.owner_id = ?
            ORDER BY v.date DESC, v.violation_id DESC
            LIMIT 10
        """
        recent = conn.execute(recent_query, (owner_id,)).fetchall()
        
        type_counts = dict_rows(conn.execute("""
            SELECT v.type, COUNT(*) as count FROM violations v
            JOIN vehicles veh ON v.vehicle_id = veh.vehicle_id
            WHERE veh.owner_id = ?
            GROUP BY v.type ORDER BY count DESC
        """, (owner_id,)).fetchall())

        registered_owners = None
        registered_vehicles = conn.execute(
            "SELECT COUNT(*) FROM vehicles WHERE owner_id = ?", (owner_id,)
        ).fetchone()[0]
        
    else:
        # Admin global stats
        total_violations = conn.execute("SELECT COUNT(*) FROM violations").fetchone()[0]
        total_cameras = conn.execute("SELECT COUNT(*) FROM cameras").fetchone()[0]
        collected = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM payments").fetchone()[0]
        pending = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM fines WHERE status = 'Unpaid'").fetchone()[0]
        registered_owners = conn.execute("SELECT COUNT(*) FROM owners").fetchone()[0]
        registered_vehicles = conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]

        recent = conn.execute("""
            SELECT v.violation_id, v.type, v.date, v.confidence,
                   veh.reg_no as vehicle_reg,
                   c.location as camera_location,
                   COALESCE(f.status, 'N/A') as fine_status
            FROM violations v
            LEFT JOIN vehicles veh ON v.vehicle_id = veh.vehicle_id
            LEFT JOIN cameras c ON v.camera_id = c.camera_id
            LEFT JOIN fines f ON f.violation_id = v.violation_id
            ORDER BY v.date DESC, v.violation_id DESC
            LIMIT 10
        """).fetchall()

        type_counts = dict_rows(conn.execute(
            "SELECT type, COUNT(*) as count FROM violations GROUP BY type ORDER BY count DESC"
        ).fetchall())

    conn.close()
    payload = {
        'totalViolations': total_violations,
        'totalCameras': total_cameras,
        'finesCollected': collected,
        'pendingFines': pending,
        'recentViolations': dict_rows(recent),
        'violationTypes': type_counts,
        'registeredVehicles': registered_vehicles,
    }
    if registered_owners is not None:
        payload['registeredOwners'] = registered_owners
    return jsonify(payload)


@app.route('/api/map/hotspots')
def map_hotspots():
    """Admin dashboard: camera locations with violation / fine density for live map."""
    if request.args.get('owner_id'):
        return jsonify({'ok': False, 'message': 'Admin only'}), 403
    conn = get_db()
    rows = conn.execute("""
        SELECT c.camera_id, c.location, c.latitude, c.longitude, c.status,
            (SELECT COUNT(*) FROM violations v WHERE v.camera_id = c.camera_id) AS violations,
            (SELECT COUNT(*) FROM violations v
             JOIN fines f ON f.violation_id = v.violation_id WHERE v.camera_id = c.camera_id) AS fines_total,
            (SELECT COUNT(*) FROM violations v
             JOIN fines f ON f.violation_id = v.violation_id
             WHERE v.camera_id = c.camera_id AND f.status = 'Unpaid') AS fines_unpaid,
            (SELECT IFNULL(SUM(f.amount), 0) FROM violations v
             JOIN fines f ON f.violation_id = v.violation_id
             WHERE v.camera_id = c.camera_id AND f.status = 'Unpaid') AS pending_amount
        FROM cameras c
        ORDER BY violations DESC, c.camera_id
    """).fetchall()
    conn.close()

    center_lat, center_lng = CITY_MAP_DEFAULT['center']
    rows_list = [dict(r) for r in rows]
    max_v = max((int(d['violations'] or 0) for d in rows_list), default=1)
    points = []
    for d in rows_list:
        vct = int(d['violations'] or 0)
        lat, lng = d.get('latitude'), d.get('longitude')
        if lat is None or lng is None:
            h = sum(ord(c) * (i + 1) for i, c in enumerate(d['camera_id']))
            lat = center_lat + (h % 17 - 8) * 0.0022
            lng = center_lng + (h % 13 - 6) * 0.0022
        points.append({
            'cameraId': d['camera_id'],
            'location': d['location'],
            'lat': float(lat),
            'lng': float(lng),
            'status': d['status'],
            'violations': vct,
            'finesTotal': int(d['fines_total'] or 0),
            'finesUnpaid': int(d['fines_unpaid'] or 0),
            'pendingAmount': float(d['pending_amount'] or 0),
            'heat': round(vct / max_v, 4) if max_v else 0,
        })

    return jsonify({'ok': True, 'city': CITY_MAP_DEFAULT, 'points': points, 'updatedAt': time.time()})


# ============================================
# API: Cameras
# ============================================

@app.route('/api/cameras', methods=['GET'])
def list_cameras():
    conn = get_db()
    rows = conn.execute("SELECT * FROM cameras ORDER BY camera_id").fetchall()
    conn.close()
    return jsonify(dict_rows(rows))


@app.route('/api/cameras', methods=['POST'])
def create_camera():
    data = request.json
    cam_id = next_id('cameras', 'CAM')
    conn = get_db()
    conn.execute(
        "INSERT INTO cameras (camera_id, location, status, latitude, longitude) VALUES (?, ?, ?, ?, ?)",
        (cam_id, data['location'], data.get('status', 'Active'),
         data.get('latitude'), data.get('longitude')),
    )
    conn.commit()
    conn.close()
    return jsonify({'id': cam_id, 'message': 'Camera added'}), 201


@app.route('/api/cameras/<cam_id>', methods=['PUT'])
def update_camera(cam_id):
    data = request.json
    conn = get_db()
    conn.execute(
        "UPDATE cameras SET location=?, status=?, latitude=?, longitude=? WHERE camera_id=?",
        (data['location'], data.get('status', 'Active'),
         data.get('latitude'), data.get('longitude'), cam_id),
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Camera updated'})


@app.route('/api/cameras/<cam_id>', methods=['DELETE'])
def delete_camera(cam_id):
    conn = get_db()
    conn.execute("DELETE FROM cameras WHERE camera_id=?", (cam_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Camera deleted'})


# ============================================
# API: Owners
# ============================================

@app.route('/api/owners', methods=['GET'])
def list_owners():
    owner_id = request.args.get('owner_id')
    conn = get_db()
    if owner_id:
        rows = conn.execute("SELECT * FROM owners WHERE owner_id = ?", (owner_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM owners ORDER BY owner_id").fetchall()
    conn.close()
    return jsonify(dict_rows(rows))


@app.route('/api/owners', methods=['POST'])
def create_owner():
    data = request.json
    own_id = next_id('owners', 'OWN')
    conn = get_db()
    conn.execute("INSERT INTO owners VALUES (?, ?, ?, ?, ?)",
                 (own_id, data['name'], data['license_no'], data.get('phone', ''), data.get('email', '')))
    conn.commit()
    conn.close()
    return jsonify({'id': own_id, 'message': 'Owner added'}), 201


@app.route('/api/owners/<own_id>', methods=['PUT'])
def update_owner(own_id):
    data = request.json
    conn = get_db()
    conn.execute("UPDATE owners SET name=?, license_no=?, phone=?, email=? WHERE owner_id=?",
                 (data['name'], data['license_no'], data.get('phone', ''), data.get('email', ''), own_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Owner updated'})


@app.route('/api/owners/<own_id>', methods=['DELETE'])
def delete_owner(own_id):
    conn = get_db()
    conn.execute("DELETE FROM owners WHERE owner_id=?", (own_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Owner deleted'})


# ============================================
# API: Vehicles
# ============================================

@app.route('/api/vehicles', methods=['GET'])
def list_vehicles():
    owner_id = request.args.get('owner_id')
    conn = get_db()
    query = """
        SELECT v.*, o.name as owner_name
        FROM vehicles v
        LEFT JOIN owners o ON v.owner_id = o.owner_id
    """
    if owner_id:
        query += " WHERE v.owner_id = ?"
        rows = conn.execute(query, (owner_id,)).fetchall()
    else:
        query += " ORDER BY v.vehicle_id"
        rows = conn.execute(query).fetchall()
    conn.close()
    return jsonify(dict_rows(rows))


@app.route('/api/vehicles', methods=['POST'])
def create_vehicle():
    data = request.json
    veh_id = next_id('vehicles', 'VEH')
    conn = get_db()
    conn.execute("INSERT INTO vehicles VALUES (?, ?, ?, ?, ?)",
                 (veh_id, data['owner_id'], data['reg_no'], data['type'], data.get('color', '')))
    conn.commit()
    conn.close()
    return jsonify({'id': veh_id, 'message': 'Vehicle added'}), 201


@app.route('/api/vehicles/<veh_id>', methods=['PUT'])
def update_vehicle(veh_id):
    data = request.json
    conn = get_db()
    conn.execute("UPDATE vehicles SET owner_id=?, reg_no=?, type=?, color=? WHERE vehicle_id=?",
                 (data['owner_id'], data['reg_no'], data['type'], data.get('color', ''), veh_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Vehicle updated'})


@app.route('/api/vehicles/<veh_id>', methods=['DELETE'])
def delete_vehicle(veh_id):
    conn = get_db()
    conn.execute("DELETE FROM vehicles WHERE vehicle_id=?", (veh_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Vehicle deleted'})


# ============================================
# API: Violations
# ============================================

@app.route('/api/violations', methods=['GET'])
def list_violations():
    owner_id = request.args.get('owner_id')
    conn = get_db()
    query = """
        SELECT v.*, veh.reg_no as vehicle_reg, c.location as camera_location,
               COALESCE(f.status, 'N/A') as fine_status, f.fine_id, f.amount as fine_amount
        FROM violations v
        LEFT JOIN vehicles veh ON v.vehicle_id = veh.vehicle_id
        LEFT JOIN cameras c ON v.camera_id = c.camera_id
        LEFT JOIN fines f ON f.violation_id = v.violation_id
    """
    if owner_id:
        query += " WHERE veh.owner_id = ?"
        query += " ORDER BY v.date DESC, v.violation_id DESC"
        rows = conn.execute(query, (owner_id,)).fetchall()
    else:
        query += " ORDER BY v.date DESC, v.violation_id DESC"
        rows = conn.execute(query).fetchall()
    conn.close()
    return jsonify(dict_rows(rows))


@app.route('/api/violations', methods=['POST'])
def create_violation():
    data = request.json
    vio_id = next_id('violations', 'VIO')
    confidence = data.get('confidence', 90)

    # Fine amounts by violation type
    fine_amounts = {
        'Signal Jumping': 1000, 'Overspeeding': 2000, 'Helmetless Riding': 500,
        'Illegal Parking': 500, 'Lane Violation': 1000, 'Wrong Way Driving': 2000,
        'Using Mobile Phone': 1500, 'Accident': 5000,
    }
    amount = fine_amounts.get(data['type'], 500)

    conn = get_db()
    conn.execute("INSERT INTO violations VALUES (?, ?, ?, ?, ?, ?)",
                 (vio_id, data['vehicle_id'], data['camera_id'], data['type'], data['date'], confidence))

    # Auto-generate fine
    fin_id = next_id('fines', 'FIN')
    conn.execute("INSERT INTO fines VALUES (?, ?, ?, ?)",
                 (fin_id, vio_id, amount, 'Unpaid'))

    conn.commit()
    conn.close()
    return jsonify({
        'violation_id': vio_id,
        'fine_id': fin_id,
        'amount': amount,
        'message': f'Violation logged. Fine {fin_id} of ₹{amount} generated.'
    }), 201


@app.route('/api/violations/<vio_id>', methods=['DELETE'])
def delete_violation(vio_id):
    conn = get_db()
    conn.execute("DELETE FROM fines WHERE violation_id=?", (vio_id,))
    conn.execute("DELETE FROM violations WHERE violation_id=?", (vio_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Violation and linked fine deleted'})


# ============================================
# API: Fines
# ============================================

@app.route('/api/fines', methods=['GET'])
def list_fines():
    status_filter = request.args.get('status', 'all')
    owner_id = request.args.get('owner_id')
    conn = get_db()
    query = """
        SELECT f.*, v.type as violation_type, v.vehicle_id,
               veh.reg_no as vehicle_reg
        FROM fines f
        LEFT JOIN violations v ON f.violation_id = v.violation_id
        LEFT JOIN vehicles veh ON v.vehicle_id = veh.vehicle_id
        WHERE 1=1
    """
    params = []
    if owner_id:
        query += " AND f.status = 'Unpaid'"
        query += " AND veh.owner_id = ?"
        params.append(owner_id)
    elif status_filter != 'all':
        query += " AND f.status = ?"
        params.append(status_filter)

    query += " ORDER BY f.fine_id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify(dict_rows(rows))


# ============================================
# API: Payments
# ============================================

@app.route('/api/payments', methods=['GET'])
def list_payments():
    owner_id = request.args.get('owner_id')
    conn = get_db()
    if owner_id:
        rows = conn.execute("""
            SELECT p.* FROM payments p
            JOIN fines f ON p.fine_id = f.fine_id
            JOIN violations v ON f.violation_id = v.violation_id
            JOIN vehicles veh ON v.vehicle_id = veh.vehicle_id
            WHERE veh.owner_id = ?
            ORDER BY p.date DESC, p.payment_id DESC
        """, (owner_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM payments ORDER BY date DESC, payment_id DESC").fetchall()
    conn.close()
    return jsonify(dict_rows(rows))


@app.route('/api/payments', methods=['POST'])
def create_payment():
    data = request.json
    pay_id = next_id('payments', 'PAY')
    fine_id = data['fine_id']

    conn = get_db()
    # Get fine amount
    fine = conn.execute("SELECT * FROM fines WHERE fine_id=?", (fine_id,)).fetchone()
    if not fine:
        conn.close()
        return jsonify({'error': 'Fine not found'}), 404

    amount = fine['amount']

    conn.execute("INSERT INTO payments VALUES (?, ?, ?, ?, ?)",
                 (pay_id, fine_id, amount, data['date'], data['mode']))
    # Update fine status to Paid
    conn.execute("UPDATE fines SET status='Paid' WHERE fine_id=?", (fine_id,))
    conn.commit()
    conn.close()
    return jsonify({
        'payment_id': pay_id,
        'message': f'Payment {pay_id} recorded. Fine marked as Paid.'
    }), 201


# ============================================
# API: AI Detection (used by frontend simulation)
# ============================================

@app.route('/api/detect', methods=['POST'])
def ai_detect():
    """
    Called by the frontend AI detection simulation.
    Creates a violation + fine in the database.
    """
    data = request.json
    vio_id = next_id('violations', 'VIO')
    confidence = data.get('confidence', 90)

    fine_amounts = {
        'Signal Jumping': 1000, 'Overspeeding': 2000, 'Helmetless Riding': 500,
        'Illegal Parking': 500, 'Lane Violation': 1000, 'Wrong Way Driving': 2000,
        'Using Mobile Phone': 1500, 'Accident': 5000,
    }
    amount = fine_amounts.get(data['type'], 500)

    conn = get_db()
    conn.execute("INSERT INTO violations VALUES (?, ?, ?, ?, ?, ?)",
                 (vio_id, data['vehicle_id'], data['camera_id'], data['type'], data['date'], confidence))

    fin_id = next_id('fines', 'FIN')
    conn.execute("INSERT INTO fines VALUES (?, ?, ?, ?)",
                 (fin_id, vio_id, amount, 'Unpaid'))

    conn.commit()
    conn.close()

    return jsonify({
        'violation_id': vio_id,
        'fine_id': fin_id,
        'amount': amount,
        'confidence': confidence,
        'message': f'{data["type"]} detected with {confidence}% confidence'
    }), 201


# ============================================
# API: REAL AI VIDEO DETECTION (YOLOv8)
# ============================================

import time
processing_jobs = {}

@app.route('/api/upload-video', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400

    filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4().hex}_{filename}"
    filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
    file.save(filepath)

    return jsonify({
        'filename': unique_filename,
        'message': 'Video uploaded successfully'
    }), 200


def process_video_task(filename, camera_id):
    """Background task to run YOLO on the video"""
    job_id = filename
    processing_jobs[job_id] = {'status': 'processing', 'progress': 0, 'detections': [], 'output_video': None}
    
    input_path = os.path.join(UPLOAD_FOLDER, filename)
    output_filename = f"processed_{filename}"
    output_path = os.path.join(PROCESSED_FOLDER, output_filename)

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        processing_jobs[job_id]['status'] = 'error'
        processing_jobs[job_id]['message'] = 'Could not open video'
        return

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # We output as mp4
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    frame_count = 0
    detections = []

    # Get sample vehicles so we can tie detections to DB entries for full cycle
    conn = get_db()
    vehicles = dict_rows(conn.execute("SELECT * FROM vehicles LIMIT 5").fetchall())
    conn.close()
    
    # YOLO COCO classes mapping relevant to us
    # 0 = person, 1 = bicycle, 2 = car, 3 = motorcycle, 5 = bus, 7 = truck, 9 = traffic light
    VIOLATION_HEURISTICS = [
        {'type': 'Helmetless Riding', 'classes': [0, 3], 'desc': 'person + motorcycle'},
        {'type': 'Illegal Parking', 'classes': [2, 5, 7], 'desc': 'car/truck'},
        {'type': 'Signal Jumping', 'classes': [2, 3, 5, 7, 9], 'desc': 'vehicle + traffic light'}
    ]

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            if frame_count % 30 == 0:  # update progress
                processing_jobs[job_id]['progress'] = int((frame_count / total_frames) * 100)

            # Process with YOLO
            results = model(frame, verbose=False)
            
            # Extract detections for heuristics
            frame_detections = []
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    cls_id = int(box.cls[0].item())
                    conf = box.conf[0].item()
                    
                    if conf > 0.25:
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                        cls_name = model.names[cls_id]
                        frame_detections.append({'cls_id': cls_id, 'name': cls_name, 'conf': conf, 'box': [x1, y1, x2, y2]})
                        
                        # Draw bounding box
                        color = (0, 255, 0)
                        if cls_id in [0, 2, 3, 5, 7]: # person, car, motorcycle, bus, truck - tracking
                            color = (0, 0, 255) # Red for potential vehicles/people
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(frame, f"{cls_name} {conf:.2f}", (x1, max(10, y1-10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            # Apply heuristics arbitrarily to simulate AI violation classification based on YOLO objects
            # For demonstration: If we see a person AND a motorcycle in the same frame, flag Helmetless
            person_found = any(d['cls_id'] == 0 for d in frame_detections)
            moto_found = any(d['cls_id'] == 3 for d in frame_detections)
            car_found = any(d['cls_id'] == 2 for d in frame_detections)
            light_found = any(d['cls_id'] == 9 for d in frame_detections)

            violation_type = None
            conf_score = 0
            
            # Heuristic triggers tailored for demo visibility
            if frame_count % int(fps*1) == 0: # Check every second
                if moto_found:
                    violation_type = 'Helmetless Riding'
                    conf_score = 88
                elif car_found and light_found:
                    violation_type = 'Signal Jumping'
                    conf_score = 92
                elif car_found and frame_count % int(fps*10) == 0:
                    violation_type = 'Overspeeding'
                    conf_score = 85
                elif car_found and frame_count % int(fps*20) == 0:
                    violation_type = 'Illegal Parking'
                    conf_score = 95
                
            if violation_type and vehicles:
                # Randomly assign a vehicle from DB to the detection
                import random
                assigned_veh = random.choice(vehicles)
                
                det = {
                    'type': violation_type,
                    'confidence': conf_score,
                    'timestamp': frame_count / fps,
                    'camera_id': camera_id,
                    'vehicle_id': assigned_veh['vehicle_id'],
                    'vehicle_reg': assigned_veh['reg_no']
                }
                detections.append(det)

                # Overlay violation alert on video
                cv2.putText(frame, f"VIOLATION: {violation_type}!", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)

            out.write(frame)
            
    except Exception as e:
        print(f"Error processing video: {str(e)}")
        import traceback
        traceback.print_exc()
        processing_jobs[job_id]['status'] = 'error'
        processing_jobs[job_id]['message'] = str(e)
    finally:
        if 'cap' in locals(): cap.release()
        if 'out' in locals(): out.release()

    # Save detections to Database
    saved_detections = []
    if processing_jobs[job_id]['status'] != 'error':
        try:
            conn = get_db()
            fine_amounts = {
                'Signal Jumping': 1000, 'Overspeeding': 2000, 'Helmetless Riding': 500,
                'Illegal Parking': 500, 'Lane Violation': 1000, 'Wrong Way Driving': 2000,
                'Using Mobile Phone': 1500, 'Accident': 5000,
            }
            
            for det in detections:
                vio_id = next_id('violations', 'VIO')
                date_str = time.strftime('%Y-%m-%d')
                conn.execute("INSERT INTO violations VALUES (?, ?, ?, ?, ?, ?)",
                             (vio_id, det['vehicle_id'], det['camera_id'], det['type'], date_str, det['confidence']))
                             
                fin_id = next_id('fines', 'FIN')
                amount = fine_amounts.get(det['type'], 500)
                conn.execute("INSERT INTO fines VALUES (?, ?, ?, ?)",
                             (fin_id, vio_id, amount, 'Unpaid'))
                             
                det['violation_id'] = vio_id
                det['fine_id'] = fin_id
                det['amount'] = amount
                saved_detections.append(det)
                
            conn.commit()
            conn.close()

            processing_jobs[job_id]['status'] = 'completed'
            processing_jobs[job_id]['progress'] = 100
            processing_jobs[job_id]['output_video'] = output_filename
            processing_jobs[job_id]['detections'] = saved_detections
        except Exception as db_err:
            print(f"Database error: {str(db_err)}")
            processing_jobs[job_id]['status'] = 'error'
            processing_jobs[job_id]['message'] = f"Database error: {str(db_err)}"

@app.route('/api/process-video', methods=['POST'])
def process_video():
    data = request.json
    filename = data.get('filename')
    camera_id = data.get('camera_id', 'CAM-001')
    
    if not filename or filename not in processing_jobs and not os.path.exists(os.path.join(UPLOAD_FOLDER, filename)):
        return jsonify({'error': 'File not found'}), 404
        
    # Start thread
    thread = threading.Thread(target=process_video_task, args=(filename, camera_id))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'job_id': filename,
        'message': 'Processing started matching YOLO model instances'
    }), 202


@app.route('/api/job-status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    if job_id not in processing_jobs:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(processing_jobs[job_id])


@app.route('/api/video/<type>/<filename>')
def serve_video(type, filename):
    folder = PROCESSED_FOLDER if type == 'processed' else UPLOAD_FOLDER
    return send_from_directory(folder, filename)


# ============================================
# API: Unpaid Fines (for payment dropdown)
# ============================================

@app.route('/api/fines/unpaid', methods=['GET'])
def list_unpaid_fines():
    owner_id = request.args.get('owner_id')
    conn = get_db()
    query = """
        SELECT f.*, v.type as violation_type, veh.reg_no as vehicle_reg
        FROM fines f
        LEFT JOIN violations v ON f.violation_id = v.violation_id
        LEFT JOIN vehicles veh ON v.vehicle_id = veh.vehicle_id
        WHERE f.status = 'Unpaid'
    """
    params = []
    if owner_id:
        query += " AND veh.owner_id = ?"
        params.append(owner_id)
    query += " ORDER BY f.fine_id"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify(dict_rows(rows))


# ============================================
# Main
# ============================================

if __name__ == '__main__':
    print("=" * 50)
    print("  TrafficAI — Smart Violation Detection System")
    print("=" * 50)
    init_db()
    migrate_schema()
    seed_data()
    print(f"✓ Database: {DB_PATH}")
    print(f"✓ Server starting at http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, port=5000)
