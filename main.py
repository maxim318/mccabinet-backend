from pypdf import PdfReader
from fastapi import FastAPI, UploadFile, File, Body
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
    allow_origins=["*"],
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
@app.post("/analyze-plan")
from pydantic import BaseModel

class AnalyzeRequest(BaseModel):
    path: str

    try:
        # Download file from Supabase
        response = supabase.storage.from_("uploads").download(path)

        # Save temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(response)
            temp_file_path = temp_file.name

        # Convert PDF → images
        pages = convert_from_path(temp_file_path, dpi=200)

        image_paths = []
        text = ""

        for i, page in enumerate(pages):
            img_path = f"/tmp/page_{i}.png"
            page.save(img_path, "PNG")
            image_paths.append(img_path)

        # Call OpenAI
        ai_response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a kitchen CAD layout engine. Return ONLY valid JSON."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this kitchen floor plan."},
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
