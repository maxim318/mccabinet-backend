from pdf2image import convert_from_path
import base64

def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
import json
import os
import uuid
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pypdf import PdfReader
from supabase import create_client
from openai import OpenAI

app = FastAPI(title="McCabinet API")

# Allow frontend to talk to backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all for now (we'll lock later)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

       # Convert PDF pages to images
       pages = convert_from_path(temp_file_path, dpi=200)

       image_paths = []
       for i, page in enumerate(pages):
           img_path = f"/tmp/page_{i}.png"
           page.save(img_path, "PNG")
           image_paths.append(img_path)
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

========================
STRICT OUTPUT SCHEMA
========================

Your JSON MUST follow this structure exactly:

{
  "kitchen_type": "string (galley, L-shape, U-shape, etc)",
  "walls": [
    {
      "id": "Wall A",
      "length_inches": number,
      "description": "what this wall represents",
      "cabinets": [
        {
          "type": "base | wall | tall | filler | corner",
          "width": number,
          "position_note": "where it sits on wall",
          "adjacent_to_appliance": false
        }
      ]
    }
  ],
  "appliances": [
    {
      "type": "sink | stove | fridge | dishwasher | unknown",
      "estimated_width": number,
      "wall_id": "Wall A"
    }
  ],
  "corners": [
    {
      "between_walls": ["Wall A", "Wall B"],
      "cabinet_type": "corner"
    }
  ],
  "assumptions": [
    "any missing measurements you had to assume"
  ]
}

========================
RULES
========================

- MUST build wall-by-wall layout
- MUST place appliances FIRST, then fit cabinets around them
- MUST ONLY use cabinet widths:
  9, 12, 15, 18, 21, 24, 27, 30, 33, 36
- MUST NOT overlap cabinets or appliances
- MUST leave clearance where doors/windows exist
- MUST be realistic (like an actual installer would build)

NO text outside JSON.
NO explanations.
"""
    },
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "Analyze this kitchen floor plan and create cabinet layout."},
        {
          "type": "image_url",
          "image_url": {
            "url": f"data:image/png;base64,{encode_image(image_paths[0])}"
          }
        }
      ]
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
