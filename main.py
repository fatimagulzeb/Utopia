import os
import json
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from mistralai.client import Mistral
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize FastAPI
app = FastAPI()

# Mount static files (CSS/JS)
# app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize templates (for HTML rendering)
templates = Jinja2Templates(directory="templates")

# Initialize Mistral client
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
client = Mistral(api_key=MISTRAL_API_KEY)

# Email configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

def extract_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```json") and raw.endswith("```"):
        raw = raw[7:-3].strip()
    elif raw.startswith("```") and raw.endswith("```"):
        raw = raw[3:-3].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            raise ValueError(f"No valid JSON found in the response. Raw: {raw}")

def generate_content(transcript: str, your_name: str, your_role: str) -> dict:
    system_prompt = """
You are the AI content and relationship assistant for a creative studio.

Studio process facts:
- Every studio meeting is recorded in Granola; transcripts are tagged with attendees and timestamps.
- The studio uses the LAUNCH framework:
  Lead, Amplify, Unify, Nurture, Convert, Harvest.
- Every published asset should align naturally with one LAUNCH stage.
- Studio voice is declarative, specific, confident, and opinion-led.
- Avoid hedging language such as "might", "could", "perhaps", or vague summaries.
- The studio publishes strong perspectives and clear takeaways.

From every meeting transcript, generate:
1. One LinkedIn post in the studio voice
2. One personalized follow-up email
3. One press-angle sentence

Requirements:
- LinkedIn post:
  - 150–250 words
  - conversational but authoritative
  - first person
  - opinion-driven
  - end with a sharp insight, takeaway, or question
  - include 3–5 hashtags
  - naturally reflect one LAUNCH framework stage

- Follow-up email:
  - under 180 words
  - warm and human
  - reference a specific detail from the conversation
  - include clear next steps or action items

- Press-angle sentence:
  - one concise sentence
  - media-ready
  - highlight the most newsworthy insight from the discussion

Strictly return ONLY valid JSON.
No markdown.
No explanations.
No code fences.

Required JSON format:
{
  "linkedin": "...",
  "email": "...",
  "press_angle": "..."
}
"""
    user_prompt = f"""My name: {your_name}
My role: {your_role}

Raw meeting transcript:
{transcript}"""

    response = client.chat.complete(
        model="mistral-large-latest",
        messages=[
            {"role": "system", "content": system_prompt},  
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7,
        max_tokens=1024,
    )
    raw = response.choices[0].message.content
    return extract_json(raw)

def send_email(recipient_email: str, subject: str, body: str) -> bool:
    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = recipient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return False

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(
    request=request,
    name="index.html",
    context={"request": request}
)

@app.post("/generate_and_send")
async def generate_and_send(
    request: Request,
    transcript: UploadFile = File(...),
    attendee_email: str = Form(...),
    your_name: str = Form(...),
    your_role: str = Form(...),
):
    # Read transcript
    transcript_content = await transcript.read()
    transcript_text = transcript_content.decode("utf-8")

    # Generate content
    try:
        result = generate_content(transcript_text, your_name, your_role)

        linkedin_post = result["linkedin"]
        email_body = result["email"]
        press_angle = result["press_angle"]


        output_data = {
            "linkedin": result["linkedin"],
            "email": result["email"],
            "press_angle": result["press_angle"],
            "attendee_email": attendee_email,
            "your_name": your_name,
            "your_role": your_role,
        }

        os.makedirs("outputs", exist_ok=True)

        file_path = "outputs/result.json"

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4, ensure_ascii=False)

        # Send email
        email_sent = send_email(
            recipient_email=attendee_email,
            subject="Follow-Up from Our Meeting",
            body=email_body,
        )

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "linkedin_post": linkedin_post,
                "email_sent": email_sent,
                "attendee_email": attendee_email,
                "press_angle": press_angle
            },
        )
    
    except Exception as e:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"error": f"Error generating content: {e}"},
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)




