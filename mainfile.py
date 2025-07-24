from flask import Flask, request, jsonify
from flask_cors import CORS
import joblib
import requests

app = Flask(__name__)
CORS(app)

model = joblib.load("mood_models.pkl")
tfidf = joblib.load("tfidf_vectorizers.pkl")

import os
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

MOOD_CATEGORY_MAP = {
    "sadness": "cafes",
    "joy": "entertainment",
    "anger": "gyms",
    "fear": "spiritual_center",
    "love": "desserts"
}

def get_google_places(mood, location):
    category = MOOD_CATEGORY_MAP.get(mood, "activities")
    url = f"https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": f"{category} in {location}",
        "key": GOOGLE_API_KEY
    }
    res = requests.get(url, params=params)
    results = res.json().get("results", [])
    return [{
        "name": r["name"],
        "address": r.get("formatted_address", ""),
        "url": f"https://www.google.com/maps/place/?q=place_id:{r['place_id']}"
    } for r in results[:5]]  # return top 5

@app.route("/")
def home():
    return "MoodMatch backend is running!"

@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()
    text = data.get("text", "")
    city = data.get("city", "Cleveland")

    if not text:
        return jsonify({"error": "Text is required"}), 400

    vec = tfidf.transform([text])
    mood = model.predict(vec)[0].lower()

    suggestions = {
        "sadness": ["Visit a cozy cafe", "Write in a journal", "Watch a comfort show"],
        "joy": ["Join a group activity", "Attend a local event", "Go dancing"],
        "anger": ["Do a workout", "Go boxing", "Take a walk"],
        "fear": ["Try meditation", "Read a calming book", "Talk to a friend"],
        "love": ["Go for dessert", "Visit a gallery", "Plan a picnic"]
    }.get(mood, ["Explore your city", "Try something new"])

    places = get_google_places(mood, city)

    return jsonify({
        "predicted_mood": mood,
        "suggestions": suggestions,
        "places_links": places
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

