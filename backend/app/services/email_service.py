"""Email service for sending follow-up emails.

Uses Resend for transactional email delivery.
Configure RESEND_API_KEY in environment variables.
If not configured, emails are logged but not sent (development mode).
"""

import os
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wizard import WizardSubmission

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@clubresolve.ca")

FOLLOWUP_TEMPLATE = """Hi there,

7 days ago, ClubResolve generated an action plan for your sports club dispute. Your first recommended step was:

"{first_step_title}"

Did you take that step?

→ Yes, I took action: {yes_url}
→ Not yet: {no_url}

Your feedback helps us improve ClubResolve for other parents facing similar situations.

Remember: this is advocacy support, not legal advice. If your situation has escalated, consider consulting a qualified lawyer.

Best,
ClubResolve
"""


async def save_submission(
    db: AsyncSession,
    user_id: int,
    email: str,
    sport: str,
    category: str,
    summary: str,
    first_step_title: str,
) -> WizardSubmission:
    """Save a wizard submission for follow-up tracking."""
    submission = WizardSubmission(
        user_id=user_id,
        email=email,
        sport=sport,
        category=category,
        summary=summary,
        first_step_title=first_step_title,
    )
    db.add(submission)
    await db.flush()
    return submission


async def send_followup_email(submission: WizardSubmission, base_url: str = "") -> bool:
    """Send a 7-day follow-up email for a wizard submission.

    Returns True if sent successfully, False otherwise.
    """
    if not RESEND_API_KEY:
        logger.info(
            "RESEND_API_KEY not configured. Follow-up email logged but not sent. "
            f"Submission ID: {submission.id}, Email: {submission.email}"
        )
        return False

    try:
        import resend

        resend.api_key = RESEND_API_KEY

        yes_url = f"{base_url}/api/wizard/followup/{submission.id}?action=yes"
        no_url = f"{base_url}/api/wizard/followup/{submission.id}?action=no"

        body = FOLLOWUP_TEMPLATE.format(
            first_step_title=submission.first_step_title,
            yes_url=yes_url,
            no_url=no_url,
        )

        resend.Emails.send(
            {
                "from": FROM_EMAIL,
                "to": submission.email,
                "subject": "Did you take the first step? — ClubResolve",
                "text": body,
            }
        )
        logger.info(f"Follow-up email sent to {submission.email} for submission {submission.id}")
        return True
    except Exception as e:
        logger.error(f"Failed to send follow-up email: {e}")
        return False


async def get_pending_followups(db: AsyncSession) -> list[WizardSubmission]:
    """Get submissions that need follow-up emails (7+ days old, not yet sent)."""
    cutoff = datetime.utcnow() - timedelta(days=7)
    result = await db.execute(
        select(WizardSubmission).where(
            WizardSubmission.created_at <= cutoff,
            WizardSubmission.followup_sent == False,
        )
    )
    return list(result.scalars().all())
