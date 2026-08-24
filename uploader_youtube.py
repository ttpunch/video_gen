import os
import json
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

if os.path.exists("client_secret.json"):
    CLIENT_SECRETS_FILE = os.path.abspath("client_secret.json")
else:
    CLIENT_SECRETS_FILE = os.path.abspath("client_secrets.json")
TOKEN_FILE = os.path.abspath("token_youtube.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
# Read access for the analytics feedback loop:
#  - youtube.readonly         -> read public stats (views/likes) via Data API
#  - yt-analytics.readonly    -> read retention/watch-time via Analytics API
ANALYTICS_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
# Requested during the consent flow so a single (re-)auth grants upload + reads.
ALL_SCOPES = SCOPES + ANALYTICS_SCOPES

def get_youtube_credentials():
    """Load cached credentials or return None if re-authentication is required."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as e:
            print(f"Error loading youtube token file: {e}")
            
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Save refreshed credentials
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        except Exception as e:
            print(f"Error refreshing youtube credentials: {e}")
            creds = None
            
    return creds

def get_youtube_service():
    """Get authenticated YouTube v3 service instance or raise an error if client_secrets.json is missing."""
    creds = get_youtube_credentials()
    
    if not creds:
        if not os.path.exists(CLIENT_SECRETS_FILE):
            raise FileNotFoundError(
                f"Missing {CLIENT_SECRETS_FILE}. Please download your client secrets JSON file "
                "from Google Cloud Console, rename it to 'client_secrets.json', and place it in the root folder."
            )
        
        # Run local server to authenticate the user (grants upload + analytics)
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, ALL_SCOPES)
        creds = flow.run_local_server(port=0)

        # Save credentials to cache file
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)

def get_youtube_analytics_service():
    """Authenticated YouTube Analytics API v2 service for the retention feedback loop.

    Reuses the cached upload credentials. If they predate the analytics scope
    (older installs authenticated for upload only), raises a clear error asking
    the user to re-authenticate — it never launches a browser flow itself, so it
    is safe to call from inside the FastAPI request handler.
    """
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, ALL_SCOPES)
        except Exception as e:
            print(f"Error loading youtube token file for analytics: {e}")

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        except Exception as e:
            print(f"Error refreshing youtube credentials: {e}")
            creds = None

    if not creds:
        raise RuntimeError(
            "YouTube Analytics access not authorized. Re-authenticate YouTube to grant the "
            "analytics (yt-analytics.readonly) scope, then retry."
        )
    return build("youtubeAnalytics", "v2", credentials=creds)

def is_youtube_authenticated() -> bool:
    """Check if YouTube credentials are cached and valid (or refreshable)."""
    creds = get_youtube_credentials()
    return creds is not None

def trigger_youtube_auth_flow_url() -> str:
    """Trigger the InstalledAppFlow manually if running headlessly or wanting a direct auth url."""
    if not os.path.exists(CLIENT_SECRETS_FILE):
        raise FileNotFoundError(f"Missing {CLIENT_SECRETS_FILE}")
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, ALL_SCOPES)
    # Port 0 lets OAuth select an open port automatically
    # Standard InstalledAppFlow run_local_server will open browser
    creds = flow.run_local_server(port=0)
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    return "Authentication successful!"

def upload_video_to_youtube(video_path: str, title: str, description: str, tags: list, privacy_status: str = "private", progress_callback=None):
    """Uploads local video file to YouTube Shorts using official client libraries."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found at: {video_path}")
        
    service = get_youtube_service()
    
    body = {
        "snippet": {
            "title": title[:100],  # YouTube title limit is 100 characters
            "description": description,
            "tags": tags,
            "categoryId": "22"  # Category: People & Blogs (general category for shorts)
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False
        }
    }
    
    media = MediaFileUpload(
        video_path,
        mimetype="video/*",
        chunksize=1024 * 1024,  # 1MB chunks for progress reports
        resumable=True
    )
    
    request = service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )
    
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status and progress_callback:
            progress_percent = int(status.progress() * 100)
            progress_callback(progress_percent)
            
    video_id = response.get("id")
    return video_id
