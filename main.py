from fastapi import FastAPI, UploadFile, File, HTTPException
import os

from supabase import create_client

app = FastAPI()

# ===============================
# ENV VARIABLES (Railway)
# ===============================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ===============================
# SUPABASE CLIENT
# ===============================
supabase = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print("Supabase init error:", e)


# ===============================
# HEALTH CHECK
# ===============================
@app.get("/")
def root():
    return {"status": "API running"}


# ===============================
# UPLOAD FLOOR PLAN (CORE FEATURE)
# ===============================
@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")

    contents = await file.read()
    filename = file.filename or "upload.pdf"

    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        supabase.storage.from_("plans").upload(
            filename,
            contents,
            file_options={"content-type": "application/pdf"}
        )
    except Exception as e:
        print("Storage error:", e)
        raise HTTPException(status_code=500, detail="Upload failed")

    return {
        "status": "success",
        "filename": filename
    }
