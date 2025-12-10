from django.apps import AppConfig
import os
from django.apps import AppConfig
from django.conf import settings

# Only import Firebase packages here
# We delay the import to avoid an error if settings aren't loaded yet
# but Django will handle the timing correctly by running this in ready()
import firebase_admin
from firebase_admin import credentials
from firebase_admin import auth 
from firebase_admin import exceptions # Optional: useful for specific error handling



class UseridConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'userID'

    def ready(self):
        # Prevent initialization from running twice if settings load multiple times
        if not firebase_admin._apps:
            print("--- Initializing Firebase Admin SDK ---")
            
            # 1. Get the path to your credentials file
            # Assuming you set a variable like FIREBASE_CREDENTIALS_PATH in settings.py
            cred_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', None)
            
            if cred_path and os.path.exists(cred_path):
                # 2. Load the certificate
                cred = credentials.Certificate(cred_path)
                
                # 3. Initialize the app
                firebase_admin.initialize_app(cred)
                print("--- Firebase Admin SDK initialized successfully ---")
            else:
                # Handle error if the path is missing or file doesn't exist
                print("!!! ERROR: Firebase credentials path not found or invalid. Check settings.py !!!")
