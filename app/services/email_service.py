"""
TalentMesh Email Service — Resend API
Sends screening report as PDF attachment.
Email body contains interview questions + likely answers per candidate.
"""
import base64
from typing import List, Optional
import resend
from app.core.config import settings


def _init_resend():
    if settings.RESEND_API_KEY:
        resend.api_key = settings.RESEND_API_KEY
        return True
    return False


async def send_report_email(
    job,
    candidates: List,
    pdf_bytes: bytes,
    questions_by_candidate: Optional[dict] = None
) -> bool:
    """
    Send screening report email via Resend.
    - PDF report attached
    - Email body contains interview questions + likely answers per candidate
    """
    if not _init_resend():
        print("  ⚠️  RESEND_API_KEY not configured — skipping email")
        return False

    try:
        from_email = settings.RESEND_FROM_EMAIL or "TalentMesh <noreply@talentmesh.nimbus-24.com>"
        subject    = f"TalentMesh Report: {job.title} — {len(candidates)} Candidates Ranked"

        html_body  = build_email_html(job, candidates, questions_by_candidate)

        # Encode PDF as base64 for attachment
        pdf_b64    = base64.b64encode(pdf_bytes).decode("utf-8")
        filename   = f"TalentMesh_{job.title.replace(' ', '_')}_Report.pdf"

        params = {
            "from":    from_email,
            "to":      [job.hr_email],
            "subject": subject,
            "html":    html_body,
            "attachments": [
                {
                    "filename":    filename,
                    "content":     pdf_b64,
                    "content_type": "application/pdf"
                }
            ]
        }

        resend.Emails.send(params)
        print(f"  📧 Report + questions emailed to {job.hr_email}")
        return True

    except Exception as e:
        print(f"  Email error: {e}")
        return False


def build_email_html(job, candidates: List, questions_by_candidate: Optional[dict] = None) -> str:
    """
    Build the email HTML body.
    - Clean intro, no report table (that's in the PDF attachment)
    - Interview questions + likely answers for each top candidate
    """

    # ── Candidate summary rows (compact, no full report) ──
    summary_rows = ""
    for c in candidates[:5]:  # top 5 only in email
        score = round(c.match_score or 0, 1)
        color = "#2d7a4f" if score >= 70 else "#d97706" if score >= 45 else "#c0392b"
        bg    = "#edf7f1" if score >= 70 else "#fffbeb" if score >= 45 else "#fdf0ee"
        summary_rows += f"""
        <tr>
          <td style="padding:10px 14px;font-weight:700;color:#1a2e1a;">#{c.rank}</td>
          <td style="padding:10px 14px;color:#1a2e1a;">{c.full_name or "Unknown"}</td>
          <td style="padding:10px 14px;color:#555;font-size:13px;">{c.email or "—"}</td>
          <td style="padding:10px 14px;text-align:center;">
            <span style="background:{bg};color:{color};padding:4px 12px;border-radius:20px;font-weight:700;font-size:13px;border:1px solid {color}30;">
              {score}%
            </span>
          </td>
        </tr>"""

    # ── Interview questions per candidate ──
    questions_html = ""
    if questions_by_candidate is not None and len(questions_by_candidate) > 0:
        # Use the first (highest-ranked) candidate's questions as the single question set.
        # Questions are role-level and consistent across candidates.
        first_data = next(iter(questions_by_candidate.values()))
        qs = first_data.get("questions", [])

        if qs:
            quality_colors = {
                "Strong":     ("#2d7a4f", "#edf7f1"),
                "Acceptable": ("#d97706", "#fffbeb"),
                "Weak":       ("#c0392b", "#fdf0ee"),
            }

            questions_items = ""
            for q in qs:
                num      = q.get("number", "")
                category = q.get("category", "")
                question = q.get("question", "")
                why      = q.get("why_we_ask", "")
                followup = q.get("follow_up", "")
                answers  = q.get("likely_answers", [])

                answers_html = ""
                for a in answers:
                    quality = a.get("quality", "")
                    answer  = a.get("answer", "")
                    signal  = a.get("what_it_signals", "")
                    fc, bg  = quality_colors.get(quality, ("#555", "#f5f5f5"))
                    answers_html += f"""
                <div style="background:{bg};border-left:3px solid {fc};border-radius:6px;padding:10px 14px;margin-bottom:8px;">
                  <span style="font-size:11px;font-weight:700;color:{fc};text-transform:uppercase;letter-spacing:0.5px;">
                    {quality} Answer
                  </span>
                  <p style="margin:6px 0 4px;color:#1a1a1a;font-size:13px;font-style:italic;">"{answer}"</p>
                  <p style="margin:0;color:#666;font-size:12px;">→ {signal}</p>
                </div>"""

                questions_items += f"""
            <div style="margin-bottom:28px;padding-bottom:24px;border-bottom:1px solid #e8e0d4;">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                <span style="background:#1a2e1a;color:white;width:24px;height:24px;border-radius:50%;
                             display:inline-flex;align-items:center;justify-content:center;
                             font-size:12px;font-weight:700;flex-shrink:0;">{num}</span>
                <span style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">{category}</span>
              </div>
              <p style="font-size:15px;font-weight:600;color:#1a2e1a;margin:0 0 8px 32px;">{question}</p>
              <p style="font-size:12px;color:#5a7a5a;background:#f0f4f0;border-radius:6px;
                        padding:8px 12px;margin:0 0 10px 32px;">
                💡 <strong>Why we ask:</strong> {why}
              </p>
              <div style="margin-left:32px;">{answers_html}</div>
              <p style="font-size:12px;color:#888;margin:8px 0 0 32px;">
                🔁 <strong>Follow-up if vague:</strong> {followup}
              </p>
              <div style="margin:10px 0 0 32px;background:white;border:1px dashed #ccc;
                          border-radius:6px;padding:10px 12px;">
                <p style="margin:0;font-size:12px;color:#aaa;font-style:italic;">
                  📝 HR notes: record candidate's actual answer here
                </p>
              </div>
            </div>"""

            questions_html = f"""
        <div style="margin-top:40px;">
          <h2 style="color:#1a2e1a;font-size:18px;border-bottom:2px solid #2d7a4f;padding-bottom:8px;">
            📋 Interview Questions &amp; Likely Answers
          </h2>
          <p style="color:#555;font-size:14px;margin-bottom:24px;">
            Use these questions for your initial screening calls. For each question you'll find
            three likely answer types — Strong, Acceptable, and Weak — to help you judge responses
            even if you're not technical.
          </p>
          <div style="background:#f9fbf9;border:1px solid #ddd5c4;border-radius:10px;padding:24px 28px;">
            {questions_items}
          </div>
        </div>"""


    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:860px;margin:0 auto;padding:20px;color:#1a1a1a;background:#fff;">

  <!-- Header -->
  <div style="background:#1a2e1a;padding:28px 32px;border-radius:12px;margin-bottom:28px;">
    <div style="font-size:22px;font-weight:700;color:#68d391;margin-bottom:4px;">TalentMesh</div>
    <div style="font-size:18px;font-weight:600;color:white;">Screening Report: {job.title}</div>
    <div style="font-size:13px;color:#a0c0a0;margin-top:4px;">
      {len(candidates)} candidates ranked · Report attached as PDF
    </div>
  </div>

  <!-- Intro -->
  <p style="font-size:14px;color:#333;line-height:1.7;margin-bottom:20px;">
    Hi,<br><br>
    Your TalentMesh screening is complete. The full ranked report is <strong>attached as a PDF</strong>
    to this email — open it to see all candidate scores, justifications, and profile links.<br><br>
    Below is a quick summary of the top candidates, followed by tailored interview questions
    with likely answer examples to help you conduct an effective initial screening call.
  </p>

  <!-- Summary table -->
  <h2 style="font-size:16px;color:#1a2e1a;border-bottom:2px solid #2d7a4f;padding-bottom:8px;margin-bottom:0;">
    Top Candidates Summary
  </h2>
  <table style="width:100%;border-collapse:collapse;margin-bottom:8px;background:#faf7f2;border-radius:8px;overflow:hidden;">
    <thead>
      <tr style="background:#edf7f1;font-size:12px;color:#4a6355;text-transform:uppercase;letter-spacing:0.5px;">
        <th style="padding:10px 14px;text-align:left;">Rank</th>
        <th style="padding:10px 14px;text-align:left;">Name</th>
        <th style="padding:10px 14px;text-align:left;">Email</th>
        <th style="padding:10px 14px;text-align:center;">Match</th>
      </tr>
    </thead>
    <tbody>{summary_rows}</tbody>
  </table>
  <p style="font-size:12px;color:#888;margin-bottom:32px;">Full report with justifications, skills and profile links is in the attached PDF.</p>

  {questions_html}

  <!-- Footer -->
  <div style="margin-top:40px;padding:16px 20px;background:#f0f4f0;border-radius:8px;
              font-size:12px;color:#888;text-align:center;">
    Powered by TalentMesh AI &nbsp;·&nbsp;
    CV data is permanently deleted when you mark the position as filled.<br>
    If not marked, data auto-deletes after 30 days.
  </div>

</body>
</html>"""
