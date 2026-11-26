from fastapi import APIRouter

from app.schemas.director import Chat, Plan
from app.services import director_chat

router = APIRouter(prefix="/api/projects/{pid}/director")


@router.post("/chat")
async def chat(pid: str, body: Chat):
    return await director_chat.chat(pid, body)


@router.post("/plan")
async def plan(pid: str, body: Plan):
    return await director_chat.apply_plan(pid, body)
