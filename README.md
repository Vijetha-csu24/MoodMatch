# MoodMatch 🎭

MoodMatch is a smart, emotionally aware web app that helps Gen Z users (ages 13–25) discover real-world activities and places based on their current mood.

## Features
- ML-powered mood prediction based on user input
- Suggestions based on mood (e.g., joy → concerts, sadness → cozy cafes)
- Google Places API integration for local activity recommendations


## Technologies Used
- Python (Flask) for backend API
- HTML/CSS/JavaScript for frontend
- scikit-learn + TF-IDF + Logistic Regression for mood classification
- Google Maps API for location-based suggestions

## 📁 Folder Structure
```
MoodMatch/
├── backend/
│   ├── app.py
│   ├── mood_models.pkl
│   ├── tfidf_vectorizers.pkl
│   └── requirements.txt
│
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── script.js
```

## 🚀 How to Run (Locally)
1. Clone the repo
2. Navigate to `backend/`:
   ```
   pip install -r requirements.txt
   python app.py
   ```
3. Open `frontend/index.html` in a browser

## 🌐 Live Demo
https://3f550acc-32dd-4a97-aad4-fa0a1ad47c3a-00-hqupe0z5dxmi.spock.replit.dev/ 
https://6c025374-f7ad-4605-aa81-f1713f43f9fb-00-ebb7xzk88wjx.kirk.replit.dev/

---

Created by Sai Vijetha
