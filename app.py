import os
import json
import re
import base64
import traceback
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import google.generativeai as genai
from PIL import Image
from io import BytesIO
from math import radians, cos, sin, sqrt, atan2
from geopy.geocoders import Nominatim
import ssl

# Fix urllib3 SSL warnings (optional)
ssl._create_default_https_context = ssl._create_unverified_context

# Initialize app
app = Flask(__name__)

# Load env variables
load_dotenv(dotenv_path="myenv.env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("❌ Gemini API key not found.")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Load destination dataset
try:
    with open('dataset.json') as f:
        dataset = json.load(f)
    print(f"✅ Loaded {len(dataset)} destinations")
except Exception as e:
    print(f"❌ Error loading dataset: {e}")
    dataset = []

# Utilities
def get_current_season():
    month = datetime.now().month
    return (
        "winter" if month in [12, 1, 2]
        else "summer" if month in [3, 4, 5]
        else "monsoon" if month in [6, 7, 8, 9]
        else "autumn"
    )

def haversine(coord1, coord2):
    R = 6371
    lat1, lon1 = map(radians, coord1)
    lat2, lon2 = map(radians, coord2)
    dlat, dlon = lat2-lat1, lon2-lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

def get_coordinates(city_name):
    if not city_name:
        return None
    city_coords = {
        "mumbai": (19.0760, 72.8777),
        "delhi": (28.6139, 77.2090),
        "bangalore": (12.9716, 77.5946),
        "chennai": (13.0827, 80.2707),
        "hyderabad": (17.3850, 78.4867),
        "kolkata": (22.5726, 88.3639),
        "pune": (18.5204, 73.8567),
        "ahmedabad": (23.0225, 72.5714),
        "jaipur": (26.9124, 75.7873),
        "goa": (15.2993, 74.1240)
    }
    city_key = city_name.strip().lower()
    if city_key in city_coords:
        return city_coords[city_key]
    try:
        geolocator = Nominatim(user_agent="vacayfinder", timeout=10)
        location = geolocator.geocode(f"{city_name}, India")
        return (location.latitude, location.longitude) if location else None
    except:
        return None

# Routes
@app.route('/')
def index(): return render_template('index.html')

@app.route('/questions')
def questions(): return render_template('questions.html')

@app.route('/login')
def login(): return render_template('login.html')

@app.route('/signup')
def signup(): return render_template('signup.html')

@app.route('/about')
def about(): return render_template('about.html')

@app.route('/contact')
def contact(): return render_template('contact.html')

# Destination recommendation
@app.route('/recommend', methods=['POST'])
def recommend():
    try:
        if 'image' not in request.files:
            return jsonify({"error": "Please upload an image"}), 400
        form = request.form
        image_file = request.files['image']
        if image_file.content_length > 5 * 1024 * 1024:
            return jsonify({"error": "Image too large"}), 400

        # User prefs
        current_city = form.get('currentLocation', '').strip()
        max_distance = min(int(form.get('distance', 500)), 2000)
        weather, activity, companion = form.get('weather', 'any'), form.get('activities', 'any'), form.get('companion', 'any')
        season = get_current_season()

        image_bytes = image_file.read()
        pil_image = Image.open(BytesIO(image_bytes))

        prompt = "Analyze the image and respond ONLY with one of: beach, mountain, desert, forest, colonial, spiritual, historic, safari, cultural, urban."

        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content([prompt, pil_image])
        theme = response.text.strip().lower()
        print(f"🎨 Theme: {theme}")

        user_coords = get_coordinates(current_city)
        if not user_coords:
            return jsonify({"error": f"Unable to geolocate {current_city}"}), 400

        filtered = []
        for dest in dataset:
            loc = dest.get("location")
            if loc:
                dist = haversine(user_coords, (loc["latitude"], loc["longitude"]))
                if dist <= max_distance:
                    filtered.append(dest)

        if not filtered:
            return jsonify({"error": "No matching destinations found."}), 404

        prompt2 = f"""
        You are a travel assistant.
        From these destinations: {[d['name'] for d in filtered]},
        pick ONE that matches: Weather: {weather}, Activities: {activity}, Companion: {companion}, Season: {season}, Image Theme: {theme}.
        Respond ONLY as:
        {{"destination": "Name", "location": "City, State", "why_perfect": "Reason", "best_season": "Best time", "local_tip": "Tip"}}
        """

        text_model = genai.GenerativeModel("gemini-1.5-flash")
        rec_response = text_model.generate_content(prompt2)
        response_text = rec_response.text.strip()
        clean_text = re.sub(r"^```(?:json)?|```$", "", response_text, flags=re.MULTILINE).strip()
        print(clean_text)

        recommendation = json.loads(clean_text)
        match = next((d for d in dataset if d['name'].lower() == recommendation['destination'].lower()), None)
        if match:
            recommendation.update({
                "image_url": match.get("image_url"),
                "budget": match.get("budget"),
                "safety_rating": match.get("safety_rating"),
            })

        return jsonify({"success": True, "theme": theme, "recommendation": recommendation})

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# Contact form handling
CONTACT_DB = 'contact_submissions.json'

def init_contact_db():
    if not os.path.exists(CONTACT_DB):
        with open(CONTACT_DB, 'w') as f:
            json.dump([], f)

def validate_contact_data(data):
    if not all(field in data for field in ['name', 'email', 'message']):
        return False
    return all(data.get(field, '').strip() for field in ['name', 'email', 'message'])

@app.route('/submit-contact', methods=['POST'])
def submit_contact():
    try:
        if not request.is_json:
            return jsonify({'error': 'JSON expected'}), 400
        data = request.get_json()
        if not validate_contact_data(data):
            return jsonify({'error': 'All fields required'}), 400
        init_contact_db()
        with open(CONTACT_DB, 'r') as f:
            submissions = json.load(f)
        submissions.append({**data, 'timestamp': datetime.now().isoformat()})
        with open(CONTACT_DB, 'w') as f:
            json.dump(submissions, f, indent=2)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/debug-submissions')
def debug_submissions():
    try:
        init_contact_db()
        with open(CONTACT_DB, 'r') as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Run
if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5001)
