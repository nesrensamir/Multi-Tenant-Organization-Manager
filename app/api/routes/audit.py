import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import google.generativeai as genai

from app.api.dependencies import get_db, get_org_admin
from app.models.user import User
from app.models.tenant import AuditLog
from app.schemas.tenant import AuditLogResponse
from app.schemas.tenant import AskRequest
from app.core.config import settings

# Configure the LLM
if settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)

router = APIRouter(prefix="/organizations/{id}/audit-logs", tags=["Audit Logs"])

@router.get("", response_model=list[AuditLogResponse])
async def get_audit_logs(
    id: uuid.UUID,
    current_admin: User = Depends(get_org_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin only. Return organization audit entries.
    """
    # Fetch logs ordered by most recent
    query = select(AuditLog).where(AuditLog.organization_id == id).order_by(AuditLog.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/ask")
async def ask_chatbot(
    id: uuid.UUID,
    request: AskRequest,
    current_admin: User = Depends(get_org_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin only. Answers questions about today's activity using an LLM.
    """
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="LLM API key not configured.")

    # 1. Retrieve all logs (filtering by today as requested)
    today = datetime.now(timezone.utc).date()
    query = select(AuditLog).where(AuditLog.organization_id == id)
    result = await db.execute(query)
    logs = result.scalars().all()

    # Filter logs for today to optimize context window
    todays_logs = [log for log in logs if log.created_at.date() == today]
    
    if not todays_logs:
        return {"answer": "No activity recorded for this organization today."}

    # 2. Format logs for the LLM
    log_text = "\n".join([
        f"[{log.created_at.strftime('%H:%M:%S')}] Action: {log.action} | Details: {log.description}" 
        for log in todays_logs
    ])

    prompt = f"""
    You are an intelligent system administrator assistant. 
    Here are the audit logs for the organization today:
    
    {log_text}
    
    Based ONLY on the logs provided above, answer the following question from the Admin:
    "{request.question}"
    """

    model = genai.GenerativeModel('gemini-2.5-flash')

    # 3. Handle Streaming vs Non-Streaming
    if request.stream:
        # Use FastAPI's StreamingResponse to yield chunks of text as they arrive
        async def event_stream():
            try:
                response = await model.generate_content_async(prompt, stream=True)
                async for chunk in response:
                    if chunk.text:
                        # Yield in Server-Sent Events (SSE) format
                        yield chunk.text
            except Exception as e:
                yield f"Error generating response: {str(e)}"

        return StreamingResponse(event_stream(), media_type="text/plain")
    
    else:
        # Standard synchronous return
        response = await model.generate_content_async(prompt)
        return {"answer": response.text}