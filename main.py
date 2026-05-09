import os
import uuid
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from pypdf import PdfReader
from supabase import create_client
from openai import OpenAI

app = FastAPI(title="McCabinet API")

# ===================================
# OPENAI CLIENT (NEW)
# ===================================
openai_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# ===================================
# SAFE SUPABASE CONNECTION (LAZY LOAD)
# ===================================
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
async def analyze_plan(request: AnalyzeRequest):
    path = request.path
from pydantic import BaseModel

class AnalyzeRequest(BaseModel):
    path: str
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
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

        # ===================================
        # SEND TEXT TO OPENAI (THE MAGIC STEP)
        # ===================================
        ai_response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a kitchen and cabinetry expert. Analyze floor plans and describe cabinetry needs clearly."
                },
                {
                    "role": "user",
                    "content": f"""
Here is the extracted floor plan text:

{text}

Please describe:
- Kitchen layout type
- Cabinet locations
- Appliance placement
- Any design suggestions
"""
                }
            ],
            temperature=0.2
        )

        analysis = ai_response.choices[0].message.content

        return {
            "status": "success",
            "analysis": analysis
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
