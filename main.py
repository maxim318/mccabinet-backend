from pypdf import PdfReader
from fastapi import FastAPI, UploadFile, File, Body
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

app = FastAPI(title="McCabinet API")

# Allow frontend to talk to backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://localhost:5173",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# =========================
# OPENAI
# =========================
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================
# SUPABASE
# =========================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("⚠️ Missing Supabase environment variables")
    supabase = None
else:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
# =========================
# IMAGE ENCODER
# =========================
def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

# =========================
# UPLOAD ENDPOINT
# =========================
@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    contents = await file.read()
    if supabase is None:
        return {"status": "error", "message": "Supabase not configured"}

    unique_name = f"{uuid.uuid4()}_{file.filename}"
    file_path = f"uploads/{unique_name}"

    supabase.storage.from_("uploads").upload(
        file_path,
        contents,
        file_options={"content-type": file.content_type},
    )

    return {"status": "uploaded", "path": file_path}

# =========================
# ANALYZE PLAN (FULL AI PIPELINE)
# =========================
class AnalyzeRequest(BaseModel):
    path: str


@app.post("/analyze-plan")
async def analyze_plan(request: AnalyzeRequest):
    try:
        path = request.path

        response = supabase.storage.from_("uploads").download(path)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(response)
            temp_file_path = temp_file.name

        pages = convert_from_path(temp_file_path, dpi=200)

        image_paths = []

        for i, page in enumerate(pages):
            img_path = f"/tmp/page_{i}.png"
            page.save(img_path, "PNG")
            image_paths.append(img_path)

response = openai_client.responses.create(
    model="gpt-4o-mini",
    response_format={"type": "json_object"},
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Analyze this kitchen floorplan and return cabinet layout JSON."},
                {
                    "type": "input_image",
                    "image_base64": encode_image(image_paths[0])
                }
            ]
        }
    ],
    temperature=0.2
)

print("AI RAW OUTPUT:", response.output_text)

analysis = json.loads(response.output_text)
        return {
            "status": "success",
            "analysis": analysis
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
