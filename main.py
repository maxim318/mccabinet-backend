from fastapi import FastAPI, UploadFile, File, HTTPException
import os

app = FastAPI(title="McCabinet API")

# ===================================
# HEALTH CHECK (ROOT ROUTE)
# ===================================
@app.get("/")
def root():
    return {"status": "McCabinet API is running"}

# ===================================
# TEST ROUTE
# ===================================
@app.get("/ping")
def ping():
    return {"message": "pong"}

# ===================================
# SAFE SUPABASE CONNECTION (LAZY LOAD)
# ===================================
supabase = None

def get_supabase():
    global supabase

    if supabase is not None:
        return supabase

    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Supabase env vars missing")
        return None

    try:
        from supabase import create_client
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Supabase connected")
        return supabase
    except Exception as e:
        print("Supabase connection failed:", e)
        return None

# ===================================
# FILE UPLOAD (PDF FLOOR PLAN)
# ===================================
@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")

    contents = await file.read()
    filename = file.filename or "upload.pdf"

    supabase_client = get_supabase()

    if supabase_client is None:
        return {
            "status": "received",
            "filename": filename,
            "warning": "Supabase not connected yet"
        }

    try:
        supabase_client.storage.from_("plans").upload(
            filename,
            contents,
            file_options={"content-type": "application/pdf"}
        )

        return {
            "status": "success",
            "filename": filename,
            "message": "File uploaded to storage"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
