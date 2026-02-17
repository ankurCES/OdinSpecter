import os
import json
import requests
import mimetypes
import base64
import subprocess

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
                {"text": "Transcribe this audio clip"},
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
        get_response(text_output)
    except (KeyError, IndexError):
        print("Error in response:", json.dumps(result, indent=2))

def get_response(text):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent"

    payload = json.dumps({
    "contents": [
        {
        "parts": [
            {
            "text": "{}".format(text)
            }
        ]
        }
    ]
    })
    headers = {
    'x-goog-api-key': API_KEY,
    'Content-Type': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    result = response.json()
    answer = result['candidates'][0]['content']['parts'][0]['text']
    print(answer)
    generate_gemini_speech(answer)

def generate_gemini_speech(text, output_filename="data/answer.wav", voice="Leda"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={API_KEY}"
    
    # 1. Prepare the Request Payload
    payload = {
        "contents": [{
            "parts": [{
                "text": text
            }]
        }],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voice
                    }
                }
            }
        }
    }

    headers = {"Content-Type": "application/json"}

    # 2. Call the API
    print(f"Requesting speech for: '{text}'...")
    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        print(response.text)
        return

    # 3. Extract Base64 and Decode to PCM
    response_data = response.json()
    try:
        audio_base64 = response_data['candidates'][0]['content']['parts'][0]['inlineData']['data']
        pcm_data = base64.b64decode(audio_base64)
        
        # Save temporary PCM file
        temp_pcm = "temp_output.pcm"
        with open(temp_pcm, "wb") as f:
            f.write(pcm_data)
            
        # 4. Convert PCM to WAV using FFmpeg via subprocess
        # This mimics your: ffmpeg -f s16le -ar 24000 -ac 1 -i out.pcm out.wav
        print("Converting PCM to WAV...")
        subprocess.run([
            'ffmpeg', '-y', 
            '-f', 's16le', 
            '-ar', '16000', 
            '-ac', '2', 
            '-i', temp_pcm, 
            output_filename
        ], check=True, capture_output=True)
        
        os.remove(temp_pcm)
        print(f"Success! Saved to {output_filename}")

    except (KeyError, IndexError) as e:
        print(f"Failed to parse response: {e}")
        print(json.dumps(response_data, indent=2))
