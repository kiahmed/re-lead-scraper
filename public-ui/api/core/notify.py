"""Notification channels behind one send() call.

Three channels, each independently switchable by config, because the honest
answer to "make it free" differs per channel:

  email    ACS ($0.25/1,000 — effectively free at our volume, zero DNS setup
           with an Azure-managed domain) or Brevo (9,000/month, genuinely $0)
  webpush  free and unlimited, but browser-opt-in: it reaches a browser the
           user granted permission on, NOT a phone number
  sms      real texts, genuinely costs money ($2/mo toll-free lease +
           ~$0.01/segment) and needs a cleared toll-free verification before
           a single message will deliver. Off by default.

A channel that is switched off is not merely hidden in the UI — send()
refuses it, and GET /api/meta never advertises it, so a saved alert cannot
point at a dead channel.

Config:
  NOTIFY_EMAIL_PROVIDER   acs | brevo | smtp | off      (default: acs)
  NOTIFY_WEBPUSH_ENABLED  true | false                  (default: true)
  NOTIFY_SMS_ENABLED      true | false                  (default: false)
  NOTIFY_SMS_PROVIDER     acs                           (default: acs)
"""
import json
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

from . import config
from .http import ApiError

CHANNELS = ("email", "webpush", "sms")


class NotifyError(Exception):
    """A channel failed to deliver. Callers record it and move on — one dead
    channel must never abort a notifier run."""


# ── availability ─────────────────────────────────────────────────────────────
def email_provider() -> str:
    return config.get("NOTIFY_EMAIL_PROVIDER", "acs").strip().lower()


def sms_provider() -> str:
    return config.get("NOTIFY_SMS_PROVIDER", "acs").strip().lower()


def email_enabled() -> bool:
    provider = email_provider()
    if provider == "off":
        return False
    if provider == "acs":
        return bool(config.get("ACS_CONNECTION_STRING") and config.get("ACS_SENDER_ADDRESS"))
    if provider == "brevo":
        return bool(config.get("BREVO_API_KEY") and config.get("NOTIFY_FROM_EMAIL"))
    if provider == "smtp":
        return bool(config.get("SMTP_HOST") and config.get("NOTIFY_FROM_EMAIL"))
    return False


def webpush_enabled() -> bool:
    return config.flag("NOTIFY_WEBPUSH_ENABLED", True) and bool(
        config.get("VAPID_PUBLIC_KEY") and config.get("VAPID_PRIVATE_KEY")
    )


def sms_enabled() -> bool:
    if not config.flag("NOTIFY_SMS_ENABLED", False):
        return False
    return bool(config.get("ACS_CONNECTION_STRING") and config.get("ACS_SMS_FROM_NUMBER"))


def available_channels() -> list[dict]:
    """What the SPA may offer. `note` is shown under the checkbox so a user
    understands what they're picking — especially that push is not SMS."""
    return [
        {
            "id": "email",
            "label": "Email",
            "enabled": email_enabled(),
            "note": "Always arrives. Verify your address first.",
        },
        {
            "id": "webpush",
            "label": "Instant push",
            "enabled": webpush_enabled(),
            "note": "Free and worldwide, but it goes to this browser — "
                    "not to a phone number. Allow notifications to switch it on.",
        },
        {
            "id": "sms",
            "label": "Text message",
            "enabled": sms_enabled(),
            "note": "A real SMS to your phone. US, Canada and Puerto Rico only.",
        },
    ]


# ── email ────────────────────────────────────────────────────────────────────
def _send_email_acs(to_address: str, subject: str, text: str, html: str = "") -> None:
    try:
        from azure.communication.email import EmailClient
    except ImportError:  # pragma: no cover - deployment-time dependency
        raise NotifyError("azure-communication-email is not installed") from None

    client = EmailClient.from_connection_string(config.get("ACS_CONNECTION_STRING"))
    content = {"subject": subject, "plainText": text}
    if html:
        content["html"] = html
    message = {
        "senderAddress": config.get("ACS_SENDER_ADDRESS"),
        "content": content,
        "recipients": {"to": [{"address": to_address}]},
    }
    try:
        poller = client.begin_send(message)
        result = poller.result()
    except Exception as e:
        raise NotifyError(f"ACS email failed: {e}") from None
    status = (result or {}).get("status", "")
    if status and status.lower() != "succeeded":
        raise NotifyError(f"ACS email finished as {status}")


def _send_email_brevo(to_address: str, subject: str, text: str, html: str = "") -> None:
    payload = {
        "sender": {
            "email": config.get("NOTIFY_FROM_EMAIL"),
            "name": config.get("NOTIFY_FROM_NAME", "FlyNest Leads"),
        },
        "to": [{"email": to_address}],
        "subject": subject,
        "textContent": text,
    }
    if html:
        payload["htmlContent"] = html
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode(),
        headers={
            "api-key": config.get("BREVO_API_KEY"),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status not in (200, 201, 202):
                raise NotifyError(f"Brevo returned HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        raise NotifyError(f"Brevo rejected the send: {e.read().decode()[:200]}") from None
    except NotifyError:
        raise
    except Exception as e:
        raise NotifyError(f"Brevo unreachable: {e}") from None


def _send_email_smtp(to_address: str, subject: str, text: str, html: str = "") -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.get("NOTIFY_FROM_EMAIL")
    msg["To"] = to_address
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    host, port = config.get("SMTP_HOST"), int(config.get("SMTP_PORT", "587"))
    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()
            user, password = config.get("SMTP_USER"), config.get("SMTP_PASSWORD")
            if user:
                server.login(user, password)
            server.send_message(msg)
    except Exception as e:
        raise NotifyError(f"SMTP send failed: {e}") from None


def send_email(to_address: str, subject: str, text: str, html: str = "") -> None:
    if not email_enabled():
        raise NotifyError("email channel is not configured")
    if not to_address:
        raise NotifyError("no email address on file")
    {
        "acs": _send_email_acs,
        "brevo": _send_email_brevo,
        "smtp": _send_email_smtp,
    }[email_provider()](to_address, subject, text, html)


# ── web push ─────────────────────────────────────────────────────────────────
def send_webpush(subscription: dict, title: str, body: str, url: str = "") -> None:
    """`subscription` is the browser's PushSubscription JSON, stored verbatim
    when the user granted permission."""
    if not webpush_enabled():
        raise NotifyError("web push is not configured")
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:  # pragma: no cover - deployment-time dependency
        raise NotifyError("pywebpush is not installed") from None

    payload = json.dumps({"title": title, "body": body, "url": url})
    try:
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=config.get("VAPID_PRIVATE_KEY"),
            vapid_claims={"sub": f"mailto:{config.get('VAPID_CONTACT_EMAIL', 'admin@example.com')}"},
        )
    except WebPushException as e:
        # 404/410 mean the browser dropped the subscription — the caller
        # prunes it rather than retrying forever
        status = getattr(getattr(e, "response", None), "status_code", 0)
        raise NotifyError(f"push failed ({status or 'error'}): {e}") from None
    except Exception as e:
        raise NotifyError(f"push failed: {e}") from None


def push_is_gone(error: NotifyError) -> bool:
    return "(404)" in str(error) or "(410)" in str(error)


# ── sms ──────────────────────────────────────────────────────────────────────
def send_sms(to_number: str, text: str) -> None:
    if not sms_enabled():
        raise NotifyError("SMS is switched off")
    if not to_number:
        raise NotifyError("no phone number on file")
    try:
        from azure.communication.sms import SmsClient
    except ImportError:  # pragma: no cover - deployment-time dependency
        raise NotifyError("azure-communication-sms is not installed") from None

    client = SmsClient.from_connection_string(config.get("ACS_CONNECTION_STRING"))
    try:
        results = client.send(
            from_=config.get("ACS_SMS_FROM_NUMBER"),
            to=[to_number],
            message=text[:1600],  # ~10 segments; alerts should never approach this
        )
    except Exception as e:
        raise NotifyError(f"ACS SMS failed: {e}") from None
    for result in results or []:
        if not getattr(result, "successful", False):
            raise NotifyError(getattr(result, "error_message", "SMS was not accepted"))


def assert_channel_available(channel: str) -> None:
    if channel not in CHANNELS:
        raise ApiError(400, f"channel must be one of {list(CHANNELS)}")
    enabled = {"email": email_enabled, "webpush": webpush_enabled, "sms": sms_enabled}[channel]()
    if not enabled:
        raise ApiError(400, f"the {channel} channel is not available right now")
