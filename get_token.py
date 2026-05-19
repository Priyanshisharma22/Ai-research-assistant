# get_token.py – run once to generate a fresh refresh token
# Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in your .env before running
import os
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id":     os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
            "token_uri":     "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    },
    scopes=SCOPES,
)
creds = flow.run_local_server(port=8080, access_type="offline", prompt="consent")
print("\n✅ Copy these into your .env:\n")
print(f"GOOGLE_ACCESS_TOKEN={creds.token}")
print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
