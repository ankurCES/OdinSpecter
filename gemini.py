import os
import json
import requests
import mimetypes
import json

with open('config.json', 'r') as file:
    data = json.load(file)

# Configuration
API_KEY = data["GEMINI_API_KEY"]
AUDIO_PATH = data["FILE"]
DISPLAY_NAME = "AUDIO"

def upload_and_generate():
    # 1. Prepare Metadata
    mime_type, _ = mimetypes.guess_type(AUDIO_PATH)
    num_bytes = os.path.getsize(AUDIO_PATH)
    
    upload_url_endpoint = "https://generativelanguage.googleapis.com/upload/v1beta/files"
    
    headers_start = {
        "x-goog-api-key": API_KEY,
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(num_bytes),
        "X-Goog-Upload-Header-Content-Type": mime_type,
        "Content-Type": "application/json"
    }
    
    metadata = {"file": {"display_name": DISPLAY_NAME}}

    # 2. Initial Resumable Request
    print("Initiating upload...")
    response_start = requests.post(upload_url_endpoint, headers=headers_start, json=metadata)
    upload_url = response_start.headers.get("x-goog-upload-url")

    # 3. Upload Actual Bytes
    print("Uploading bytes...")
    headers_upload = {
        "Content-Length": str(num_bytes),
        "X-Goog-Upload-Offset": "0",
        "X-Goog-Upload-Command": "upload, finalize"
    }
    
    with open(AUDIO_PATH, "rb") as f:
        response_upload = requests.post(upload_url, headers=headers_upload, data=f)
    
    file_info = response_upload.json()
    file_uri = file_info["file"]["uri"]
    print(f"File URI: {file_uri}")

    # 4. Generate Content
    print("Generating description...")
    gen_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={API_KEY}"
    
    payload = {
        "contents": [{
            "parts": [
                {"text": "Describe this audio clip"},
                {"file_data": {"mime_type": mime_type, "file_uri": file_uri}}
            ]
        }]
    }
    
    response_gen = requests.post(gen_url, json=payload)
    
    # 5. Parse and Print Output
    result = response_gen.json()
    try:
        text_output = result['candidates'][0]['content']['parts'][0]['text']
        print("\nGemini Response:\n", text_output)
    except (KeyError, IndexError):
        print("Error in response:", json.dumps(result, indent=2))