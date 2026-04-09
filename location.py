from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import math
import json

app = Flask(__name__)
app.secret_key = 'supersecretkey' # In a real app, use an environment variable
CORS(app)

# Database Configuration
db_path = os.path.join(os.path.dirname(__file__), 'locations.db')
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
    """Check if point is within threshold meters of any point in ANY of the routes"""
    if not routes:
        return False
    
    for route in routes:
        if not route: continue
        # Handle both list of points and objects with 'points' key
        points = route['points'] if isinstance(route, dict) else route
        for point in points:
            dist = calculate_distance(lat, lon, point[0], point[1])
            if dist <= threshold:
                return True
    return False


# Create database tables and seed users
with app.app_context():
    db.create_all()
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

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    user = User.query.filter_by(username=data.get('username'), password=data.get('password')).first()
    if user:
        session['username'], session['role'] = user.username, user.role
        return jsonify({"status": "success", "role": user.role, "redirect": url_for('index')})
    return jsonify({"status": "error", "message": "Invalid credentials"}), 401

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
        if config['mode'] == 'point':
            at_checkpoint = 1 if calculate_distance(lat, lon, config['lat'], config['lon']) <= config['radius'] else 0
        else:
            at_checkpoint = 1 if is_near_roads(lat, lon, config['routes'], config['radius']) else 0

        new_location = UserLocation(latitude=lat, longitude=lon, username=session['username'], is_at_checkpoint=at_checkpoint)
        db.session.add(new_location)
        db.session.commit()

        user = User.query.filter_by(username=session['username']).first()
        balance = user.balance if user else 0.0

        return jsonify({
            "status": "success",
            "message": "At Target" if at_checkpoint else "Outside",
            "data": {"at_checkpoint": at_checkpoint, "balance": balance}
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/get_target', methods=['GET'])
def api_get_target_route():
    config = get_config()
    if 'username' in session:
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
        "timestamp": loc.timestamp.isoformat(), "is_at_checkpoint": loc.is_at_checkpoint
    } for loc in locations])


if __name__ == '__main__':
    print("Starting secure authentication & location server on http://127.0.0.1:5000")
    app.run(debug=True, port=5000)