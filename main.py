from pypdf import PdfReader
from fastapi import Body
import tempfile
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
import uuid

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    try:
        contents = await file.read()

        unique_name = f"{uuid.uuid4()}_{file.filename}"
        file_path = f"uploads/{unique_name}"

        response = supabase.storage.from_("uploads").upload(
            file_path,
            contents,
            file_options={"content-type": file.content_type}
        )

        return {
            "status": "uploaded",
            "filename": unique_name,
            "path": file_path,
            "supabase_response": str(response)
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)}

@app.post("/analyze-plan")
async def analyze_plan(path: str = Body(...)):
    try:
        # Download file from Supabase
        response = supabase.storage.from_("uploads").download(path)

        # Save temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(response)
            temp_file_path = temp_file.name

        # Read PDF text
        reader = PdfReader(temp_file_path)
        text = ""

        for page in reader.pages:
            text += page.extract_text() + "\n"

        return {
            "status": "success",
            "extracted_text": text[:2000]
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
