"""Wizard action plan generation and follow-up tracking endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, APIKeyConfig
from app.models.wizard import WizardSubmission
from app.api.auth import get_current_user
from app.schemas.wizard import WizardIntakeRequest, ActionPlanResponse
from app.services.action_plan import generate_action_plan
from app.services.email_service import save_submission

router = APIRouter(prefix="/api/wizard", tags=["wizard"])


@router.post("/generate", response_model=ActionPlanResponse)
async def generate_wizard_action_plan(
    intake: WizardIntakeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a personalized action plan from intake form data.

    Requires an authenticated user with a configured BYOK API key.
    Calls the user's LLM provider to generate a structured action plan
    with legal citations, template emails, and escalation timeline.
    """
    # Get user's API key config
    result = await db.execute(
        select(APIKeyConfig).where(
            APIKeyConfig.user_id == current_user.id,
            APIKeyConfig.is_active == True,
        )
    )
    key_config = result.scalar_one_or_none()

    if not key_config:
        raise HTTPException(
            status_code=400,
            detail="No API key configured. Please add your LLM API key in Settings.",
        )

    intake_data = intake.model_dump()

    try:
        plan = await generate_action_plan(
            intake_data=intake_data,
            provider=key_config.provider,
            encrypted_key=key_config.encrypted_key,
            preferred_model=key_config.preferred_model,
        )
    except TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Action plan generation timed out. Please try again.",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to generate action plan: {str(e)}",
        )

    # Save submission for follow-up tracking if email provided
    if intake.email:
        first_step = plan.get("steps", [{}])[0].get("title", "Review your action plan")
        await save_submission(
            db=db,
            user_id=current_user.id,
            email=intake.email,
            sport=intake.sport,
            category=intake.category,
            summary=plan.get("summary", ""),
            first_step_title=first_step,
        )
        await db.commit()

    return plan


@router.get("/followup/{submission_id}")
async def track_followup(
    submission_id: int,
    action: str = Query(..., pattern="^(yes|no)$"),
    db: AsyncSession = Depends(get_db),
):
    """Track follow-up email click (yes/no on 'Did you take Step 1?')."""
    result = await db.execute(
        select(WizardSubmission).where(WizardSubmission.id == submission_id)
    )
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    submission.followup_clicked = action == "yes"
    await db.commit()

    return {"message": "Thank you for your feedback!", "action": action}
