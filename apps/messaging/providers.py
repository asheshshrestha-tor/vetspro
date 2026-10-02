"""Where messages go. Each channel is set up with environment variables.

SMS (SMS_PROVIDER):
    console  - default. Nothing is sent; the message is only logged.
    sparrow  - Sparrow SMS (Nepal). Needs SPARROW_SMS_TOKEN and SPARROW_SMS_FROM.
    aakash   - Aakash SMS (Nepal). Needs AAKASH_SMS_TOKEN.

WhatsApp (WHATSAPP_MODE):
    link     - default. Opens WhatsApp (web or phone) with the message typed in; staff press send.
    cloud    - WhatsApp Business Cloud API. Needs WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID.
               Meta only delivers free-form text inside a 24-hour window after the owner last wrote;
               outside it, approved templates are required.

Email uses Django's email settings (EMAIL_HOST, EMAIL_HOST_USER, ...).
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.mail import send_mail

TIMEOUT = 15


class Result:
    def __init__(self, status, reference="", error="", url=""):
        self.status = status
        self.reference = reference
        self.error = error
        self.url = url  # for WhatsApp links


def international(phone, country="977"):
    """Digits with the country code, e.g. 9779801234567."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    if phone.strip().startswith("+") or digits.startswith(country) and len(digits) > 10:
        return digits
    return country + digits.lstrip("0")


def local_number(phone):
    digits = international(phone)
    return digits[3:] if digits.startswith("977") else digits


def _post(url, data=None, json_body=None, headers=None):
    body = json.dumps(json_body).encode() if json_body is not None else urllib.parse.urlencode(data or {}).encode()
    request = urllib.request.Request(url, data=body, headers=headers or {}, method="POST")
    if json_body is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.status, response.read().decode("utf-8", "replace")


def sms_provider():
    return os.environ.get("SMS_PROVIDER", "console").lower()


def whatsapp_mode():
    return os.environ.get("WHATSAPP_MODE", "link").lower()


def send_sms(to, body):
    from .models import OutboundMessage as M

    provider = sms_provider()
    try:
        if provider == "sparrow":
            status, text = _post("https://api.sparrowsms.com/v2/sms/", {
                "token": os.environ.get("SPARROW_SMS_TOKEN", ""),
                "from": os.environ.get("SPARROW_SMS_FROM", ""),
                "to": local_number(to),
                "text": body,
            })
            return Result(M.SENT, reference=text[:100]) if status == 200 else Result(M.FAILED, error=text[:255])
        if provider == "aakash":
            status, text = _post("https://sms.aakashsms.com/sms/v3/send", {
                "auth_token": os.environ.get("AAKASH_SMS_TOKEN", ""),
                "to": local_number(to),
                "text": body,
            })
            return Result(M.SENT, reference=text[:100]) if status == 200 else Result(M.FAILED, error=text[:255])
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        return Result(M.FAILED, error=str(error)[:255])
    return Result(M.LOGGED)


def whatsapp_link(to, body):
    return f"https://wa.me/{international(to)}?text={urllib.parse.quote(body)}"


def send_whatsapp(to, body):
    from .models import OutboundMessage as M

    if whatsapp_mode() != "cloud":
        return Result(M.OPENED, url=whatsapp_link(to, body))
    token = os.environ.get("WHATSAPP_TOKEN", "")
    phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    try:
        status, text = _post(
            f"https://graph.facebook.com/v20.0/{phone_id}/messages",
            json_body={"messaging_product": "whatsapp", "to": international(to), "type": "text", "text": {"body": body}},
            headers={"Authorization": f"Bearer {token}"},
        )
    except urllib.error.HTTPError as error:
        return Result(M.FAILED, error=error.read().decode("utf-8", "replace")[:255])
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        return Result(M.FAILED, error=str(error)[:255])
    return Result(M.SENT, reference=text[:100]) if status == 200 else Result(M.FAILED, error=text[:255])


def send_email(to, subject, body):
    from .models import OutboundMessage as M

    try:
        send_mail(subject or "Message from the hospital", body, settings.DEFAULT_FROM_EMAIL, [to])
    except Exception as error:  # noqa: BLE001 - any mail failure is reported to staff, not raised
        return Result(M.FAILED, error=str(error)[:255])
    return Result(M.SENT)


def channel_status():
    """How each channel is set up, for the send page."""
    return {
        "sms": sms_provider(),
        "whatsapp": whatsapp_mode(),
        "email": settings.EMAIL_BACKEND.rsplit(".", 2)[-2],
    }
