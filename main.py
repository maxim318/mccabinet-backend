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
            "input_type": "unknown",
            "scale_detected": False,
            "scale_value": "",
            "can_generate_layout": False,
            "layout_generation_reason": "AI returned invalid structure",
            "detected_dimensions": [],
            "detected_appliances": [],
            "detected_openings": [],
            "layout_type": "",
            "uncertain_items": ["AI returned invalid structure"],
            "questions_for_client": ["Please confirm kitchen dimensions manually."]
        }

    detected_dimensions = analysis.get("detected_dimensions", [])
    can_generate_layout = analysis.get("can_generate_layout", False)

    if not can_generate_layout and isinstance(detected_dimensions, list) and len(detected_dimensions) > 0:
        can_generate_layout = True

    return {
        "page_used": analysis.get("page_used", ""),
        "input_type": analysis.get("input_type", "unknown"),
        "scale_detected": analysis.get("scale_detected", False),
        "scale_value": analysis.get("scale_value", ""),
        "can_generate_layout": can_generate_layout,
        "layout_generation_reason": analysis.get("layout_generation_reason", ""),
        "detected_dimensions": detected_dimensions,
        "detected_appliances": analysis.get("detected_appliances", []),
        "detected_openings": analysis.get("detected_openings", []),
        "layout_type": analysis.get("layout_type", ""),
        "uncertain_items": analysis.get("uncertain_items", []),
        "questions_for_client": analysis.get("questions_for_client", []),
        "raw_ai_output": analysis,
    }


def normalize_cabinet_layout(layout: dict):
    if not isinstance(layout, dict):
        return {
            "layout_status": "needs_review",
            "walls": [],
            "appliances": [],
            "questions_for_client": ["Cabinet layout could not be generated."]
        }

    walls = layout.get("walls", [])
    normalized_walls = []

    for index, wall in enumerate(walls):
        if not isinstance(wall, dict):
            continue

        cabinets = wall.get("cabinets", [])
        if not isinstance(cabinets, list):
            cabinets = []

        normalized_cabinets = []
        running_x = 0

        for cabinet in cabinets:
            if not isinstance(cabinet, dict):
                continue

            width = cabinet.get("width") or 30

            normalized_cabinets.append({
                "type": cabinet.get("type", "base"),
                "width": width,
                "depth": cabinet.get("depth") or 24,
                "x": cabinet.get("x", running_x),
                "y": cabinet.get("y", 0),
                "rotation": cabinet.get("rotation", 0),
                "position_note": cabinet.get("position_note", ""),
                "adjacent_to_appliance": cabinet.get("adjacent_to_appliance", False),
            })

            running_x += width

        normalized_walls.append({
            "id": wall.get("id") or f"Wall {chr(65 + index)}",
            "length_inches": wall.get("length_inches") or wall.get("length") or 0,
            "x1": wall.get("x1", 0),
            "y1": wall.get("y1", 0),
            "x2": wall.get("x2", wall.get("length_inches") or wall.get("length") or 0),
            "y2": wall.get("y2", 0),
            "description": wall.get("description", ""),
            "cabinets": normalized_cabinets,
            "notes": wall.get("notes", "")
        })

    return {
        "layout_status": layout.get("layout_status", "draft_needs_client_confirmation"),
        "kitchen_type": layout.get("kitchen_type", ""),
        "walls": normalized_walls,
        "appliances": layout.get("appliances", []),
        "fillers": layout.get("fillers", []),
        "assumptions": layout.get("assumptions", []),
        "questions_for_client": layout.get("questions_for_client", []),
        "raw_ai_output": layout,
    }


def generate_layout_from_data(data: dict):
    layout_prompt = f"""
You are a professional cabinet layout assistant.

Using ONLY the confirmed measurement data below, generate a cabinet layout with real top-down coordinates.

This software must support BOTH:
- scaled architectural plans
- unscaled PDFs
- hand-drawn dimensioned sketches
- screenshots/exports from other design software

Scale handling:
- If use_scale is true and scale_value is provided, use the scale as supporting information.
- If use_scale is false, ignore the detected scale and use only confirmed written dimensions.
- If no scale is available, use the visible or confirmed dimensions.
- Do not require scale.
- If dimensions are missing or unclear, create a draft but mark it as needing client confirmation.

Confirmed data:
{json.dumps(data, indent=2)}

Return ONLY valid JSON.
Do not use markdown.
Do not wrap in ```json.
Do not include explanation outside JSON.

Use only these cabinet widths:
9, 12, 15, 18, 21, 24, 27, 30, 33, 36.

Coordinate rules:
- Use inches as the coordinate unit.
- x and y are top-down plan coordinates.
- rotation is degrees: 0, 90, 180, or 270.
- Base cabinets usually have depth 24.
- Wall cabinets usually have depth 12.
- Tall cabinets usually have depth 24.
- Put cabinets along their related wall.
- If exact placement is uncertain, still provide x/y but explain the assumption.

Return this exact schema:

{{
  "layout_status": "draft_needs_client_confirmation",
  "kitchen_type": "",
  "walls": [
    {{
      "id": "Wall A",
      "length_inches": 0,
      "x1": 0,
      "y1": 0,
      "x2": 0,
      "y2": 0,
      "description": "",
      "cabinets": [
        {{
          "type": "base | wall | tall | sink_base | drawer_base | filler | corner",
          "width": 30,
          "depth": 24,
          "x": 0,
          "y": 0,
          "rotation": 0,
          "position_note": "",
          "adjacent_to_appliance": false
        }}
      ],
      "notes": ""
    }}
  ],
  "appliances": [
    {{
      "type": "",
      "estimated_width": 30,
      "depth": 24,
      "x": 0,
      "y": 0,
      "rotation": 0,
      "wall_id": "",
      "location_note": ""
    }}
  ],
  "fillers": [
    {{
      "wall_id": "",
      "width": 3,
      "x": 0,
      "y": 0,
      "rotation": 0,
      "reason": ""
    }}
  ],
  "assumptions": [
    ""
  ],
  "questions_for_client": [
    ""
  ]
}}

Rules:
- This is NOT pricing.
- This is a draft layout only.
- Cabinet widths must be standard 3-inch increments from 9 to 36 inches.
- Respect doors, windows, openings, appliances, and uncertain dimensions.
- If a wall length is not clearly extracted, set length_inches to 0 and ask the client to confirm.
- Do not claim final accuracy unless dimensions are high confidence.
"""

    layout_response = openai_client.responses.create(
        model="gpt-4o-mini",
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": layout_prompt}
                ],
            }
        ],
        temperature=0.1,
    )

    layout_text = layout_response.output[0].content[0].text

    print("LAYOUT AI RAW OUTPUT:")
    print(layout_text)

    layout_raw = clean_ai_json(layout_text)
    return normalize_cabinet_layout(layout_raw)


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


class GenerateLayoutRequest(BaseModel):
    confirmed_dimensions: list = []
    detected_appliances: list = []
    detected_openings: list = []
    layout_type: str = ""
    notes: str = ""
    use_scale: bool = True
    scale_value: str = ""
    input_type: str = ""


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

        measurement_prompt = """
You are reading kitchen plan pages.

Your FIRST job is to classify the uploaded plan and extract usable measurements.
Do NOT guess cabinet layout yet.

The uploaded file can be any of these:
- scaled architectural PDF
- unscaled architectural PDF
- hand-drawn dimensioned sketch
- screenshot/export from other design software
- unknown plan type

Scale is helpful but NOT mandatory.
If a scale is visible, extract it.
If no scale is visible, use written dimensions visible on the plan.
If neither scale nor dimensions are visible, ask the client to enter key wall dimensions.

Return ONLY valid JSON.
Do not use markdown.
Do not wrap in ```json.
Do not include explanation outside JSON.

Return this exact schema:

{
  "page_used": "",
  "input_type": "scaled_architectural_plan | unscaled_architectural_plan | hand_drawn_dimensioned_sketch | software_export | unknown",
  "scale_detected": false,
  "scale_value": "",
  "can_generate_layout": false,
  "layout_generation_reason": "",
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
- Detect whether there is a visible scale.
- If scale exists, set scale_detected true and fill scale_value.
- If scale does not exist, set scale_detected false.
- Do NOT require scale.
- Only list dimensions you can actually see or reasonably read from the plan.
- If a dimension is unclear, mark confidence as low.
- Do NOT invent 90, 96, 120, or other standard wall sizes unless visible.
- Do NOT create cabinet layout yet.
- Set can_generate_layout true if there are enough visible dimensions or client-confirmable measurements to create a draft.
- Set can_generate_layout false if there are no usable dimensions.
- If no usable kitchen dimensions are visible, explain that in uncertain_items and questions_for_client.
"""

        measurement_content = [{"type": "input_text", "text": measurement_prompt}]

        for img in image_paths:
            measurement_content.append({
                "type": "input_image",
                "image_url": f"data:image/png;base64,{encode_image(img)}",
            })

        measurement_response = openai_client.responses.create(
            model="gpt-4o-mini",
            input=[
                {
                    "role": "user",
                    "content": measurement_content,
                }
            ],
            temperature=0.1,
        )

        measurement_text = measurement_response.output[0].content[0].text

        print("MEASUREMENT AI RAW OUTPUT:")
        print(measurement_text)

        measurement_raw = clean_ai_json(measurement_text)
        measurement_analysis = normalize_measurements(measurement_raw)

        print("NORMALIZED MEASUREMENT ANALYSIS:")
        print(json.dumps(measurement_analysis, indent=2))

        print("STEP 2 — coordinate cabinet layout generation called")

        cabinet_layout = generate_layout_from_data(measurement_analysis)

        print("NORMALIZED CABINET LAYOUT:")
        print(json.dumps(cabinet_layout, indent=2))

        return {
            "status": "success",
            "measurement_extraction": measurement_analysis,
            "cabinet_layout": cabinet_layout,
            "analysis": cabinet_layout
        }

    except Exception as e:
        print("ERROR IN ANALYZE:", str(e))
        return {"status": "error", "message": str(e)}


@app.post("/generate-layout")
async def generate_layout(request: GenerateLayoutRequest):
    try:
        print("GENERATE COORDINATE LAYOUT FROM CONFIRMED DIMENSIONS CALLED")

        confirmed_data = {
            "confirmed_dimensions": request.confirmed_dimensions,
            "detected_appliances": request.detected_appliances,
            "detected_openings": request.detected_openings,
            "layout_type": request.layout_type,
            "notes": request.notes,
            "use_scale": request.use_scale,
            "scale_value": request.scale_value,
            "input_type": request.input_type,
        }

        cabinet_layout = generate_layout_from_data(confirmed_data)

        return {
            "status": "success",
            "cabinet_layout": cabinet_layout,
            "analysis": cabinet_layout
        }

    except Exception as e:
        print("ERROR IN GENERATE LAYOUT:", str(e))
        return {"status": "error", "message": str(e)}