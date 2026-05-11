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
from pydantic import BaseModel

class AnalyzeRequest(BaseModel):
    path: str


@app.post("/analyze-plan")
async def analyze_plan(request: AnalyzeRequest):
    try:
        path = request.path

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

        ai_response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a kitchen layout AI. Return ONLY JSON."
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
            temperature=0.2
        )

        analysis_text = ai_response.choices[0].message.content
        print("RAW OPENAI OUTPUT:", analysis_text)
       try:
           analysis = json.loads(analysis_text)
except Exception:
           return {
               "status": "error",
               "message": "OpenAI did not return valid JSON",
               "raw_output": analysis_text
    }

        return {
            "status": "success",
            "analysis": analysis
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
