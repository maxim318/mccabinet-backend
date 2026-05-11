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

        image_path = "/tmp/page_0.png"
        pages[0].save(image_path, "PNG")

        print("PDF converted to image:", image_path)
        print("Calling OpenAI Vision...")

        prompt = """
You are a kitchen cabinet layout assistant.

Analyze this kitchen floorplan image and return ONLY valid JSON.

Do not use markdown.
Do not wrap the response in ```json.
Do not include explanations outside JSON.

Return this schema:
{
  "kitchen_type": "",
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
                            "image_url": f"data:image/png;base64,{encode_image(image_path)}",
                        },
                    ],
                }
            ],
            temperature=0.2,
        )

        ai_text = response.output[0].content[0].text

        print("AI RAW OUTPUT:")
        print(ai_text)

        clean_text = ai_text.strip()

        if clean_text.startswith("```"):
            clean_text = clean_text.split("```")[1]
            if clean_text.startswith("json"):
                clean_text = clean_text[4:]

        clean_text = clean_text.strip()

        print("CLEANED JSON:")
        print(clean_text)

        analysis = json.loads(clean_text)

        return {"status": "success", "analysis": analysis}

    except Exception as e:
        print("ERROR IN ANALYZE:", str(e))
        return {"status": "error", "message": str(e)}