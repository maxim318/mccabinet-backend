from pypdf import PdfReader
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

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenAI
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("⚠️ Missing Supabase environment variables")
    supabase = None
else:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Image encoder
def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

# Upload endpoint
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

# Request model
class AnalyzeRequest(BaseModel):
    path: str

# Analyze endpoint
@app.post("/analyze-plan")
async def analyze_plan(request: AnalyzeRequest):
    try:
        print("STEP 1 — analyze-plan called")

        if supabase is None:
            return {"status": "error", "message": "Supabase not configured"}

        # Download PDF
        path = request.path
        print("Downloading file from Supabase:", path)
        pdf_bytes = supabase.storage.from_("uploads").download(path)

        # Save temp PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(pdf_bytes)
            temp_file_path = temp_file.name

        print("PDF saved to temp:", temp_file_path)

        # Convert PDF → images
        pages = convert_from_path(temp_file_path, dpi=200)
        image_paths = []

        for i, page in enumerate(pages):
            img_path = f"/tmp/page_{i}.png"
            page.save(img_path, "PNG")
            image_paths.append(img_path)

        print("PDF converted to images:", image_paths)

        # 🧠 NEW OPENAI CALL (SDK v2 compatible)
        print("Calling OpenAI Vision…")

        prompt = """
You are a kitchen cabinet estimator.

Analyze this kitchen floorplan image and return ONLY valid JSON.

Return this schema:
{
  "walls": [],
  "cabinets": [],
  "appliances": [],
  "notes": ""
}
"""

        response = openai_client.responses.create(
            model="gpt-4o-mini",
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
    "type": "input_image",
    "image_url": f"data:image/png;base64,{encode_image(image_paths[0])}"
}
                    ]
                }
            ],
            temperature=0.2,
        )

        # 🔥 THIS is the correct way to read output in SDK v2
        ai_text = response.output[0].content[0].text

        print("AI RAW OUTPUT:")
        print(ai_text)

        analysis = json.loads(ai_text)

        return {"status": "success", "analysis": analysis}

    except Exception as e:
        print("❌ ERROR IN ANALYZE:", str(e))
        return {"status": "error", "message": str(e)}