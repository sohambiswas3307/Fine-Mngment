"""
E Parivahan — Flask Backend with SQLite Database
AI-Based Smart Traffic Violation Detection & Fine Management System
"""

import mysql.connector
from mysql.connector import pooling
import os
import uuid
import threading
import sys
import time
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import cv2

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

# YOLO model removed as per user request (Switching to Classic CV)
model = None
print("Using Classic CV (Background Subtraction) for detection.")

# ============================================
# Database Helpers
# ============================================

# MySQL Configuration
MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',
    'database': 'trafficai',
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci'
}

# Create a connection pool
db_pool = mysql.connector.pooling.MySQLConnectionPool(
    pool_name="traffic_pool",
    pool_size=10,
    **MYSQL_CONFIG
)

def get_db():
    """Get a database connection from the pool."""
    conn = db_pool.get_connection()
    return conn

def dict_row(row, columns):
    """Convert a row tuple to dict using provided column names."""
    return dict(zip(columns, row)) if row else None

def dict_rows(rows, columns):
    """Convert list of row tuples to list of dicts."""
    return [dict(zip(columns, r)) for r in rows]


def next_id(table, prefix):
    """Generate the next sequential ID for a table."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) as cnt FROM {table}")
    row = cursor.fetchone()
    count = row[0] if row else 0
    
    id_col = f"{table[:-1]}_id"
    cursor.execute(f"SELECT {id_col} FROM {table}")
    all_rows = cursor.fetchall()
    nums = []
    for r in all_rows:
        val = r[0]
        try:
            nums.append(int(val.replace(prefix + '-', '')))
        except:
            nums.append(0)
    cursor.close()
    conn.close()
    next_num = max(nums, default=0) + 1
    return f"{prefix}-{str(next_num).zfill(3)}"


# ============================================
# Database Initialization
# ============================================

def init_db():
    """Create tables if they don't exist in MySQL."""
    conn = get_db()
    cursor = conn.cursor()
    
    tables = [
        """CREATE TABLE IF NOT EXISTS cameras (
            camera_id VARCHAR(50) PRIMARY KEY,
            location VARCHAR(255) NOT NULL,
            status VARCHAR(50) DEFAULT 'Active',
            latitude DOUBLE,
            longitude DOUBLE
        )""",
        """CREATE TABLE IF NOT EXISTS owners (
            owner_id VARCHAR(50) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            license_no VARCHAR(255) NOT NULL,
            phone VARCHAR(50),
            email VARCHAR(255)
        )""",
        """CREATE TABLE IF NOT EXISTS vehicles (
            vehicle_id VARCHAR(50) PRIMARY KEY,
            owner_id VARCHAR(50) NOT NULL,
            reg_no VARCHAR(50) NOT NULL,
            type VARCHAR(50) NOT NULL,
            color VARCHAR(50),
            FOREIGN KEY (owner_id) REFERENCES owners(owner_id)
        )""",
        """CREATE TABLE IF NOT EXISTS violations (
            violation_id VARCHAR(50) PRIMARY KEY,
            vehicle_id VARCHAR(50) NOT NULL,
            camera_id VARCHAR(50) NOT NULL,
            type VARCHAR(100) NOT NULL,
            date VARCHAR(50) NOT NULL,
            confidence INT DEFAULT 0,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
            FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
        )""",
        """CREATE TABLE IF NOT EXISTS fines (
            fine_id VARCHAR(50) PRIMARY KEY,
            violation_id VARCHAR(50) NOT NULL,
            amount DOUBLE NOT NULL,
            status VARCHAR(50) DEFAULT 'Unpaid',
            FOREIGN KEY (violation_id) REFERENCES violations(violation_id)
        )""",
        """CREATE TABLE IF NOT EXISTS payments (
            payment_id VARCHAR(50) PRIMARY KEY,
            fine_id VARCHAR(50) NOT NULL,
            amount DOUBLE NOT NULL,
            date VARCHAR(50) NOT NULL,
            mode VARCHAR(50) NOT NULL,
            FOREIGN KEY (fine_id) REFERENCES fines(fine_id)
        )""",
        """CREATE TABLE IF NOT EXISTS users (
            user_id VARCHAR(50) PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL,
            owner_id VARCHAR(50),
            FOREIGN KEY (owner_id) REFERENCES owners(owner_id)
        )"""
    ]
    
    for table_sql in tables:
        cursor.execute(table_sql)
        
    conn.commit()
    cursor.close()
    conn.close()


def migrate_schema():
    """Add camera coordinates for map features; backfill demo pins in MySQL."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Check if columns exist (MySQL specific)
        cursor.execute("SHOW COLUMNS FROM cameras LIKE 'latitude'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE cameras ADD COLUMN latitude DOUBLE")
        cursor.execute("SHOW COLUMNS FROM cameras LIKE 'longitude'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE cameras ADD COLUMN longitude DOUBLE")
        
        for cam_id, (lat, lng) in CAMERA_COORDS.items():
            cursor.execute(
                """UPDATE cameras SET latitude = COALESCE(latitude, %s), longitude = COALESCE(longitude, %s)
                   WHERE camera_id = %s""",
                (lat, lng, cam_id),
            )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def seed_data():
    """Insert demo data if tables are empty in MySQL."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM cameras")
    count = cursor.fetchone()[0]
    if count > 0:
        cursor.close()
        conn.close()
        return

    # Cameras
    cam_rows = [
        ('CAM-001', 'MG Road Junction', 'Active', CAMERA_COORDS['CAM-001'][0], CAMERA_COORDS['CAM-001'][1]),
        ('CAM-002', 'Highway Toll Plaza', 'Active', CAMERA_COORDS['CAM-002'][0], CAMERA_COORDS['CAM-002'][1]),
        ('CAM-003', 'City Center Signal', 'Active', CAMERA_COORDS['CAM-003'][0], CAMERA_COORDS['CAM-003'][1]),
        ('CAM-004', 'Ring Road Flyover', 'Active', CAMERA_COORDS['CAM-004'][0], CAMERA_COORDS['CAM-004'][1]),
        ('CAM-005', 'School Zone - Park Street', 'Active', CAMERA_COORDS['CAM-005'][0], CAMERA_COORDS['CAM-005'][1]),
    ]
    cursor.executemany(
        "INSERT INTO cameras (camera_id, location, status, latitude, longitude) VALUES (%s, %s, %s, %s, %s)",
        cam_rows,
    )

    # Owners
    cursor.executemany("INSERT INTO owners VALUES (%s, %s, %s, %s, %s)", [
        ('OWN-001', 'Rahul Sharma', 'DL-1420110012345', '9876543210', 'rahul.sharma@email.com'),
        ('OWN-002', 'Priya Patel', 'MH-0220090054321', '9876543211', 'priya.patel@email.com'),
        ('OWN-003', 'Amit Kumar', 'KA-0520150098765', '9876543212', 'amit.kumar@email.com'),
        ('OWN-004', 'Sneha Reddy', 'TN-0920180034567', '9876543213', 'sneha.reddy@email.com'),
        ('OWN-005', 'Vikram Singh', 'UP-8020170045678', '9876543214', 'vikram.singh@email.com'),
    ])

    # Vehicles
    cursor.executemany("INSERT INTO vehicles VALUES (%s, %s, %s, %s, %s)", [
        ('VEH-001', 'OWN-001', 'DL-14-AB-1234', 'Car', 'White'),
        ('VEH-002', 'OWN-002', 'MH-02-CD-5678', 'Motorcycle', 'Black'),
        ('VEH-003', 'OWN-003', 'KA-05-EF-9012', 'Car', 'Silver'),
        ('VEH-004', 'OWN-004', 'TN-09-GH-3456', 'Motorcycle', 'Red'),
        ('VEH-005', 'OWN-005', 'UP-80-IJ-7890', 'Truck', 'Blue'),
        ('VEH-006', 'OWN-001', 'DL-14-KL-4567', 'Motorcycle', 'Black'),
    ])

    # Violations
    cursor.executemany("INSERT INTO violations VALUES (%s, %s, %s, %s, %s, %s)", [
        ('VIO-001', 'VEH-002', 'CAM-001', 'Helmetless Riding', '2026-04-26', 94),
        ('VIO-002', 'VEH-003', 'CAM-002', 'Overspeeding', '2026-04-27', 97),
        ('VIO-003', 'VEH-001', 'CAM-003', 'Signal Jumping', '2026-04-28', 92),
        ('VIO-004', 'VEH-004', 'CAM-001', 'Helmetless Riding', '2026-04-29', 96),
        ('VIO-005', 'VEH-005', 'CAM-004', 'Lane Violation', '2026-04-30', 89),
        ('VIO-006', 'VEH-006', 'CAM-005', 'Overspeeding', '2026-04-30', 95),
        ('VIO-007', 'VEH-001', 'CAM-002', 'Illegal Parking', '2026-05-01', 91),
    ])

    # Fines
    cursor.executemany("INSERT INTO fines VALUES (%s, %s, %s, %s)", [
        ('FIN-001', 'VIO-001', 500, 'Paid'),
        ('FIN-002', 'VIO-002', 2000, 'Paid'),
        ('FIN-003', 'VIO-003', 1000, 'Unpaid'),
        ('FIN-004', 'VIO-004', 500, 'Unpaid'),
        ('FIN-005', 'VIO-005', 1000, 'Unpaid'),
        ('FIN-006', 'VIO-006', 2000, 'Unpaid'),
        ('FIN-007', 'VIO-007', 500, 'Unpaid'),
    ])

    # Payments
    cursor.executemany("INSERT INTO payments VALUES (%s, %s, %s, %s, %s)", [
        ('PAY-001', 'FIN-001', 500, '2026-04-28', 'UPI'),
        ('PAY-002', 'FIN-002', 2000, '2026-04-29', 'Credit Card'),
    ])

    # Users
    cursor.executemany("INSERT INTO users VALUES (%s, %s, %s, %s, %s)", [
        ('USR-001', 'admin', 'admin123', 'Admin', None),
        ('USR-002', 'rahul', 'rahul123', 'User', 'OWN-001'),
        ('USR-003', 'priya', 'priya123', 'User', 'OWN-002'),
        ('USR-004', 'amit', 'amit123', 'User', 'OWN-003'),
    ])

    conn.commit()
    cursor.close()
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
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
    user = cursor.fetchone()
    
    if user:
        u = dict_row(user, cursor.column_names)
        cursor.close()
        conn.close()
        return jsonify({
            'success': True,
            'user': {
                'username': u['username'],
                'role': u['role'],
                'owner_id': u['owner_id']
            }
        })
    cursor.close()
    conn.close()
    return jsonify({'success': False, 'message': 'Invalid username or password'}), 401


@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # 1. Check if user already exists
        cursor.execute("SELECT * FROM users WHERE username = %s", (data['username'],))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Username already exists'}), 400

        # 2. Generate IDs
        own_id = next_id('owners', 'OWN')
        veh_id = next_id('vehicles', 'VEH')
        usr_id = next_id('users', 'USR')

        # 3. Insert Owner
        cursor.execute(
            "INSERT INTO owners VALUES (%s, %s, %s, %s, %s)",
            (own_id, data['name'], data['license_no'], data.get('phone', ''), data.get('email', ''))
        )

        # 4. Insert Vehicle
        cursor.execute(
            "INSERT INTO vehicles VALUES (%s, %s, %s, %s, %s)",
            (veh_id, own_id, data['vehicle_reg'], data['vehicle_type'], data.get('vehicle_color', ''))
        )

        # 5. Insert User
        cursor.execute(
            "INSERT INTO users VALUES (%s, %s, %s, %s, %s)",
            (usr_id, data['username'], data['password'], 'User', own_id)
        )

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'success': True, 'message': 'Registration successful!'})
        
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================
# API: Dashboard Stats
# ============================================

@app.route('/api/stats')
def get_stats():
    owner_id = request.args.get('owner_id')
    conn = get_db()
    cursor = conn.cursor()
    
    if owner_id:
        # User-specific stats
        cursor.execute("""
            SELECT COUNT(*) FROM violations v
            JOIN vehicles veh ON v.vehicle_id = veh.vehicle_id
            WHERE veh.owner_id = %s
        """, (owner_id,))
        total_violations = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM cameras WHERE status = 'Active'")
        total_cameras = cursor.fetchone()[0]
        
        collected = 0
        
        cursor.execute("""
            SELECT COALESCE(SUM(f.amount), 0) FROM fines f
            JOIN violations v ON f.violation_id = v.violation_id
            JOIN vehicles veh ON v.vehicle_id = veh.vehicle_id
            WHERE f.status = 'Unpaid' AND veh.owner_id = %s
        """, (owner_id,))
        pending = cursor.fetchone()[0]

        recent_query = """
            SELECT v.violation_id, v.type, v.date, v.confidence,
                   veh.reg_no as vehicle_reg,
                   c.location as camera_location,
                   COALESCE(f.status, 'N/A') as fine_status
            FROM violations v
            JOIN vehicles veh ON v.vehicle_id = veh.vehicle_id
            LEFT JOIN cameras c ON v.camera_id = c.camera_id
            LEFT JOIN fines f ON f.violation_id = v.violation_id
            WHERE veh.owner_id = %s
            ORDER BY v.date DESC, v.violation_id DESC
            LIMIT 10
        """
        cursor.execute(recent_query, (owner_id,))
        recent_rows = cursor.fetchall()
        recent = dict_rows(recent_rows, cursor.column_names)
        
        cursor.execute("""
            SELECT v.type, COUNT(*) as count FROM violations v
            JOIN vehicles veh ON v.vehicle_id = veh.vehicle_id
            WHERE veh.owner_id = %s
            GROUP BY v.type ORDER BY count DESC
        """, (owner_id,))
        type_counts = dict_rows(cursor.fetchall(), cursor.column_names)

        cursor.execute("SELECT name, license_no FROM owners WHERE owner_id = %s", (owner_id,))
        owner_info = cursor.fetchone()
        owner_name = owner_info[0] if owner_info else 'Unknown'
        license_no = owner_info[1] if owner_info else 'N/A'

        cursor.execute("SELECT COUNT(*) FROM vehicles WHERE owner_id = %s", (owner_id,))
        registered_vehicles = cursor.fetchone()[0]
        
    else:
        # Admin global stats
        cursor.execute("SELECT COUNT(*) FROM violations")
        total_violations = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM cameras")
        total_cameras = cursor.fetchone()[0]
        cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM payments")
        collected = cursor.fetchone()[0]
        cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM fines WHERE status = 'Unpaid'")
        pending = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM owners")
        registered_owners = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM vehicles")
        registered_vehicles = cursor.fetchone()[0]

        cursor.execute("""
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
        """)
        recent = dict_rows(cursor.fetchall(), cursor.column_names)

        cursor.execute("SELECT type, COUNT(*) as count FROM violations GROUP BY type ORDER BY count DESC")
        type_counts = dict_rows(cursor.fetchall(), cursor.column_names)

    cursor.close()
    conn.close()
    payload = {
        'totalViolations': total_violations,
        'totalCameras': total_cameras,
        'finesCollected': collected,
        'pendingFines': pending,
        'recentViolations': recent,
        'violationTypes': type_counts,
        'registeredVehicles': registered_vehicles,
    }
    if owner_id:
        payload['licenseNo'] = license_no
        payload['ownerName'] = owner_name
    else:
        payload['registeredOwners'] = registered_owners
    return jsonify(payload)


@app.route('/api/map/hotspots')
def map_hotspots():
    """Admin dashboard: camera locations with violation / fine density for live map."""
    if request.args.get('owner_id'):
        return jsonify({'ok': False, 'message': 'Admin only'}), 403
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
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
    """)
    rows = cursor.fetchall()
    columns = cursor.column_names
    cursor.close()
    conn.close()

    center_lat, center_lng = CITY_MAP_DEFAULT['center']
    rows_list = dict_rows(rows, columns)
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
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cameras ORDER BY camera_id")
    rows = cursor.fetchall()
    res = dict_rows(rows, cursor.column_names)
    cursor.close()
    conn.close()
    return jsonify(res)


@app.route('/api/cameras', methods=['POST'])
def create_camera():
    data = request.json
    cam_id = next_id('cameras', 'CAM')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO cameras (camera_id, location, status, latitude, longitude) VALUES (%s, %s, %s, %s, %s)",
        (cam_id, data['location'], data.get('status', 'Active'),
         data.get('latitude'), data.get('longitude')),
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'id': cam_id, 'message': 'Camera added'}), 201


@app.route('/api/cameras/<cam_id>', methods=['PUT'])
def update_camera(cam_id):
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE cameras SET location=%s, status=%s, latitude=%s, longitude=%s WHERE camera_id=%s",
        (data['location'], data.get('status', 'Active'),
         data.get('latitude'), data.get('longitude'), cam_id),
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'message': 'Camera updated'})


@app.route('/api/cameras/<cam_id>', methods=['DELETE'])
def delete_camera(cam_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cameras WHERE camera_id=%s", (cam_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'message': 'Camera deleted'})


# ============================================
# API: Owners
# ============================================

@app.route('/api/owners', methods=['GET'])
def list_owners():
    owner_id = request.args.get('owner_id')
    conn = get_db()
    cursor = conn.cursor()
    if owner_id:
        cursor.execute("SELECT * FROM owners WHERE owner_id = %s", (owner_id,))
    else:
        cursor.execute("SELECT * FROM owners ORDER BY owner_id")
    rows = cursor.fetchall()
    res = dict_rows(rows, cursor.column_names)
    cursor.close()
    conn.close()
    return jsonify(res)


@app.route('/api/owners', methods=['POST'])
def create_owner():
    data = request.json
    own_id = next_id('owners', 'OWN')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO owners VALUES (%s, %s, %s, %s, %s)",
                 (own_id, data['name'], data['license_no'], data.get('phone', ''), data.get('email', '')))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'id': own_id, 'message': 'Owner added'}), 201


@app.route('/api/owners/<own_id>', methods=['PUT'])
def update_owner(own_id):
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE owners SET name=%s, license_no=%s, phone=%s, email=%s WHERE owner_id=%s",
                 (data['name'], data['license_no'], data.get('phone', ''), data.get('email', ''), own_id))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'message': 'Owner updated'})


@app.route('/api/owners/<own_id>', methods=['DELETE'])
def delete_owner(own_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM owners WHERE owner_id=%s", (own_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'message': 'Owner deleted'})


# ============================================
# API: Vehicles
# ============================================

@app.route('/api/vehicles', methods=['GET'])
def list_vehicles():
    owner_id = request.args.get('owner_id')
    conn = get_db()
    cursor = conn.cursor()
    query = """
        SELECT v.*, o.name as owner_name
        FROM vehicles v
        LEFT JOIN owners o ON v.owner_id = o.owner_id
    """
    if owner_id:
        query += " WHERE v.owner_id = %s"
        cursor.execute(query, (owner_id,))
    else:
        query += " ORDER BY v.vehicle_id"
        cursor.execute(query)
    
    rows = cursor.fetchall()
    res = dict_rows(rows, cursor.column_names)
    cursor.close()
    conn.close()
    return jsonify(res)


@app.route('/api/vehicles', methods=['POST'])
def create_vehicle():
    data = request.json
    veh_id = next_id('vehicles', 'VEH')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO vehicles VALUES (%s, %s, %s, %s, %s)",
                 (veh_id, data['owner_id'], data['reg_no'], data['type'], data.get('color', '')))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'id': veh_id, 'message': 'Vehicle added'}), 201


@app.route('/api/vehicles/<veh_id>', methods=['PUT'])
def update_vehicle(veh_id):
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE vehicles SET owner_id=%s, reg_no=%s, type=%s, color=%s WHERE vehicle_id=%s",
                 (data['owner_id'], data['reg_no'], data['type'], data.get('color', ''), veh_id))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'message': 'Vehicle updated'})


@app.route('/api/vehicles/<veh_id>', methods=['DELETE'])
def delete_vehicle(veh_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM vehicles WHERE vehicle_id=%s", (veh_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'message': 'Vehicle deleted'})


# ============================================
# API: Violations
# ============================================

@app.route('/api/violations', methods=['GET'])
def list_violations():
    owner_id = request.args.get('owner_id')
    conn = get_db()
    cursor = conn.cursor()
    query = """
        SELECT v.*, veh.reg_no as vehicle_reg, c.location as camera_location,
               COALESCE(f.status, 'N/A') as fine_status, f.fine_id, f.amount as fine_amount
        FROM violations v
        LEFT JOIN vehicles veh ON v.vehicle_id = veh.vehicle_id
        LEFT JOIN cameras c ON v.camera_id = c.camera_id
        LEFT JOIN fines f ON f.violation_id = v.violation_id
    """
    if owner_id:
        query += " WHERE veh.owner_id = %s"
        query += " ORDER BY v.date DESC, v.violation_id DESC"
        cursor.execute(query, (owner_id,))
    else:
        query += " ORDER BY v.date DESC, v.violation_id DESC"
        cursor.execute(query)
    
    rows = cursor.fetchall()
    res = dict_rows(rows, cursor.column_names)
    cursor.close()
    conn.close()
    return jsonify(res)


@app.route('/api/violations', methods=['POST'])
def create_violation():
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
    cursor = conn.cursor()
    cursor.execute("INSERT INTO violations VALUES (%s, %s, %s, %s, %s, %s)",
                 (vio_id, data['vehicle_id'], data['camera_id'], data['type'], data['date'], confidence))

    fin_id = next_id('fines', 'FIN')
    cursor.execute("INSERT INTO fines VALUES (%s, %s, %s, %s)",
                 (fin_id, vio_id, amount, 'Unpaid'))

    conn.commit()
    cursor.close()
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
    cursor = conn.cursor()
    cursor.execute("DELETE FROM fines WHERE violation_id=%s", (vio_id,))
    cursor.execute("DELETE FROM violations WHERE violation_id=%s", (vio_id,))
    conn.commit()
    cursor.close()
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
    cursor = conn.cursor()
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
        query += " AND veh.owner_id = %s"
        params.append(owner_id)
    elif status_filter != 'all':
        query += " AND f.status = %s"
        params.append(status_filter)

    query += " ORDER BY f.fine_id DESC"
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    res = dict_rows(rows, cursor.column_names)
    cursor.close()
    conn.close()
    return jsonify(res)


# ============================================
# API: Payments
# ============================================

@app.route('/api/payments', methods=['GET'])
def list_payments():
    owner_id = request.args.get('owner_id')
    conn = get_db()
    cursor = conn.cursor()
    if owner_id:
        cursor.execute("""
            SELECT p.* FROM payments p
            JOIN fines f ON p.fine_id = f.fine_id
            JOIN violations v ON f.violation_id = v.violation_id
            JOIN vehicles veh ON v.vehicle_id = veh.vehicle_id
            WHERE veh.owner_id = %s
            ORDER BY p.date DESC, p.payment_id DESC
        """, (owner_id,))
    else:
        cursor.execute("SELECT * FROM payments ORDER BY date DESC, payment_id DESC")
    rows = cursor.fetchall()
    res = dict_rows(rows, cursor.column_names)
    cursor.close()
    conn.close()
    return jsonify(res)


@app.route('/api/payments', methods=['POST'])
def create_payment():
    data = request.json
    pay_id = next_id('payments', 'PAY')
    fine_id = data['fine_id']

    conn = get_db()
    cursor = conn.cursor()
    # Get fine amount
    cursor.execute("SELECT * FROM fines WHERE fine_id=%s", (fine_id,))
    fine_row = cursor.fetchone()
    if not fine_row:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Fine not found'}), 404

    fine = dict_row(fine_row, cursor.column_names)
    amount = fine['amount']

    cursor.execute("INSERT INTO payments VALUES (%s, %s, %s, %s, %s)",
                 (pay_id, fine_id, amount, data['date'], data['mode']))
    # Update fine status to Paid
    cursor.execute("UPDATE fines SET status='Paid' WHERE fine_id=%s", (fine_id,))
    conn.commit()
    cursor.close()
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
    cursor = conn.cursor()
    cursor.execute("INSERT INTO violations VALUES (%s, %s, %s, %s, %s, %s)",
                 (vio_id, data['vehicle_id'], data['camera_id'], data['type'], data['date'], confidence))

    fin_id = next_id('fines', 'FIN')
    cursor.execute("INSERT INTO fines VALUES (%s, %s, %s, %s)",
                 (fin_id, vio_id, amount, 'Unpaid'))

    conn.commit()
    cursor.close()
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
    """
    Background task: runs real CV-based violation detection on the uploaded video.
    Uses ViolationDetector (violation_detector.py) which detects:
      - Signal Jumping  (traffic light HSV state + stop-line tracking)
      - Lane Violation  (Hough lane lines + ByteTrack centroid crossing)
    """
    import random
    from violation_detector import ViolationDetector

    job_id = filename
    processing_jobs[job_id] = {
        'status': 'processing', 'progress': 0,
        'detections': [], 'output_video': None
    }

    input_path   = os.path.join(UPLOAD_FOLDER, filename)
    out_filename = f"processed_{filename}"
    output_path  = os.path.join(PROCESSED_FOLDER, out_filename)

    # Pull vehicles from DB so we can link detections to real records
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vehicles")
    rows = cursor.fetchall()
    vehicles = dict_rows(rows, cursor.column_names)
    cursor.close()
    conn.close()
    if not vehicles:
        processing_jobs[job_id]['status'] = 'error'
        processing_jobs[job_id]['message'] = 'No vehicles in database to link violations to'
        return

    fine_amounts = {
        'Signal Jumping': 1000, 'Lane Violation': 1000,
        'Overspeeding': 2000,   'Wrong Way Driving': 2000,
        'Helmetless Riding': 500, 'Illegal Parking': 500,
        'Using Mobile Phone': 1500, 'Accident': 5000,
    }

    try:
        detector = ViolationDetector(camera_id=camera_id)
        all_raw_violations = []

        for progress, frame, frame_violations in detector.process(input_path, output_path):
            processing_jobs[job_id]['progress'] = progress
            all_raw_violations.extend(frame_violations)

        # ── Deduplicate ──
        deduped = []
        seen_windows = {}
        for v in all_raw_violations:
            window_key = (v['type'], int(v['timestamp'] // 10))
            if window_key not in seen_windows:
                seen_windows[window_key] = True
                deduped.append(v)

        # ── Persist to database (Fixing ID collision) ──
        saved = []
        conn = get_db()
        cursor = conn.cursor()
        date_str = time.strftime('%Y-%m-%d')
        
        # Pre-fetch starting IDs to avoid collisions in loop
        curr_vio_num = int(next_id('violations', 'VIO').split('-')[1])
        curr_fin_num = int(next_id('fines', 'FIN').split('-')[1])

        for v in deduped:
            assigned_veh = random.choice(vehicles)
            
            vio_id = f"VIO-{str(curr_vio_num).zfill(3)}"
            curr_vio_num += 1
            
            cursor.execute(
                "INSERT INTO violations VALUES (%s, %s, %s, %s, %s, %s)",
                (vio_id, assigned_veh['vehicle_id'], camera_id,
                 v['type'], date_str, v['confidence'])
            )
            
            fin_id = f"FIN-{str(curr_fin_num).zfill(3)}"
            curr_fin_num += 1
            
            amount = fine_amounts.get(v['type'], 500)
            cursor.execute(
                "INSERT INTO fines VALUES (%s, %s, %s, %s)",
                (fin_id, vio_id, amount, 'Unpaid')
            )
            saved.append({
                **v,
                'violation_id': vio_id,
                'fine_id':      fin_id,
                'amount':       amount,
                'vehicle_id':   assigned_veh['vehicle_id'],
                'vehicle_reg':  assigned_veh['reg_no'],
            })
        conn.commit()
        conn.close()

        processing_jobs[job_id].update({
            'status':       'completed',
            'progress':     100,
            'output_video': out_filename,
            'detections':   saved,
        })
        print(f"[Detector] Done — {len(saved)} violation(s) saved for job {job_id}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        processing_jobs[job_id]['status']  = 'error'
        processing_jobs[job_id]['message'] = str(e)

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
    cursor = conn.cursor()
    query = """
        SELECT f.*, v.type as violation_type, veh.reg_no as vehicle_reg
        FROM fines f
        LEFT JOIN violations v ON f.violation_id = v.violation_id
        LEFT JOIN vehicles veh ON v.vehicle_id = veh.vehicle_id
        WHERE f.status = 'Unpaid'
    """
    params = []
    if owner_id:
        query += " AND veh.owner_id = %s"
        params.append(owner_id)
    query += " ORDER BY f.fine_id"
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    res = dict_rows(rows, cursor.column_names)
    cursor.close()
    conn.close()
    return jsonify(res)


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
    print(f"✓ Database: MySQL (host: {MYSQL_CONFIG['host']}, db: {MYSQL_CONFIG['database']})")
    print(f"✓ Server starting at http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, port=5000)
