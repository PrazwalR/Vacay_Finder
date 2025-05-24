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
from google import genai
from PIL import Image
from io import BytesIO
import ssl
ssl._create_default_https_context = ssl._create_unverified_context


# Initialize app
app = Flask(__name__)

# Load environment variables
load_dotenv(dotenv_path="myenv.env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("❌ Gemini API key not found. Check your .env file")

# Initialize Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# Load dataset
try:
    with open('dataset.json') as f:
        dataset = json.load(f)
    print(f"✅ Loaded {len(dataset)} destinations")
except Exception as e:
    print(f"❌ Error loading dataset: {e}")
    dataset = []




from math import radians, cos, sin, sqrt, atan2
from geopy.geocoders import Nominatim

# Helper: current season
def get_current_season():
    month = datetime.now().month
    if month in [12, 1, 2]:
        return "winter"
    elif month in [3, 4, 5]:
        return "summer"
    elif month in [6, 7, 8, 9]:
        return "monsoon"
    else:
        return "autumn"


# Haversine formula to calculate distance between two lat/lon points
def haversine(coord1, coord2):
    R = 6371  # Earth radius in km
    lat1, lon1 = map(radians, coord1)
    lat2, lon2 = map(radians, coord2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

# Hybrid city to coordinates
def get_coordinates(city_name):
    """Hybrid geolocation with fallbacks"""
    if not city_name:
        return None

    # 1. Check hardcoded cities first
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

    # 2. Try Nominatim with error handling
    try:
        geolocator = Nominatim(
            user_agent="vacayfinder",
            timeout=10,
            domain="nominatim.openstreetmap.org"
        )
        location = geolocator.geocode(f"{city_name}, India")
        return (location.latitude, location.longitude) if location else None
    except Exception as e:
        print(f"Geocoding error for {city_name}: {str(e)}")
        return None



# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/questions')
def questions():
    return render_template('questions.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/recommend', methods=['POST'])
def recommend():
    try:
        if 'image' not in request.files:
            return jsonify({"error": "Please upload an image"}), 400

        form = request.form
        image_file = request.files['image']
        if image_file.content_length > 5 * 1024 * 1024:
            return jsonify({"error": "Image too large (max 5MB)"}), 400

        # Get user preferences FIRST
        current_city = form.get('currentLocation', '').strip()
        max_distance = min(int(form.get('distance', 500)), 2000)
        weather = form.get('weather', 'any')
        activity = form.get('activities', 'any')
        companion = form.get('companion', 'any')
        current_season = get_current_season()

        image_bytes = image_file.read()
        pil_image = Image.open(BytesIO(image_bytes))

        # Step 1: Get user's coordinates from city name
        user_coords = get_coordinates(current_city)
        if not user_coords:
            return jsonify({"error": f"Unable to geolocate starting city: {current_city}"}), 400

        # Step 2: Filter destinations within max_distance km
        filtered = []
        for dest in dataset:
            location = dest.get("location")
            if location and "latitude" in location and "longitude" in location:
                dest_coords = (location["latitude"], location["longitude"])
                distance = haversine(user_coords, dest_coords)
                if distance <= max_distance:
                    filtered.append(dest)

        # Debug log
        print(f"📍 {len(filtered)} destinations within {max_distance} km of {current_city}: {[d['name'] for d in filtered]}")

        # Step 3: Handle no nearby matches
        if not filtered:
            return jsonify({"error": "No destinations found within your travel range."}), 404


        # Gemini image classification (theme detection)
        prompt = (
            "Analyze the image and respond ONLY with one of the following themes: "
            "beach, mountain, desert, forest, colonial, spiritual, historic, safari, cultural, urban. "
            "No explanations. Just the single word."
        )

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[prompt, pil_image]
        )
        theme = response.text.strip().lower()
        print(f"🎨 Gemini classified theme: {theme}")

        # Generate recommendation
        current_city = form.get('currentLocation', '').strip()
        max_distance = min(int(form.get('distance', 500)), 2000)
        weather = form.get('weather', 'any')
        activity = form.get('activities', 'any')
        companion = form.get('companion', 'any')
        current_season = get_current_season()

        prompt2 = f"""
        You are a travel assistant.

        Here is a shortlist of destinations that are within {max_distance}km of {current_city}:

        {[d['name'] + ', ' + d.get('state', '') for d in filtered]}

        Do not pick any destination that is not in this list.

        The user prefers:
        - Weather: {weather}
        - Activities: {activity}
        - Companion: {companion}
        - Season: {current_season}
        - Image Theme: {theme}

        Choose ONE destination from the list above that best matches all the preferences.

        Respond ONLY in this exact JSON format:

        {{
        "destination": "Destination Name",
        "location": "City, State",
        "why_perfect": "Short explanation",
        "best_season": "Ideal time to visit",
        "local_tip": "2-day itinerary or local hack"
        }}
        """


        rec_response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt2
        )

        response_text = rec_response.text.strip()
        clean_text = re.sub(r"^```(?:json)?|```$", "", response_text, flags=re.MULTILINE).strip()

        print(f"🧾 Gemini raw response:\n{response_text}")
        print(f"📦 Cleaned for JSON parsing:\n{clean_text}")

        recommendation = json.loads(clean_text)

        match = next((d for d in dataset if d['name'].lower() == recommendation['destination'].lower()), None)
        if match:
            recommendation.update({
                "image_url": match.get("image_url"),
                "budget": match.get("budget"),
                "safety_rating": match.get("safety_rating"),
            })

        return jsonify({
            "success": True,
            "theme": theme,
            "recommendation": recommendation
        })

    except Exception as e:
        print(f"❌ Internal server error:\n{traceback.format_exc()}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5001)


CONTACT_DB = 'contact_submissions.json'

def init_contact_db():
    """Initialize JSON file with empty list if it doesn't exist."""
    if not os.path.exists(CONTACT_DB):
        with open(CONTACT_DB, 'w', encoding='utf-8') as f:
            json.dump([], f, indent=2)

def validate_contact_data(data):
    """Validate and sanitize input data."""
    if not all(field in data for field in ['name', 'email', 'message']):
        return False
    # Trim whitespace and ensure fields aren't empty
    data['name'] = data.get('name', '').strip()
    data['email'] = data.get('email', '').strip()
    data['message'] = data.get('message', '').strip()
    return all(data.values())  # Returns False if any field is empty

@app.route('/submit-contact', methods=['POST'])
def submit_contact():
    try:
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400

        data = request.get_json()
        
        # Validate and sanitize
        if not validate_contact_data(data):
            return jsonify({'error': 'All fields are required'}), 400

        # Initialize DB and load submissions
        init_contact_db()
        with open(CONTACT_DB, 'r', encoding='utf-8') as f:
            submissions = json.load(f)

        # Add submission with timestamp
        submissions.append({
            **data,
            'timestamp': datetime.now().isoformat()
        })

        # Save back to file
        with open(CONTACT_DB, 'w', encoding='utf-8') as f:
            json.dump(submissions, f, indent=2)

        return jsonify({'success': True, 'message': 'Submission saved!'})

    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/view-submissions')
def view_submissions():
    """Admin-only route to view submissions."""
    try:
        init_contact_db()
        with open(CONTACT_DB, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/debug-submissions')
def debug_submissions():
    try:
        with open(CONTACT_DB, 'r') as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({'error': str(e)})