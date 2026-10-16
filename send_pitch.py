import sqlite3, re, smtplib, os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
load_dotenv()

c = sqlite3.connect('data/leadhunter.db')
row = c.execute("SELECT email_subject, email_message, name FROM leads WHERE id=2").fetchone()
subject, body, name = row

# Strip the demo link line
body = re.sub(r'[^\n]*Check out[^\n]*localhost[^\n]*\n?', '', body)
body = re.sub(r'[^\n]*localhost[^\n]*\n?', '', body)
body = re.sub(r'\n\s*\n\s*\n+', '\n\n', body).strip()
body = body + "\n\nBest regards"

print("=== FINAL SUBJECT ===")
print(subject)
print()
print("=== FINAL BODY ===")
print(body)
print()

# Now send
SENDER = os.environ['SENDER_EMAIL']
APP_PW = os.environ['GMAIL_APP_PASSWORD']
TO = "hello@pjhdrywall.com"  # placeholder recipient

msg = MIMEMultipart()
msg['From'] = SENDER
msg['To'] = TO
msg['Subject'] = subject
msg.attach(MIMEText(body, 'plain'))
s = smtplib.SMTP('smtp.gmail.com', 587)
s.starttls()
s.login(SENDER, APP_PW)
s.send_message(msg)
s.quit()
print(f"SENT to {TO}")
