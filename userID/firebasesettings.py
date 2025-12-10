# settings.py

import firebase_admin
from firebase_admin import credentials
import os
from pathlib import Path

# Path to the service account file (adjust this path)
# It's recommended to place this outside the root of your project
BASE_DIR = Path(__file__).resolve().parent.parent

# Use an environment variable or define the path here
FIREBASE_CRED_PATH = os.path.join(BASE_DIR, 'maxplug-6af34-firebase-adminsdk-fbsvc-61142b2082.json')

# Initialize Firebase Admin SDK
try:
    cred = credentials.Certificate(FIREBASE_CRED_PATH)
    firebase_admin.initialize_app(cred)
    print("Firebase Admin SDK initialized successfully.")
except Exception as e:
    print(f"Error initializing Firebase Admin SDK: {e}")
    # Handle the error appropriately (e.g., raise an exception to halt startup)