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
from supabase import create_client
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

print("SUPABASE_URL:", SUPABASE_URL)
print("SUPABASE_KEY exists:", bool(SUPABASE_KEY))

try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("Supabase client created successfully")
except Exception as e:
    print("Supabase FAILED to initialize:")
    print(e)
    supabase = None

# ===================================
# FILE UPLOAD (PDF FLOOR PLAN)
# ===================================
@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        filename = file.filename

        file_path = f"uploads/{filename}"

        # Convert to proper bytes upload format
        response = supabase.storage.from_("uploads").upload(
            file_path,
            contents,
            file_options={
                "content-type": file.content_type or "application/pdf",
                "upsert": "true"
            }
        )

        return {
            "status": "uploaded",
            "filename": filename,
            "path": file_path,
            "supabase_response": str(response)
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
