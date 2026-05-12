from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client
from openai import OpenAI
from pdf2image import convert_from_path
import os
import json
import uuid
import tempfile
import base64
import openai

print("OPENAI VERSION:", openai.__version__)

app = FastAPI(title="McCabinet API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Missing Supabase environment variables")
    supabase = None
else:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def clean_ai_json(ai_text: str):
    clean_text = ai_text.strip()

    if clean_text.startswith("```"):
        parts = clean_text.split("```")
        if len(parts) >= 2:
            clean_text = parts[1].strip()
            if clean_text.startswith("json"):
                clean_text = clean_text[4:].strip()

    return json.loads(clean_text)


def normalize_analysis(analysis: dict):
    if not isinstance(analysis, dict):
        return {
            "kitchen_type": "unknown",
            "walls": [],
            "appliances": [],
            "notes": "AI returned invalid structure"
        }

    walls = analysis.get("walls", [])
    appliances = analysis.get("appliances", [])
    cabinets = analysis.get("cabinets", [])

    normalized_walls = []

    for index, wall in enumerate(walls):
        if not isinstance(wall, dict):
            continue

        wall_id = wall.get("id") or wall.get("name") or f"Wall {chr(65 + index)}"
        length_inches = (
            wall.get("length_inches")
            or wall.get("length")
            or wall.get("width")
            or 120
        )

        wall_cabinets = wall.get("cabinets")

        if not isinstance(wall_cabinets, list):
            wall_cabinets = []

        normalized_walls.append({
            "id": wall_id,
            "length_inches": length_inches,
            "description": wall.get("description", ""),
            "features": wall.get("features", []),
            "cabinets": wall_cabinets,
        })

    if not normalized_walls:
        normalized_walls = [
            {
                "id": "Wall A",
                "length_inches": 120,
                "description": "Fallback wall because AI did not detect walls",
                "features": [],
                "cabinets": [],
            }
        ]

    if cabinets and not any(wall.get("cabinets") for wall in normalized_walls):
        normalized_walls[0]["cabinets"] = [
            {
                "type": cabinet.get("type", "base") if isinstance(cabinet, dict) else "base",
                "width": (
                    cabinet.get("width")
                    or cabinet.get("dimensions", {}).get("width")
                    or 30
                ) if isinstance(cabinet, dict) else 30,
                "position_note": cabinet.get("location", "auto placed") if isinstance(cabinet, dict) else "auto placed",
                "adjacent_to_appliance": False,
            }
            for cabinet in cabinets
            if isinstance(cabinet, dict)
        ]

    for wall in normalized_walls:
        if not wall["cabinets"]:
            wall["cabinets"] = [
                {
                    "type": "base",
                    "width": 30,
                    "position_note": "placeholder cabinet - client should confirm layout",
                    "adjacent_to_appliance": False,
                }
            ]

    normalized_appliances = []

    for appliance in appliances:
        if isinstance(appliance, dict):
            normalized_appliances.append({
                "type": appliance.get("type", "unknown"),
                "estimated_width": appliance.get("estimated_width") or appliance.get("width") or 30,
                "wall_id": appliance.get("wall_id") or appliance.get("location") or "Wall A",
            })

    return {
        "kitchen_type": analysis.get("kitchen_type", "unknown"),
        "walls": normalized_walls,
        "appliances": normalized_appliances,
        "notes": analysis.get("notes", ""),
        "raw_ai_output": analysis,
    }


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    try:
        if supabase is None:
            return {"status": "error", "message": "Supabase not configured"}

        contents = await file.read()
        unique_name = f"{uuid.uuid4()}_{file.filename}"
        file_path = f"uploads/{unique_name}"

        supabase.storage.from_("uploads").upload(
            file_path,
            contents,
            file_options={"content-type": file.content_type},
        )

        return {"status": "uploaded", "path": file_path}

    except Exception as e:
        return {"status": "error", "message": str(e)}


class AnalyzeRequest(BaseModel):
    path: str


@app.post("/analyze-plan")
async def analyze_plan(request: AnalyzeRequest):
    try:
        print("STEP 1 — analyze-plan called")

        if supabase is None:
            return {"status": "error", "message": "Supabase not configured"}

        path = request.path
        print("Downloading file from Supabase:", path)

        pdf_bytes = supabase.storage.from_("uploads").download(path)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(pdf_bytes)
            temp_file_path = temp_file.name

        print("PDF saved to temp:", temp_file_path)

        pages = convert_from_path(temp_file_path, dpi=200)

        if not pages:
            return {"status": "error", "message": "No PDF pages found"}

        image_paths = []

        for i, page in enumerate(pages[:4]):
            image_path = f"/tmp/page_{i}.png"
            page.save(image_path, "PNG")
            image_paths.append(image_path)

        print("PDF pages sent to AI:", image_paths)
        print("Calling OpenAI Vision...")

        prompt = """
You are a kitchen cabinet layout assistant.

Analyze these PDF pages and identify the page that most likely contains the kitchen/floor plan.
Then return ONLY valid JSON.

Do not use markdown.
Do not wrap the response in ```json.
Do not include explanations outside JSON.

IMPORTANT:
Each wall MUST include a cabinets array.
The frontend requires walls[].cabinets.

Return this exact schema:
{
  "kitchen_type": "",
  "analyzed_page_note": "",
  "walls": [
    {
      "id": "Wall A",
      "length_inches": 120,
      "description": "",
      "features": [],
      "cabinets": [
        {
          "type": "base",
          "width": 30,
          "position_note": "",
          "adjacent_to_appliance": false
        }
      ]
    }
  ],
  "appliances": [
    {
      "type": "sink",
      "estimated_width": 30,
      "wall_id": "Wall A"
    }
  ],
  "notes": ""
}

Use only these cabinet widths:
9, 12, 15, 18, 21, 24, 27, 30, 33, 36.

If dimensions are unclear, make a conservative assumption and explain it in notes.
"""

        content = [{"type": "input_text", "text": prompt}]

        for img in image_paths:
            content.append({
                "type": "input_image",
                "image_url": f"data:image/png;base64,{encode_image(img)}",
            })

        response = openai_client.responses.create(
            model="gpt-4o-mini",
            input=[
                {
                    "role": "user",
                    "content": content,
                }
            ],
            temperature=0.2,
        )

        ai_text = response.output[0].content[0].text

        print("AI RAW OUTPUT:")
        print(ai_text)

        analysis_raw = clean_ai_json(ai_text)
        analysis = normalize_analysis(analysis_raw)

        print("NORMALIZED ANALYSIS:")
        print(json.dumps(analysis, indent=2))

        return {"status": "success", "analysis": analysis}

    except Exception as e:
        print("ERROR IN ANALYZE:", str(e))
        return {"status": "error", "message": str(e)}
