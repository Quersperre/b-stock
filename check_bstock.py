"""Check Thomann product pages for a B-Stock offer and email when one appears.

Uses only the standard library. Configure via environment variables:
  SMTP_USER  Gmail address used to send (e.g. you@gmail.com)
  SMTP_PASS  Gmail app password (not your normal password)
  MAIL_TO    recipient address (defaults to SMTP_USER)
If SMTP_USER/SMTP_PASS are not set, the alert is printed instead of emailed.
"""

import html
import json
import os
import re
import smtplib
import sys
import urllib.request
from email.message import EmailMessage
from pathlib import Path

# Products to watch. Add more URLs as needed.
URLS = [
    "https://www.thomann.ro/taylor_414ce_studio_shaded_edgeburst.htm",
]

STATE_FILE = Path(__file__).with_name("state.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
}

# The B-Stock notice lives in <div class="seeother"> inside the price box and
# links to the B-Stock product page. Only this block counts: the "related
# products" carousel may mention B-Stock items that are no longer offered.
SEEOTHER_RE = re.compile(r'<div class="seeother">(.*?)</div>', re.S | re.I)
LINK_RE = re.compile(r'href="([^"]*b_stock[^"]*)"', re.I)


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def check(url):
    """Return (available, details) for one product page."""
    page = fetch(url)
    if "product-price-box" not in page:
        # Bot check / error page instead of the product: fail loudly.
        raise RuntimeError(f"Unexpected page content for {url} (blocked?)")

    for block in SEEOTHER_RE.findall(page):
        if "b-stock" not in block.lower():
            continue
        text = re.sub(r"<[^>]+>", " ", block)
        text = " ".join(html.unescape(text).replace("�", " ").split())
        link = LINK_RE.search(block)
        bstock_url = urllib.request.urljoin(url, link.group(1)) if link else url
        return True, {"text": text, "bstock_url": bstock_url}
    return False, {}


def send_email(subject, body):
    user, password = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS")
    if not (user and password):
        print(f"[no SMTP credentials, not emailing]\n{subject}\n{body}")
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = os.environ.get("MAIL_TO") or user
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    print(f"Email sent: {subject}")


def main():
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    errors = 0

    for url in URLS:
        try:
            available, details = check(url)
        except Exception as e:
            print(f"ERROR {url}: {e}", file=sys.stderr)
            errors += 1
            continue

        was_available = state.get(url, {}).get("available", False)
        print(f"{url}: B-Stock {'AVAILABLE' if available else 'not available'}"
              + (f" - {details['text']}" if available else ""))

        # Notify only on the transition not-available -> available.
        if available and not was_available:
            send_email(
                "B-Stock available: " + url.rsplit("/", 1)[-1].removesuffix(".htm"),
                f"{details['text']}\n\nB-Stock item: {details['bstock_url']}\n"
                f"Product page: {url}\n",
            )
        state[url] = {"available": available, **details}

    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
