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
async def analyze_plan(path: str = Body(...)):
    try:
        # 1️⃣ Download PDF from Supabase
        pdf_bytes = supabase.storage.from_("uploads").download(path)

        # 2️⃣ Save temp PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
            temp_pdf.write(pdf_bytes)
            temp_pdf_path = temp_pdf.name

        # 3️⃣ Convert PDF → images
        try:
            pages = convert_from_path(temp_pdf_path, dpi=150, timeout=10)
except Exception as e:
    return {"status": "error", "message": f"PDF conversion failed: {str(e)}"}

if not pages:
    return {"status": "error", "message": "No pages found in PDF"}

image_path = "/tmp/page.png"
pages[0].save(image_path, "PNG")

print("IMAGE CREATED:", image_path)

        base64_image = encode_image(image_path)

        # 4️⃣ Send to OpenAI Vision
        ai_response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": """
You are a professional kitchen CAD layout engine.

Return ONLY valid JSON using cabinet widths:
9,12,15,18,21,24,27,30,33,36

Build REALISTIC wall-by-wall kitchen cabinet layouts.
"""
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this floor plan and create cabinet layout."},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{base64_image}"}
                        }
                    ],
                },
            ],
        )

        analysis = json.loads(ai_response.choices[0].message.content)

        return {"status": "success", "analysis": analysis}

    except Exception as e:
        return {"status": "error", "message": str(e)}
