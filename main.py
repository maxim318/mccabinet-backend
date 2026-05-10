import json
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
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

        # ===================================
        # SEND TEXT TO OPENAI
        # ===================================
        ai_response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
messages=[
{
    "role": "system",
    "content": """
You are a professional kitchen CAD layout designer.

You convert floor plan text into structured cabinet layout designs.

You must follow these rules:

1. You MUST identify:
   - walls (length estimates allowed if unclear)
   - appliances (sink, fridge, stove, dishwasher)
   - doors and windows (treat as blocked zones)

2. You MUST design using ONLY standard cabinet widths:
   - 9, 12, 15, 18, 21, 24, 27, 30, 33, 36 inches

3. You MUST build logical cabinet runs along each wall:
   - base cabinets go on floor
   - wall cabinets go above where possible
   - leave clearance for appliances and doors

4. You MUST detect:
   - corner cabinets where walls meet
   - appliance gaps
   - unknown measurements

5. You MUST output ONLY valid JSON.

NO explanations. NO markdown. NO text outside JSON.
"""
}
    {
        "role": "user",
        "content": f"""
Here is the extracted floor plan text:

{text}

Return ONLY the JSON object with cabinet estimation.
"""
    }
],
            temperature=0.2
        )

        analysis_text = ai_response.choices[0].message.content
        analysis = json.loads(analysis_text)

        return {
            "status": "success",
            "analysis": analysis
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
