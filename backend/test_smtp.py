import os
import socket
import smtplib
import ssl
from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).resolve().parent / ".env"
load_dotenv(env_file, override=True)

host = os.getenv("SMTP_HOST", "").strip()
port = int(os.getenv("SMTP_PORT", "587"))
username = os.getenv("SMTP_USERNAME", "").strip()
password = os.getenv("SMTP_PASSWORD", "").strip()

print("ENV FILE:", env_file)
print("SMTP HOST:", repr(host))
print("SMTP PORT:", port)

if not host or not username or not password:
    raise SystemExit("Missing SMTP settings in .env")

try:
    print("DNS:", socket.getaddrinfo(host, port))
    with smtplib.SMTP(host, port, timeout=20) as server:
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
        server.login(username, password)
        print("SUCCESS: Gmail SMTP authentication worked.")

except Exception as exc:
    print("ERROR TYPE:", type(exc).__name__)
    print("ERROR DETAILS:", str(exc))