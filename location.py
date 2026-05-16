from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect
from datetime import datetime
import os
import math
import json

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'supersecretkey')
CORS(app)

# Database Configuration
db_path = os.environ.get('DATABASE_PATH', os.path.join(os.path.dirname(__file__), 'locations.db'))
db_dir = os.path.dirname(db_path)
if db_dir:
    os.makedirs(db_dir, exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Models ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(20), nullable=False) # 'admin' or 'user'
    number_plate = db.Column(db.String(20), nullable=True)
    vehicle_type = db.Column(db.String(50), nullable=True)
    phone = db.Column(db.String(15), nullable=True)
    aadhar = db.Column(db.String(12), nullable=True)
    balance = db.Column(db.Float, default=0.0)

class UserLocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    username = db.Column(db.String(80), nullable=True) # Track who sent it
    is_at_checkpoint = db.Column(db.Integer, default=0) # 1 if at location
    road_name = db.Column(db.String(200), nullable=True)

class TollEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    road_name = db.Column(db.String(200), nullable=True)
    event_type = db.Column(db.String(20), nullable=False) # 'ENTRY' or 'EXIT'
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class SystemConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mode = db.Column(db.String(20), default='point')
    target_lat = db.Column(db.Float, nullable=True) # Point mode
    target_lon = db.Column(db.Float, nullable=True) # Point mode
    start_lat = db.Column(db.Float, nullable=True) # Road mode metadata
    start_lon = db.Column(db.Float, nullable=True)
    end_lat = db.Column(db.Float, nullable=True)
    end_lon = db.Column(db.Float, nullable=True)
    road_name = db.Column(db.String(200), nullable=True)
    radius = db.Column(db.Integer, default=50) # Buffer radius
    route_json = db.Column(db.Text, nullable=True) # Full polyline Json

def get_config():
    config = SystemConfig.query.first()
    if not config:
        return {"mode": "point", "lat": 13.0827, "lon": 80.2707, "radius": 50, "routes": []}
    
    routes = []
    if config.route_json:
        try:
            # We now expect route_json to be a list of routes: [ [[lat1, lon1], ...], [[lat2, lon2], ...] ]
            routes = json.loads(config.route_json)
            # Migration path: if it was a single route, wrap it
            if routes and isinstance(routes[0][0], (int, float)):
                routes = [routes]
        except:
            pass
            
    return {
        "mode": config.mode,
        "lat": config.target_lat,
        "lon": config.target_lon,
        "radius": config.radius,
        "routes": routes,
        "road_name": config.road_name or "Active Monitoring Zone"
    }

def calculate_distance(lat1, lon1, lat2, lon2):
    """Haversine formula to calculate distance in meters"""
    R = 6371000 # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def is_near_roads(lat, lon, routes, threshold):
    """Check if point is within threshold meters of any point in ANY of the routes. Returns the matching route."""
    if not routes:
        return False
    
    for route in routes:
        if not route: continue
        # Handle both list of points and objects with 'points' key
        points = route['points'] if isinstance(route, dict) else route
        for point in points:
            dist = calculate_distance(lat, lon, point[0], point[1])
            if dist <= threshold:
                return route
    return False

def matched_road_name(matched_road, fallback):
    if isinstance(matched_road, dict):
        return matched_road.get('name') or fallback
    return fallback

def ensure_schema():
    inspector = inspect(db.engine)
    if 'user_location' in inspector.get_table_names():
        columns = {column['name'] for column in inspector.get_columns('user_location')}
        if 'road_name' not in columns:
            with db.engine.begin() as conn:
                conn.exec_driver_sql('ALTER TABLE user_location ADD COLUMN road_name VARCHAR(200)')


# Create database tables and seed users
with app.app_context():
    db.create_all()
    ensure_schema()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password='admin123', role='admin')
        user = User(username='user', password='user123', role='user')
        db.session.add(admin)
        db.session.add(user)
        
        # Initial config (Point Mode)
        config = SystemConfig(mode='point', target_lat=13.009318, target_lon=80.004176, radius=50)
        db.session.add(config)
        db.session.commit()

# --- Routes ---

@app.route('/')
def index():
    if 'username' not in session: return redirect(url_for('login_page'))
    if session.get('role') == 'admin': return redirect(url_for('admin_page'))
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'frontend.html')

@app.route('/login')
def login_page():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'login.html')

@app.route('/admin')
def admin_page():
    if session.get('role') != 'admin': return redirect(url_for('login_page'))
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'admin.html')

@app.route('/wallet')
def wallet_page():
    if 'username' not in session: return redirect(url_for('login_page'))
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'wallet.html')

@app.route('/admin/wallet')
def admin_wallet_page():
    if session.get('role') != 'admin': return redirect(url_for('login_page'))
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'admin_wallet.html')

@app.route('/admin/crossings')
def admin_crossings_page():
    if session.get('role') != 'admin': return redirect(url_for('login_page'))
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'admin_crossings.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    user = User.query.filter_by(username=data.get('username'), password=data.get('password')).first()
    if user:
        session['username'], session['role'] = user.username, user.role
        return jsonify({"status": "success", "role": user.role, "redirect": url_for('index')})
    return jsonify({"status": "error", "message": "Invalid credentials"}), 401

@app.route('/api/me', methods=['GET'])
def api_me():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    user = User.query.filter_by(username=session['username']).first()
    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404
    return jsonify({
        "status": "success",
        "username": user.username,
        "role": user.role,
        "balance": user.balance
    })

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if User.query.filter_by(username=username).first():
        return jsonify({"status": "error", "message": "Username already exists"}), 400
    
    new_user = User(
        username=username,
        password=password,
        role='user',
        number_plate=data.get('number_plate'),
        vehicle_type=data.get('vehicle_type'),
        phone=data.get('phone'),
        aadhar=data.get('aadhar'),
        balance=0.0
    )
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"status": "success", "message": "Registration successful"})

@app.route('/api/logout')
def api_logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/location', methods=['POST'])
def receive_location():
    if 'username' not in session: return jsonify({"status": "error"}), 401
    
    try:
        data = request.get_json()
        lat, lon = data.get("lat"), data.get("lon")
        config = get_config()
        
        at_checkpoint = 0
        matched_road = None
        road_name = config.get('road_name')
        if config['mode'] == 'point':
            at_checkpoint = 1 if calculate_distance(lat, lon, config['lat'], config['lon']) <= config['radius'] else 0
        else:
            matched_road = is_near_roads(lat, lon, config['routes'], config['radius'])
            at_checkpoint = 1 if matched_road else 0
            if matched_road:
                road_name = matched_road_name(matched_road, config.get('road_name'))

        # Detect transition for events
        last_loc = UserLocation.query.filter_by(username=session['username']).order_by(UserLocation.timestamp.desc()).first()
        prev_at_checkpoint = last_loc.is_at_checkpoint if last_loc else 0

        if prev_at_checkpoint == 0 and at_checkpoint == 1:
            # ENTRY EVENT
            new_event = TollEvent(username=session['username'], road_name=road_name, event_type='ENTRY')
            db.session.add(new_event)
        elif prev_at_checkpoint == 1 and at_checkpoint == 0:
            # EXIT EVENT
            # For exit, we use the road name from the previous location to be accurate
            prev_road = last_loc.road_name if last_loc else road_name
            new_event = TollEvent(username=session['username'], road_name=prev_road, event_type='EXIT')
            db.session.add(new_event)

        # ONLY store in database if user is at the checkpoint/geofence OR if they just exited
        if at_checkpoint or (prev_at_checkpoint == 1 and at_checkpoint == 0):
            cost_deducted = 0.0
            # Calculate distance from last checkpoint and deduct
            if isinstance(matched_road, dict) and matched_road.get('price_per_km'):
                price_per_km = float(matched_road.get('price_per_km', 0))
                # last_loc already fetched above
                if last_loc and last_loc.is_at_checkpoint == 1:
                    time_diff = (datetime.utcnow() - last_loc.timestamp).total_seconds()
                    if time_diff < 300: # Max 5 minutes between pings for continuous distance tracking
                        dist_meters = calculate_distance(lat, lon, last_loc.latitude, last_loc.longitude)
                        km_travelled = dist_meters / 1000.0
                        cost_deducted = km_travelled * price_per_km
                        
                        user_to_charge = User.query.filter_by(username=session['username']).first()
                        if user_to_charge and cost_deducted > 0:
                            user_to_charge.balance -= cost_deducted

            new_location = UserLocation(
                latitude=lat,
                longitude=lon,
                username=session['username'],
                is_at_checkpoint=at_checkpoint,
                road_name=road_name
            )
            db.session.add(new_location)
            db.session.commit()

        user = User.query.filter_by(username=session['username']).first()
        balance = user.balance if user else 0.0

        return jsonify({
            "status": "success",
            "message": "At Target" if at_checkpoint else "Outside",
            "data": {"at_checkpoint": at_checkpoint, "balance": balance, "road_name": road_name}
        })
    except Exception as e:
        print(f"ERROR in receive_location: {str(e)}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Server Error: {str(e)}"}), 500

@app.route('/api/events', methods=['GET'])
def get_events():
    if 'username' not in session: return jsonify({"status": "error"}), 401
    
    query = TollEvent.query
    if session.get('role') != 'admin':
        query = query.filter_by(username=session['username'])
    
    events = query.order_by(TollEvent.timestamp.desc()).limit(100).all()
    return jsonify([{
        "id": event.id, "username": event.username, "road_name": event.road_name,
        "event_type": event.event_type, "timestamp": event.timestamp.isoformat() + 'Z'
    } for event in events])

@app.route('/api/get_target', methods=['GET'])
def api_get_target_route():
    config = get_config()
    if 'username' in session:
        config['username'] = session['username']
        user = User.query.filter_by(username=session['username']).first()
        if user: config['balance'] = user.balance
    return jsonify(config)

@app.route('/api/recharge', methods=['POST'])
def api_recharge():
    if session.get('role') != 'admin': return jsonify({"status": "error", "message": "Unauthorized"}), 403
    
    data = request.get_json()
    username = data.get('username')
    aadhar = data.get('aadhar')
    amount = float(data.get('amount', 0))
    
    user = User.query.filter_by(username=username, aadhar=aadhar).first()
    if not user:
        return jsonify({"status": "error", "message": "User not found or Aadhar mismatch"}), 404
        
    user.balance += amount
    db.session.commit()
    return jsonify({"status": "success", "message": f"Successfully recharged {amount} to {username}", "new_balance": user.balance})

@app.route('/api/set_target', methods=['POST'])
def set_target():
    if session.get('role') != 'admin': return jsonify({"status": "error"}), 401
    
    data = request.get_json()
    config = SystemConfig.query.first()
    if not config: config = SystemConfig()
    
    config.mode = data.get('mode', 'point')
    config.target_lat = data.get('lat')
    config.target_lon = data.get('lon')
    config.radius = data.get('radius', 50)
    config.road_name = data.get('road_name', 'Active Monitoring Zone')
    
    if 'routes' in data:
        config.route_json = json.dumps(data['routes'])
    
    db.session.add(config)
    db.session.commit()
    return jsonify({"status": "success"})


@app.route('/api/locations', methods=['GET'])
def get_all_locations():
    if session.get('role') != 'admin': return jsonify({"status": "error"}), 403
    locations = UserLocation.query.order_by(UserLocation.timestamp.desc()).all()
    return jsonify([{
        "id": loc.id, "username": loc.username, "latitude": loc.latitude, "longitude": loc.longitude,
        "timestamp": loc.timestamp.isoformat() + 'Z', "is_at_checkpoint": loc.is_at_checkpoint,
        "road_name": loc.road_name
    } for loc in locations])

@app.route('/api/crossings', methods=['GET'])
def get_crossings():
    if session.get('role') != 'admin': return jsonify({"status": "error"}), 403

    road = (request.args.get('road') or '').strip()
    search = (request.args.get('search') or '').strip()

    query = UserLocation.query.filter_by(is_at_checkpoint=1)
    if road:
        query = query.filter(UserLocation.road_name == road)
    if search:
        query = query.filter(UserLocation.username.ilike(f'%{search}%'))

    locations = query.order_by(UserLocation.timestamp.desc()).limit(500).all()
    return jsonify([{
        "id": loc.id,
        "username": loc.username,
        "latitude": loc.latitude,
        "longitude": loc.longitude,
        "timestamp": loc.timestamp.isoformat() + 'Z',
        "road_name": loc.road_name or "Active Monitoring Zone"
    } for loc in locations])

@app.route('/api/crossing_roads', methods=['GET'])
def get_crossing_roads():
    if session.get('role') != 'admin': return jsonify({"status": "error"}), 403
    names = set()

    config = get_config()
    for route in config.get('routes', []):
        if isinstance(route, dict) and route.get('name'):
            names.add(route['name'])
    if config.get('road_name'):
        names.add(config['road_name'])

    rows = db.session.query(UserLocation.road_name).filter(
        UserLocation.is_at_checkpoint == 1,
        UserLocation.road_name.isnot(None)
    ).distinct().order_by(UserLocation.road_name.asc()).all()
    names.update(row[0] for row in rows if row[0])
    return jsonify(sorted(names))


if __name__ == '__main__':
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 7000))
    debug = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    print(f"Starting secure authentication & location server on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)
