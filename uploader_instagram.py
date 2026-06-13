import os
import time
import requests
from pyngrok import ngrok
from dotenv import load_dotenv

load_dotenv()

INSTAGRAM_BUSINESS_ACCOUNT_ID = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
NGROK_AUTHTOKEN = os.getenv("NGROK_AUTHTOKEN")

if NGROK_AUTHTOKEN:
    try:
        ngrok.set_auth_token(NGROK_AUTHTOKEN)
    except Exception as e:
        print(f"Error setting ngrok auth token: {e}")

def is_instagram_configured() -> bool:
    """Check if Instagram credentials are set up in the environment."""
    return bool(INSTAGRAM_BUSINESS_ACCOUNT_ID and INSTAGRAM_ACCESS_TOKEN)

def get_public_url(video_path: str, public_domain: str) -> str:
    """Resolve the local video path to a public ngrok URL."""
    # Find relative path from project root
    project_root = os.path.abspath(os.path.curdir)
    abs_video_path = os.path.abspath(video_path)
    
    if not abs_video_path.startswith(project_root):
        raise ValueError(f"Video file {video_path} is outside of the workspace directory.")
        
    rel_path = os.path.relpath(abs_video_path, project_root)
    # Convert backslashes for URLs on Windows
    url_path = rel_path.replace(os.path.sep, "/")
    return f"{public_domain}/{url_path}"

def upload_reel_to_instagram(video_path: str, caption: str, progress_callback=None):
    """Uploads local video to Instagram Reels via Graph API and dynamic ngrok tunnel."""
    if not is_instagram_configured():
        raise ValueError("Instagram is not configured. Please define INSTAGRAM_BUSINESS_ACCOUNT_ID and INSTAGRAM_ACCESS_TOKEN in your .env file.")
        
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found at: {video_path}")
        
    # 1. Start ngrok tunnel on port 8000
    if progress_callback:
        progress_callback("Starting secure ngrok tunnel to expose local video...")
        
    public_url = None
    try:
        # Connect to port 8000 (where our backend.py runs)
        tunnel = ngrok.connect(8000)
        public_url = tunnel.public_url
        print(f"ngrok tunnel established at: {public_url}")
    except Exception as e:
        raise RuntimeError(f"Failed to start ngrok tunnel: {e}. Check if NGROK_AUTHTOKEN is configured correctly.")
        
    try:
        video_public_url = get_public_url(video_path, public_url)
        print(f"Exposed video URL for Instagram download: {video_public_url}")
        
        # 2. Step A: Initialize container
        if progress_callback:
            progress_callback("Step 1/3: Creating Instagram media upload container...")
            
        url = f"https://graph.facebook.com/v19.0/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media"
        payload = {
            "media_type": "REELS",
            "video_url": video_public_url,
            "caption": caption,
            "access_token": INSTAGRAM_ACCESS_TOKEN
        }
        
        response = requests.post(url, data=payload, timeout=20)
        if response.status_code != 200:
            raise RuntimeError(f"Instagram container creation failed: {response.text}")
            
        container_id = response.json().get("id")
        print(f"Container created. ID: {container_id}")
        
        # 3. Step B: Poll status until finished
        if progress_callback:
            progress_callback("Step 2/3: Waiting for Instagram to retrieve and process video...")
            
        poll_url = f"https://graph.facebook.com/v19.0/{container_id}"
        poll_params = {
            "fields": "status_code,status",
            "access_token": INSTAGRAM_ACCESS_TOKEN
        }
        
        max_attempts = 30  # 30 * 5s = 150 seconds max wait
        success = False
        
        for attempt in range(max_attempts):
            time.sleep(5)
            poll_resp = requests.get(poll_url, params=poll_params, timeout=10)
            if poll_resp.status_code == 200:
                data = poll_resp.json()
                status_code = data.get("status_code")
                status_msg = data.get("status", "")
                
                print(f"Polling Instagram status: {status_code} ({status_msg})")
                if progress_callback:
                    progress_callback(f"Step 2/3: Instagram status is {status_code}...")
                    
                if status_code == "FINISHED":
                    success = True
                    break
                elif status_code == "ERROR":
                    raise RuntimeError(f"Instagram processing failed: {status_msg}")
            else:
                print(f"Polling error: {poll_resp.status_code} - {poll_resp.text}")
                
        if not success:
            raise TimeoutError("Timeout waiting for Instagram to process the video.")
            
        # 4. Step C: Publish the Reels container
        if progress_callback:
            progress_callback("Step 3/3: Publishing Reels post to your profile feed...")
            
        publish_url = f"https://graph.facebook.com/v19.0/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media_publish"
        publish_payload = {
            "creation_id": container_id,
            "access_token": INSTAGRAM_ACCESS_TOKEN
        }
        
        pub_resp = requests.post(publish_url, data=publish_payload, timeout=20)
        if pub_resp.status_code != 200:
            raise RuntimeError(f"Instagram publishing failed: {pub_resp.text}")
            
        media_id = pub_resp.json().get("id")
        print(f"Published successfully! Reel Media ID: {media_id}")
        
        if progress_callback:
            progress_callback(f"Successfully published to Instagram! Media ID: {media_id}")
            
        return media_id
        
    finally:
        # Always clean up the ngrok tunnel
        if public_url:
            print(f"Stopping ngrok tunnel: {public_url}")
            try:
                ngrok.disconnect(public_url)
            except Exception as e:
                print(f"Error disconnecting ngrok: {e}")
