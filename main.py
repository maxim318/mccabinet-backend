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


def normalize_measurements(analysis: dict):
    if not isinstance(analysis, dict):
        return {
            "page_used": "",
            "detected_dimensions": [],
            "detected_appliances": [],
            "detected_openings": [],
            "layout_type": "",
            "uncertain_items": ["AI returned invalid structure"],
            "questions_for_client": ["Please confirm kitchen dimensions manually."]
        }

    return {
        "page_used": analysis.get("page_used", ""),
        "detected_dimensions": analysis.get("detected_dimensions", []),
        "detected_appliances": analysis.get("detected_appliances", []),
        "detected_openings": analysis.get("detected_openings", []),
        "layout_type": analysis.get("layout_type", ""),
        "uncertain_items": analysis.get("uncertain_items", []),
        "questions_for_client": analysis.get("questions_for_client", []),
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
        print("STEP 1 — measurement extraction called")

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
        print("Calling OpenAI Vision for measurements...")

        prompt = """
You are reading architectural kitchen floor plan pages.

Your FIRST job is to extract visible measurements and plan details.
Do NOT guess cabinet layout yet.

Return ONLY valid JSON.
Do not use markdown.
Do not wrap in ```json.
Do not include explanation outside JSON.

Return this exact schema:

{
  "page_used": "",
  "detected_dimensions": [
    {
      "label": "",
      "value": "",
      "location": "",
      "confidence": "high | medium | low"
    }
  ],
  "detected_appliances": [
    {
      "type": "",
      "location": "",
      "confidence": "high | medium | low"
    }
  ],
  "detected_openings": [
    {
      "type": "door | window | opening",
      "location": "",
      "size": "",
      "confidence": "high | medium | low"
    }
  ],
  "layout_type": "",
  "uncertain_items": [
    ""
  ],
  "questions_for_client": [
    ""
  ]
}

Rules:
- Only list dimensions you can actually see or reasonably read from the plan.
- If a dimension is unclear, mark confidence as low.
- Do NOT invent 90, 96, 120, or other standard wall sizes unless visible.
- Do NOT create cabinet layout yet.
- If no usable kitchen dimensions are visible, say that in uncertain_items and questions_for_client.
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
            temperature=0.1,
        )

        ai_text = response.output[0].content[0].text

        print("AI RAW OUTPUT:")
        print(ai_text)

        measurement_raw = clean_ai_json(ai_text)
        measurement_analysis = normalize_measurements(measurement_raw)

        print("NORMALIZED MEASUREMENT ANALYSIS:")
        print(json.dumps(measurement_analysis, indent=2))

        return {
            "status": "success",
            "measurement_extraction": measurement_analysis,
            "analysis": measurement_analysis
        }

    except Exception as e:
        print("ERROR IN ANALYZE:", str(e))
        return {"status": "error", "message": str(e)}