import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
from fastapi import FastAPI, UploadFile, File
from supabase import create_client
import stripe
import uuid
import resend

app = FastAPI()

# 🔐 ENV VARIABLES (we add these in Railway later)
SUPABASE_URL = "SUPABASE_URL"
SUPABASE_KEY = "SUPABASE_KEY"
STRIPE_KEY = "STRIPE_SECRET_KEY"
RESEND_KEY = "RESEND_API_KEY"

supabase = None

try:
    from supabase import create_client
    if SUPABASE_URL and SUPABASE_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print("Supabase not connected yet:", e)
stripe.api_key = STRIPE_KEY
resend.api_key = RESEND_KEY


# ===============================
# USER SIGNUP
# ===============================
@app.post("/signup")
def signup(email: str, password: str):
    user = supabase.auth.sign_up({"email": email, "password": password})
    return {"message": "user created"}


# ===============================
# UPLOAD FLOOR PLAN
# ===============================
@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    try:
        contents = await file.read()

        filename = file.filename or "upload.pdf"

        # Try Supabase upload (but never crash if it fails)
        try:
            if supabase:
                supabase.storage.from_("plans").upload(
                    filename,
                    contents,
                    file_options={"content-type": "application/pdf"}
                )
        except Exception as storage_error:
            print("Storage warning:", storage_error)

        return {
            "status": "success",
            "filename": filename,
            "message": "File received successfully",
            "cabinets": [
                {"type": "Base Cabinet", "width": 36},
                {"type": "Sink Cabinet", "width": 30},
                {"type": "Wall Cabinet", "width": 36}
            ],
            "cutlist": [
                "2x 36in base cabinets",
                "1x 30in sink cabinet",
                "2x 36in wall cabinets"
            ]
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


# ===============================
# STRIPE SUBSCRIPTION
# ===============================
@app.post("/create-checkout-session")
def create_checkout(email: str):
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{
            "price": "YOUR_STRIPE_PRICE_ID",
            "quantity": 1
        }],
        success_url="https://mccabinet.digilols.com/success",
        cancel_url="https://mccabinet.digilols.com/cancel",
        customer_email=email
    )
    return {"url": session.url}


# ===============================
# SEND EMAIL
# ===============================
@app.post("/send-email")
def send_email(to: str):
    resend.Emails.send({
        "from": "McCabinet <onboarding@digilols.com>",
        "to": to,
        "subject": "Welcome to McCabinet AI",
        "html": "<h1>Your account is ready</h1>"
    })
    return {"sent": True}


# ===============================
# SIMPLE METRICS
# ===============================
@app.get("/metrics")
def metrics():
    users = supabase.table("users").select("*").execute()
    return {"total_users": len(users.data)}
