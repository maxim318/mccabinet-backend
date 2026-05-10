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
You are a professional kitchen CAD layout engine.

Your job is NOT pricing and NOT explanation.

You must convert architectural floor plan text into a structured cabinet layout using STANDARD cabinet sizes.

========================
HARD RULES
========================

1. Output MUST represent a real kitchen layout that could be built.

2. You MUST detect:
   - walls and approximate wall lengths
   - doors (block cabinet placement)
   - windows (no cabinets in front unless noted)
   - appliances (sink, stove, fridge, dishwasher)
   - empty/usable wall space

3. You MUST use ONLY these cabinet widths (in inches):
   9, 12, 15, 18, 21, 24, 27, 30, 33, 36

4. You MUST "fit" cabinets into wall segments logically:
   - No overlapping appliances or doors
   - Fill remaining space with closest reasonable cabinet combination
   - If space doesn't perfectly fit, leave filler space

5. You MUST return a STRUCTURED layout, not just counts:
   - each wall should have its own cabinet run
   - include corner cabinets where walls meet
   - include gaps for appliances

6. You MUST be conservative and realistic:
   - Do NOT overfill walls
   - Do NOT assume missing walls
   - If unclear, mark assumptions clearly

========================
OUTPUT RULE
========================

Return ONLY valid JSON.

No explanations.
No markdown.
No extra text.

JSON must represent:
- wall-by-wall cabinet layout
- appliance placements
- assumptions
"""
    },
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
