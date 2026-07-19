import os
import time
import uuid
import requests
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import JSONResponse, HTMLResponse

# Disable docs to keep user-side completely hidden
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# Your Backend Configurations
FIREBASE_DB_URL = "https://nxm-winss-default-rtdb.firebaseio.com"
REAL_API_URL = "https://tfqdeadlo-1-78bapi.hf.space/search"

# Admin Security (Set these in your Render Environment Variables)
ADMIN_PASSKEY = os.getenv("ADMIN_PASSKEY", "your_secret_admin_passkey_here")
ALLOWED_IP = os.getenv("ALLOWED_IP", "ALL") # Change "ALL" to your specific IP to enable IP checking

# --- Hidden User Side ---
@app.get("/")
def read_root():
    return JSONResponse(status_code=403, content={"detail": "403 Forbidden"})

# --- Secure Admin Panel ---
def verify_admin(request: Request, passkey: str):
    # Render puts the real client IP in the x-forwarded-for header
    client_ip = request.headers.get("x-forwarded-for", request.client.host).split(",")[0].strip()
    
    if passkey != ADMIN_PASSKEY:
        raise HTTPException(status_code=403, detail="403 Forbidden")
    
    if ALLOWED_IP != "ALL" and client_ip != ALLOWED_IP:
        raise HTTPException(status_code=403, detail="403 Forbidden - IP Restricted")

@app.get("/admin", response_class=HTMLResponse)
def admin_panel(request: Request, passkey: str = ""):
    verify_admin(request, passkey)
    
    html_content = f"""
    <html>
        <head>
            <title>Admin Dashboard</title>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 40px; background: #111; color: #fff; }}
                .box {{ background: #222; padding: 20px; border-radius: 8px; max-width: 400px; margin: auto; }}
                input, button {{ width: 100%; padding: 10px; margin: 10px 0; border-radius: 4px; border: none; }}
                button {{ background: #4CAF50; color: white; cursor: pointer; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="box">
                <h2>Generate New API Key</h2>
                <form action="/admin/generate" method="POST">
                    <input type="hidden" name="passkey" value="{passkey}">
                    <label>Daily Limit (Requests per day):</label>
                    <input type="number" name="daily_limit" value="100" required>
                    <label>Valid for (Days):</label>
                    <input type="number" name="valid_days" value="30" required>
                    <button type="submit">Generate API Key</button>
                </form>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/admin/generate")
async def generate_key(request: Request, passkey: str = Form(...), daily_limit: int = Form(...), valid_days: int = Form(...)):
    verify_admin(request, passkey)
    
    new_key = f"nxm_{uuid.uuid4().hex[:16]}"
    current_time = int(time.time())
    expires_at = current_time + (valid_days * 86400)
    
    # Save Key Details to Firebase
    data = {
        "daily_limit": daily_limit,
        "usage_today": 0,
        "last_reset": current_time,
        "expires_at": expires_at,
        "active": True
    }
    
    firebase_url = f"{FIREBASE_DB_URL}/api_keys/{new_key}.json"
    requests.put(firebase_url, json=data)
    
    return {
        "status": "Success",
        "message": "Key Generated and Saved to Firebase",
        "api_key": new_key,
        "expires_in_days": valid_days,
        "daily_limit": daily_limit
    }

# --- The Protected API Endpoint ---
@app.get("/api/search")
def api_search(api_key: str, mobile: str):
    # 1. Fetch Key Data from Firebase
    firebase_url = f"{FIREBASE_DB_URL}/api_keys/{api_key}.json"
    res = requests.get(firebase_url)
    key_data = res.json()
    
    if not key_data or not key_data.get("active"):
        raise HTTPException(status_code=403, detail="Invalid or Inactive API Key")
        
    current_time = int(time.time())
    
    # 2. Check Expiration (Auto-Stop)
    if current_time > key_data["expires_at"]:
        requests.patch(firebase_url, json={"active": False})
        raise HTTPException(status_code=403, detail="API Key Expired")
        
    # 3. Check Daily Limit
    if current_time - key_data["last_reset"] > 86400:
        key_data["usage_today"] = 0
        key_data["last_reset"] = current_time
        
    if key_data["usage_today"] >= key_data["daily_limit"]:
        raise HTTPException(status_code=429, detail="Daily rate limit exceeded")
        
    # 4. Fetch from Real API
    try:
        real_api_response = requests.get(f"{REAL_API_URL}?mobile={mobile}")
        real_api_response.raise_for_status()
        data = real_api_response.json()
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=502, detail="Upstream API Error")
        
    # 5. Increment Usage in Firebase
    key_data["usage_today"] += 1
    requests.patch(firebase_url, json={
        "usage_today": key_data["usage_today"],
        "last_reset": key_data["last_reset"]
    })
    
    return data
    
