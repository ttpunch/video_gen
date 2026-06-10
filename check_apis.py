import os
import requests
from dotenv import load_dotenv
load_dotenv()

def check_ollama():
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    print(f"Connecting to Ollama at {host}...")
    try:
        response = requests.get(f"{host}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            print("✅ Ollama is running!")
            print("Available models:")
            for m in models:
                print(f" - {m['name']}")
            return True
        else:
            print(f"❌ Ollama returned status code {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Failed to connect to Ollama: {e}")
        return False

def check_leonardo():
    api_key = os.getenv("LEONARDO_API_KEY")
    if not api_key:
        print("❌ LEONARDO_API_KEY not found in environment!")
        return False
    
    print("Connecting to Leonardo.ai API...")
    url = "https://cloud.leonardo.ai/api/rest/v1/me"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {api_key}"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            user_data = response.json().get("user_details", [{}])[0]
            username = user_data.get("user", {}).get("username", "Unknown")
            print(f"✅ Leonardo API is valid! Authenticated as user: {username}")
            return True
        else:
            print(f"❌ Leonardo API returned status code {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Failed to connect to Leonardo.ai: {e}")
        return False

if __name__ == "__main__":
    print("--- Diagnostic Check ---")
    ollama_ok = check_ollama()
    print()
    leonardo_ok = check_leonardo()
    print("------------------------")
    if ollama_ok and leonardo_ok:
        print("🎉 All API checks passed! Ready for implementation.")
    else:
        print("⚠️ Some checks failed. Please resolve them before proceeding.")
