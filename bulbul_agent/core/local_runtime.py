"""Local Bulbul runtime used by Telegram without the Goa event bus."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from google.adk.agents.llm_agent import Agent
from google.adk.code_executors import BuiltInCodeExecutor
from google.adk.events import Event, EventActions
from google.adk.models import Gemini
from google.adk.runners import Runner
from google.adk.sessions.base_session_service import (
    BaseSessionService,
    GetSessionConfig,
    ListSessionsResponse,
)
from google.adk.tools import AgentTool
from google.adk.tools.google_search_tool import GoogleSearchTool
from google.genai import types

from .goal_service import GoalService
from .memory_service import MemoryService
from .persona_service import PersonaService
from .tools.goal_tool import init_goal_tool, manage_goal
from .tools.memory_tool import init_memory_tool, manage_memory
from .tools.persona_tool import init_persona_tool, update_persona
from .tools.progress_tool import init_progress_tool, send_progress

logger = logging.getLogger(__name__)

APP_NAME = "bulbul"
UI_ENVELOPE_RE = re.compile(r"\s*<bulbul_ui>(?P<json>.*?)</bulbul_ui>\s*$", re.DOTALL)
_SESSION_EVENTS: Dict[str, List[Event]] = {}

_persona_service: Optional[PersonaService] = None
_memory_service: Optional[MemoryService] = None
_goal_service: Optional[GoalService] = None


def _services() -> tuple[PersonaService, MemoryService, GoalService]:
    global _persona_service, _memory_service, _goal_service
    if _persona_service is None:
        _persona_service = PersonaService()
    if _memory_service is None:
        _memory_service = MemoryService()
    if _goal_service is None:
        _goal_service = GoalService()
    return _persona_service, _memory_service, _goal_service


class LocalSessionService(BaseSessionService):
    """Small ADK session service backed by one in-memory session."""

    def __init__(self, session_id: str, user_id: str, state: dict[str, Any], events: List[Event]):
        from google.adk.sessions.session import Session

        self.session = Session(
            id=session_id,
            app_name=APP_NAME,
            user_id=user_id,
            state=state,
            events=list(events),
        )

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[GetSessionConfig] = None,
    ):
        return self.session

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict] = None,
        session_id: Optional[str] = None,
    ):
        return self.session

    async def list_sessions(
        self,
        *,
        app_name: str,
        user_id: Optional[str] = None,
    ) -> ListSessionsResponse:
        return ListSessionsResponse(sessions=[self.session])

    async def delete_session(self, *, app_name: str, user_id: str, session_id: str) -> None:
        self.session.events.clear()

    async def append_event(self, session, event):
        if not any(existing.id == event.id for existing in session.events):
            session.events.append(event)
        return event


def _build_agent() -> Agent:
    search_agent = Agent(
        model=Gemini(model="gemini-3.1-pro-preview"),
        name="google_search",
        description="Search the web for current information, news, facts.",
        instruction="You are a search assistant. Use Google Search. Respond in Arabic.",
        tools=[GoogleSearchTool()],
    )
    code_agent = Agent(
        model=Gemini(model="gemini-3.1-pro-preview"),
        name="code_executor",
        description="Execute Python code for math calculations, data analysis.",
        instruction="Write and execute Python code. Respond in Arabic.",
        code_executor=BuiltInCodeExecutor(),
    )
    prompt_file = Path(__file__).parent / "instruction.md"
    return Agent(
        model=Gemini(model="gemini-3.1-pro-preview"),
        name="bulbul",
        instruction=prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else "أنت مساعد ذكي.",
        description="assistant",
        tools=[
            update_persona,
            manage_memory,
            manage_goal,
            send_progress,
            AgentTool(agent=search_agent),
            AgentTool(agent=code_agent),
        ],
    )


_agent: Optional[Agent] = None


def _agent_instance() -> Agent:
    global _agent
    if _agent is None:
        _agent = _build_agent()
    return _agent


def _format_goals_for_state(goals: List[dict]) -> str:
    if not goals:
        return "لا توجد أهداف محفوظة بعد"

    lines = []
    for goal in goals:
        completed_steps = goal.get("completed_steps") or []
        completed_display = "، ".join(str(step) for step in completed_steps) if completed_steps else "لا يوجد"
        block = [
            f"- [{goal.get('goal_id')}] {goal.get('title')} ({goal.get('status')})",
            f"  الوصف: {goal.get('description') or 'غير محدد'}",
            f"  ملخص التقدم: {goal.get('progress_summary') or 'لا يوجد بعد'}",
            f"  الخطوات المكتملة: {completed_display}",
            f"  الخطوة الحالية: {goal.get('current_step') or 'غير محددة'}",
            f"  الخطوة التالية: {goal.get('next_action') or 'غير محددة'}",
        ]
        if goal.get("archived_reason"):
            block.append(f"  سبب الأرشفة: {goal.get('archived_reason')}")
        lines.append("\n".join(block))
    return "\n\n".join(lines)


def _format_goals_reply(goals: List[dict]) -> str:
    if not goals:
        return "ما عندك أهداف محفوظة حالياً.\n\nإذا عندك هدف تعلّم أو هدف شخصي، قل لي عنه وبسألك إذا تحب أتابعه معك."

    status_labels = {
        "proposed": "مقترح",
        "active": "نشط",
        "paused": "متوقف مؤقتاً",
        "completed": "مكتمل",
        "archived": "مؤرشف",
    }
    lines = ["<b>أهدافك الحالية</b>"]
    for goal in goals:
        lines.extend([
            "",
            f"<b>{goal.get('title')}</b> <code>{goal.get('goal_id')}</code>",
            f"الحالة: {status_labels.get(goal.get('status'), goal.get('status'))}",
            f"التقدم: {goal.get('progress_summary') or 'لا يوجد ملخص بعد'}",
            f"الخطوة الحالية: {goal.get('current_step') or 'غير محددة'}",
            f"التالي: {goal.get('next_action') or 'غير محدد'}",
        ])
    lines.append("\nقل: كمل هدف goal-01، أو وقف الهدف، أو أرني تقدمي.")
    return "\n".join(lines)


def _goal_cards_ui(goals: List[dict]) -> dict:
    return {"type": "goal_cards", "goals": goals}


def _short_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _validate_ui_element(element: Any) -> Optional[dict]:
    if not isinstance(element, dict):
        return None

    element_type = element.get("type")
    if element_type == "actions":
        buttons = []
        for raw_button in (element.get("buttons") or [])[:8]:
            if not isinstance(raw_button, dict):
                continue
            label = _short_text(raw_button.get("label"), 64)
            if not label:
                continue
            button = {
                "id": re.sub(r"[^A-Za-z0-9_-]", "_", _short_text(raw_button.get("id") or label, 32))
                or f"action_{len(buttons) + 1}",
                "label": label,
            }
            url = _short_text(raw_button.get("url"), 2048)
            prompt = _short_text(raw_button.get("prompt"), 1000)
            if url.startswith(("http://", "https://")):
                button["url"] = url
            elif prompt:
                button["prompt"] = prompt
            else:
                continue
            buttons.append(button)
        return {"type": "actions", "buttons": buttons} if buttons else None

    if element_type == "quiz":
        question = _short_text(element.get("question"), 300)
        options = [_short_text(option, 100) for option in (element.get("options") or [])[:10]]
        options = [option for option in options if option]
        correct_index = element.get("correct_index")
        if not question or len(options) < 2:
            return None
        if not isinstance(correct_index, int) or correct_index < 0 or correct_index >= len(options):
            return None
        return {
            "type": "quiz",
            "question": question,
            "options": options,
            "correct_index": correct_index,
            "explanation": _short_text(element.get("explanation"), 200),
        }

    if element_type == "poll":
        question = _short_text(element.get("question"), 300)
        options = [_short_text(option, 100) for option in (element.get("options") or [])[:10]]
        options = [option for option in options if option]
        if not question or len(options) < 2:
            return None
        return {
            "type": "poll",
            "question": question,
            "options": options,
            "multiple_answers": bool(element.get("multiple_answers")),
        }

    return None


def _validate_dynamic_ui(data: Any) -> Optional[dict]:
    if not isinstance(data, dict) or data.get("version") != 1:
        return None

    elements = []
    for element in (data.get("elements") or [])[:5]:
        validated = _validate_ui_element(element)
        if validated:
            elements.append(validated)

    return {"version": 1, "elements": elements} if elements else None


def extract_dynamic_ui(text: str) -> tuple[str, Optional[dict]]:
    match = UI_ENVELOPE_RE.search(text or "")
    if not match:
        return text, None

    visible_text = (text or "")[:match.start()].rstrip()
    try:
        data = json.loads(match.group("json").strip())
    except json.JSONDecodeError as exc:
        logger.warning("Invalid bulbul_ui JSON envelope: %s", exc)
        return visible_text, None

    ui = _validate_dynamic_ui(data)
    if not ui:
        logger.warning("Rejected empty or invalid bulbul_ui envelope")
    return visible_text, ui


def reset_local_session(user_id: str | int) -> None:
    _SESSION_EVENTS.pop(str(user_id), None)


def _manual_event(author: str, role: str, text: str) -> Event:
    return Event(
        id=str(uuid.uuid4()),
        invocation_id=str(uuid.uuid4()),
        author=author,
        content=types.Content(role=role, parts=[types.Part(text=text)]),
        actions=EventActions(state_delta={}),
        turn_complete=True,
    )


async def ask_local_agent(
    *,
    user_id: str | int,
    text: str,
    image_bytes: Optional[bytes] = None,
    image_mime: str = "",
    progress_callback: Optional[Callable[[str], Awaitable[None]]] = None,
) -> dict:
    user_id_str = str(user_id)
    query_text = (text or "").strip()
    persona_service, memory_service, goal_service = _services()

    if query_text == "/reset_persona":
        await persona_service.reset_persona(user_id_str)
        reset_local_session(user_id_str)
        return {
            "status": "success",
            "response": "تم إعادة تعيين شخصية المساعد! 🔄\n\nتم مسح جميع التفضيلات والإعدادات السابقة.\nفي المحادثة القادمة، سأتعرف عليك من جديد وأتكيف مع تفضيلاتك.\n\nأرسل أي رسالة للبدء! ✨",
            "ui": None,
        }

    if query_text == "/goals":
        goals = await goal_service.get_goals(user_id_str)
        return {
            "status": "success",
            "response": _format_goals_reply(goals),
            "ui": _goal_cards_ui(goals) if goals else None,
        }

    persona = await persona_service.get_persona(user_id_str)
    memories = await memory_service.get_memories(user_id_str)
    goals = await goal_service.get_goals(
        user_id_str,
        statuses=("proposed", "active", "paused"),
    )

    init_persona_tool(persona_service, user_id_str)
    init_memory_tool(memory_service, user_id_str)
    init_goal_tool(goal_service, user_id_str)
    init_progress_tool(progress_callback)

    initial_state = dict(persona)
    initial_state["current_time"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    initial_state["user_memories"] = (
        "\n".join(f"- [{memory['fact_id']}] {memory['fact']}" for memory in memories)
        if memories
        else "لا توجد ذكريات محفوظة بعد"
    )
    initial_state["user_goals"] = _format_goals_for_state(goals)

    session = LocalSessionService(
        session_id=user_id_str,
        user_id=user_id_str,
        state=initial_state,
        events=_SESSION_EVENTS.get(user_id_str, []),
    )
    runner = Runner(agent=_agent_instance(), app_name=APP_NAME, session_service=session)

    parts = []
    if query_text:
        parts.append(types.Part(text=query_text))
    if image_bytes:
        parts.append(
            types.Part(
                inline_data=types.Blob(
                    mime_type=image_mime or "image/jpeg",
                    data=image_bytes,
                )
            )
        )
    if not parts:
        parts.append(types.Part(text="[رسالة فارغة]"))

    response_parts = []
    final_response_seen = False
    try:
        events = runner.run_async(
            user_id=user_id_str,
            session_id=user_id_str,
            new_message=types.Content(role="user", parts=parts),
        )
        async for event in events:
            if not final_response_seen and event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text and not getattr(part, "thought", False):
                        response_parts.append(part.text)
            if event.is_final_response():
                final_response_seen = True

        final_response = "".join(response_parts)
    except Exception as exc:
        logger.exception("Agent execution failed")
        return {"status": "error", "error": str(exc)}
    finally:
        init_progress_tool(None)

    if not final_response:
        final_response = "عذراً، لم أتمكن من تجهيز إجابة واضحة."

    visible_response, dynamic_ui = extract_dynamic_ui(final_response)
    session_events = list(session.session.events)
    if not any(event.content and event.content.role == "user" for event in session_events[-2:]):
        session_events.append(_manual_event("user", "user", query_text or "[رسالة صورة]"))
    if not any(event.is_final_response() for event in session_events[-3:]):
        session_events.append(_manual_event("bulbul", "model", visible_response))
    _SESSION_EVENTS[user_id_str] = session_events[-80:]

    return {
        "status": "success",
        "response": visible_response,
        "ui": dynamic_ui,
    }
