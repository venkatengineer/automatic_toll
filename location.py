from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)

# Database Configuration
db_path = os.path.join(os.path.dirname(__file__), 'locations.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

@app.route('/')
def index():
    return app.send_static_file('frontend.html')

# Location Model
class Location(db.Model):
    id = db.Column(db.Column(db.Integer).type, primary_key=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timestamp": self.timestamp.isoformat()
        }

# Simplified model definition to ensure it works on fresh run
class UserLocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# Create database tables
with app.app_context():
    db.create_all()

@app.route('/location', methods=['POST'])
def receive_location():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        lat = data.get("lat")
        lon = data.get("lon")

        if lat is None or lon is None:
            return jsonify({"status": "error", "message": "Missing coordinates"}), 400

        # Save to Database
        new_location = UserLocation(latitude=lat, longitude=lon)
        db.session.add(new_location)
        db.session.commit()

        print(f"✓ Location Secured in Database: Lat {lat}, Lon {lon}")

        return jsonify({
            "status": "success",
            "message": "Location synchronized and stored successfully",
            "data": {
                "latitude": lat,
                "longitude": lon,
                "db_id": new_location.id
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/locations', methods=['GET'])
def get_all_locations():
    locations = UserLocation.query.order_by(UserLocation.timestamp.desc()).all()
    return jsonify([
        {
            "id": loc.id,
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "timestamp": loc.timestamp.isoformat()
        } for loc in locations
    ])

if __name__ == '__main__':
    print("Starting secure location sync server on http://127.0.0.1:5000")
    app.run(debug=True, port=5000)