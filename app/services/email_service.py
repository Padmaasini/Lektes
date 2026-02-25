import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List
from app.core.config import settings

async def send_report_email(job, candidates: List) -> bool:
    """
    Send the screening report to HR via Gmail SMTP.
    Completely free — uses your Gmail account.
    """
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        print("  ⚠️  Gmail credentials not configured — skipping email")
        return False

    try:
        html_body = build_email_html(job, candidates)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🎯 TalentMesh Report: Top {len(candidates)} Candidates for {job.title}"
        msg["From"] = settings.GMAIL_USER
        msg["To"] = job.hr_email

        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
            server.sendmail(settings.GMAIL_USER, job.hr_email, msg.as_string())

        print(f"  📧 Report sent to {job.hr_email}")
        return True

    except Exception as e:
        print(f"  Email error: {e}")
        return False

def build_email_html(job, candidates: List) -> str:
    """Build a clean HTML email report."""
    rows = ""
    for c in candidates:
        score = round(c.match_score or 0, 1)
        color = "#22c55e" if score >= 70 else "#f59e0b" if score >= 50 else "#ef4444"
        red_flags_html = f"<p style='color:#ef4444;font-size:12px;'>⚠️ {c.red_flags}</p>" if c.red_flags else ""
        linkedin_html = f"<a href='{c.linkedin_url}' style='color:#0077b5;'>LinkedIn</a>" if c.linkedin_url else "—"
        github_html = f"<a href='{c.github_url}' style='color:#333;'>GitHub</a>" if c.github_url else "—"

        rows += f"""
        <tr style="border-bottom:1px solid #e5e7eb;">
            <td style="padding:12px;font-weight:bold;">#{c.rank}</td>
            <td style="padding:12px;">{c.full_name or "Unknown"}</td>
            <td style="padding:12px;">{c.email or "—"}</td>
            <td style="padding:12px;text-align:center;">
                <span style="background:{color};color:white;padding:4px 10px;border-radius:20px;font-weight:bold;">
                    {score}%
                </span>
            </td>
            <td style="padding:12px;font-size:13px;">
                {c.score_justification or "—"}
                {red_flags_html}
            </td>
            <td style="padding:12px;">{linkedin_html} &nbsp; {github_html}</td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:Arial,sans-serif;max-width:900px;margin:0 auto;padding:20px;color:#111;">
        <div style="background:linear-gradient(135deg,#667eea,#764ba2);padding:30px;border-radius:12px;margin-bottom:30px;">
            <h1 style="color:white;margin:0;font-size:26px;">🎯 TalentMesh Screening Report</h1>
            <p style="color:rgba(255,255,255,0.85);margin:8px 0 0 0;">
                Role: <strong>{job.title}</strong> &nbsp;|&nbsp; Top {len(candidates)} Candidates
            </p>
        </div>

        <table style="width:100%;border-collapse:collapse;background:white;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
            <thead>
                <tr style="background:#f9fafb;font-size:13px;text-transform:uppercase;color:#6b7280;">
                    <th style="padding:12px;text-align:left;">Rank</th>
                    <th style="padding:12px;text-align:left;">Name</th>
                    <th style="padding:12px;text-align:left;">Email</th>
                    <th style="padding:12px;text-align:center;">Match</th>
                    <th style="padding:12px;text-align:left;">Justification</th>
                    <th style="padding:12px;text-align:left;">Profiles</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>

        <div style="margin-top:30px;padding:20px;background:#f0fdf4;border-radius:8px;border-left:4px solid #22c55e;">
            <p style="margin:0;font-size:14px;color:#166534;">
                💡 <strong>Need screening questions?</strong> Reply to this email with the candidate name 
                and TalentMesh will generate 2-3 tailored technical questions with answer blueprints.
            </p>
        </div>

        <p style="color:#9ca3af;font-size:12px;margin-top:20px;text-align:center;">
            Powered by TalentMesh AI &nbsp;|&nbsp; talentmesh.ai
        </p>
    </body>
    </html>
    """
