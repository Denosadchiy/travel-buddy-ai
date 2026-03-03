"""
Contact form API endpoint.
"""
import httpx

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from src.auth.config import auth_settings

router = APIRouter(tags=["contact"])

CONTACT_RECIPIENT = "locally.office@gmail.com"


class ContactRequest(BaseModel):
    name: str
    email: EmailStr
    message: str


@router.post("/contact")
async def send_contact_message(req: ContactRequest):
    """Send a contact form message via Resend HTTP API."""
    if not req.name.strip() or not req.message.strip():
        raise HTTPException(status_code=400, detail="Name and message are required")

    if not auth_settings.resend_api_key:
        raise HTTPException(status_code=503, detail="Email service is not configured")

    html = f"""\
<div style="font-family: -apple-system, sans-serif; max-width: 560px; margin: 0 auto; padding: 24px;">
  <h2 style="color: #FF7043; margin-bottom: 16px;">New Contact Message</h2>
  <table style="width: 100%; border-collapse: collapse;">
    <tr><td style="padding: 8px 0; color: #888;">Name</td><td style="padding: 8px 0;">{req.name}</td></tr>
    <tr><td style="padding: 8px 0; color: #888;">Email</td><td style="padding: 8px 0;"><a href="mailto:{req.email}">{req.email}</a></td></tr>
  </table>
  <hr style="border: none; border-top: 1px solid #eee; margin: 16px 0;">
  <p style="white-space: pre-wrap;">{req.message}</p>
</div>"""

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {auth_settings.resend_api_key}"},
                json={
                    "from": auth_settings.email_from,
                    "to": [CONTACT_RECIPIENT],
                    "reply_to": req.email,
                    "subject": f"Contact Form: {req.name}",
                    "html": html,
                },
                timeout=10,
            )
            resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=503, detail="Failed to send email") from e

    return {"status": "sent"}
