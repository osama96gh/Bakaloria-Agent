"""
Main polling loop for the Bulbul agent, running entirely on the Goa event bus.
"""

import asyncio
import logging
import os
import sys
import uuid
from typing import Optional, List
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
import httpx

from google.adk.agents.llm_agent import Agent
from google.adk.models import Gemini
from google.adk.runners import Runner
from google.adk.tools import AgentTool
from google.adk.code_executors import BuiltInCodeExecutor
from google.adk.tools.google_search_tool import GoogleSearchTool
from google.genai import types
from google.adk.events import Event, EventActions

# Load env
env_paths = [
    Path(__file__).parent.parent / ".env",
    Path("/app/.env"),
    Path(".env"),
]
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path)
        break

from bulbul_agent.core.persona_service import PersonaService
from bulbul_agent.core.memory_service import MemoryService
from bulbul_agent.core.tools.persona_tool import init_persona_tool, update_persona
from bulbul_agent.core.tools.memory_tool import init_memory_tool, manage_memory

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Config
GOA_URL = os.getenv("GOA_URL", "http://195.35.0.64").rstrip("/")
GOA_API_KEY = os.getenv("GOA_API_KEY")
if not GOA_API_KEY:
    logger.error("GOA_API_KEY is required for bulbul agent to authenticate.")
    sys.exit(1)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("SUPABASE_URL and SUPABASE_SERVICE_KEY are required for persona/memory services.")
    sys.exit(1)

# Services
_persona_service = PersonaService(supabase_url=SUPABASE_URL, supabase_key=SUPABASE_KEY)
_memory_service = MemoryService(supabase_url=SUPABASE_URL, supabase_key=SUPABASE_KEY)

# Define Agent
_search_agent = Agent(
    model=Gemini(model='gemini-3.1-pro-preview'),
    name="google_search",
    description="Search the web for current information, news, facts.",
    instruction="You are a search assistant. Use Google Search. Respond in Arabic.",
    tools=[GoogleSearchTool()],
)

_code_agent = Agent(
    model=Gemini(model='gemini-3.1-pro-preview'),
    name="code_executor",
    description="Execute Python code for math calculations, data analysis.",
    instruction="Write and execute Python code. Respond in Arabic.",
    code_executor=BuiltInCodeExecutor(),
)

_prompt_file = Path(__file__).parent / "core" / "instruction.md"
_agent = Agent(
    model=Gemini(model='gemini-3.1-pro-preview'),
    name="bulbul",
    instruction=_prompt_file.read_text(encoding="utf-8") if _prompt_file.exists() else "أنت مساعد ذكي.",
    description="assistant",
    tools=[
        update_persona,
        manage_memory,
        AgentTool(agent=_search_agent),
        AgentTool(agent=_code_agent),
    ],
)


from google.adk.sessions.base_session_service import BaseSessionService, GetSessionConfig, ListSessionsResponse

class DummySessionService(BaseSessionService):
    """A minimal mock SessionService so ADK Runner doesn't complain. We feed it the history manually."""
    def __init__(self, session_id, user_id, state):
        from google.adk.sessions.session import Session
        self.session = Session(id=session_id, app_name="bulbul", user_id=user_id, state=state, events=[])
        
    async def get_session(self, *, app_name: str, user_id: str, session_id: str, config: Optional[GetSessionConfig] = None): 
        return self.session
    
    async def create_session(self, *, app_name: str, user_id: str, state: Optional[dict] = None, session_id: Optional[str] = None): 
        return self.session
        
    async def list_sessions(self, *, app_name: str, user_id: Optional[str] = None) -> ListSessionsResponse:
        return ListSessionsResponse(sessions=[self.session])
        
    async def delete_session(self, *, app_name: str, user_id: str, session_id: str) -> None:
        pass
        
    async def append_event(self, session, event): 
        if not any(existing.id == event.id for existing in session.events):
            session.events.append(event)
        return event


async def _goa_request(method: str, path: str, **kwargs) -> httpx.Response:
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {GOA_API_KEY}"
    headers["Content-Type"] = "application/json"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        return await client.request(method, f"{GOA_URL}{path}", headers=headers, **kwargs)


async def get_goa_task_events(task_id: str) -> List[dict]:
    resp = await _goa_request("GET", f"/tasks/{task_id}")
    resp.raise_for_status()
    return resp.json().get("events", [])


def _goa_event_to_adk_event(goa_ev: dict) -> Event:
    """Convert Goa event into ADK event so we can feed it to the LLM."""
    content = None
    if goa_ev.get("content"):
        # For simplicity, if it's a question it's from the user, if answer it's from the model
        role = "user" if goa_ev["event_type"] == "question" else "model"
        parts = []
        text = goa_ev["content"].get("text")
        if text:
            parts.append(types.Part(text=text))
        # Note: We intentionally skip attaching the image blobs here to avoid 
        # re-downloading them for old history. The text context is usually enough.

        if not parts:
            parts.append(types.Part(text="[رسالة فارغة أو صورة فقط]"))
            
        content = types.Content(role=role, parts=parts)
        # NOTE: Handling image attachments from Goa would go here
        
        content = types.Content(role=role, parts=parts)

    return Event(
        id=goa_ev["id"],
        invocation_id=str(uuid.uuid4()),
        author="user" if goa_ev["event_type"] == "question" else "bulbul",
        content=content,
        actions=EventActions(state_delta={}),
        turn_complete=True,
    )


async def process_question(task_id: str, question_event_id: str, goa_events: List[dict]):
    """Processes a pending question via ADK."""
    
    # Extract the user_id from the task's external_ref (e.g. "telegram_12345")
    resp = await _goa_request("GET", f"/tasks/{task_id}")
    resp.raise_for_status()
    task_data = resp.json()["task"]
    ext_ref = task_data.get("external_ref", "")
    user_id = ext_ref.split("_")[1] if "_" in ext_ref else "default_user"
    
    logger.info(f"Processing question {question_event_id} for user {user_id}")
    
    # Identify the actual question text/image
    question_event = next((e for e in goa_events if e["id"] == question_event_id), None)
    if not question_event:
        logger.error(f"Question event {question_event_id} not found in task {task_id}")
        return
        
    query_text = question_event.get("content", {}).get("text", "")
    
    # Handle commands (simplistic intercept)
    if query_text == "/start":
        reply = "مرحباً! أنا مساعدك الذكي القابل للتخصيص ✨\n\nالأوامر المتاحة:\n/help - عرض المساعدة\n/new - بدء محادثة جديدة\n/reset_persona - إعادة تعيين شخصيتي والبدء من جديد\n\nأرسل أي رسالة وسأتعرف عليك! 🎓"
        await post_answer(task_id, question_event_id, reply)
        return
    elif query_text == "/help":
        reply = "📖 كيفية استخدام المساعد الذكي\n\nأنا مساعد قابل للتخصيص - يمكنك تحديد شخصيتي ودوري وأسلوبي!\n\nالأوامر المتاحة:\n/start - رسالة الترحيب\n/help - عرض هذه المساعدة\n/new - بدء محادثة جديدة (نسيان المحادثة السابقة)\n/reset_persona - إعادة تعيين شخصيتي والبدء من جديد\n\nكيفية تخصيصي:\n• أخبرني باسمك المفضل لي\n• حدد دوري (مدرس، صديق، مستشار، إلخ)\n• اختر أسلوب التواصل (رسمي، ودود، مرح)\n• حدد المجالات التي تريد مساعدة فيها\n\nنصائح:\n• يمكنني تذكر المحادثة والتفضيلات السابقة\n• إذا أردت تغيير شخصيتي، فقط أخبرني\n• استخدم /reset_persona للبدء من الصفر\n\nفقط أرسل رسالتك وسأساعدك! 💡"
        await post_answer(task_id, question_event_id, reply)
        return
    elif query_text == "/new":
        reply = "تم بدء محادثة جديدة! 🆕\n\nيمكنك الآن طرح سؤال جديد، وسأنسى المحادثة السابقة.\n\nفقط أرسل سؤالك! 📚"
        await post_answer(task_id, question_event_id, reply)
        return
    elif query_text == "/reset_persona":
        await _persona_service.reset_persona(user_id)
        reply = "تم إعادة تعيين شخصية المساعد! 🔄\n\nتم مسح جميع التفضيلات والإعدادات السابقة.\nفي المحادثة القادمة، سأتعرف عليك من جديد وأتكيف مع تفضيلاتك.\n\nأرسل أي رسالة للبدء! ✨"
        await post_answer(task_id, question_event_id, reply)
        return
    elif query_text.startswith("/"):
        # Ignore other commands
        await post_answer(task_id, question_event_id, "عذراً، أمر غير معروف.")
        return

    # Load State (Persona + Memory)
    persona = await _persona_service.get_persona(user_id)
    memories = await _memory_service.get_memories(user_id)
    init_persona_tool(_persona_service, user_id)
    init_memory_tool(_memory_service, user_id)

    initial_state = dict(persona)
    initial_state["current_time"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    initial_state["user_memories"] = "\n".join(f"- [{m['fact_id']}] {m['fact']}" for m in memories) if memories else "لا توجد ذكريات محفوظة بعد"

    # Only use events that happened before this question. Goa may already contain
    # late answers or retries for newer work, and those must not leak backward.
    current_idx = next((i for i, ev in enumerate(goa_events) if ev["id"] == question_event_id), len(goa_events))
    prior_goa_events = goa_events[:current_idx]

    # Find the index of the last /new command to truncate history
    last_new_idx = -1
    for i, ev in enumerate(prior_goa_events):
        if ev.get("event_type") == "question" and ev.get("content", {}).get("text", "").strip() == "/new":
            last_new_idx = i
            
    # Keep only events after the last /new
    relevant_goa_events = prior_goa_events[last_new_idx + 1:] if last_new_idx != -1 else prior_goa_events

    # Command questions and their canned answers are delivery-layer control flow,
    # not conversational context for the LLM.
    command_question_ids = {
        ev["id"]
        for ev in relevant_goa_events
        if ev.get("event_type") == "question"
        and ev.get("content", {}).get("text", "").strip().startswith("/")
    }
    relevant_goa_events = [
        ev for ev in relevant_goa_events
        if ev.get("id") not in command_question_ids
        and ev.get("in_reply_to") not in command_question_ids
    ]

    # Convert Goa history to ADK history
    adk_history = [_goa_event_to_adk_event(ev) for ev in relevant_goa_events if ev["event_type"] in ("question", "answer")]
    
    # Note: We exclude the *current* question from history because we pass it as `new_message` to the Runner
    adk_history = [e for e in adk_history if e.id != question_event_id]

    dummy_session = DummySessionService(task_id, user_id, initial_state)
    dummy_session.session.events = adk_history

    runner = Runner(
        agent=_agent,
        app_name="bulbul",
        session_service=dummy_session
    )

    parts = []
    if query_text:
        parts.append(types.Part(text=query_text))
    
    # Process images attached to the question
    attachments = question_event.get("content", {}).get("attachments", [])
    for attachment in attachments:
        blob_id = attachment.get("blob_id")
        mime_type = attachment.get("mime_type", "image/jpeg")
        
        if blob_id and mime_type.startswith("image/"):
            try:
                # Fetch blob from Goa - Note: blobs are fetched from global /blobs endpoint, not task-specific
                blob_resp = await _goa_request("GET", f"/blobs/{blob_id}")
                blob_resp.raise_for_status()
                image_bytes = blob_resp.content
                parts.append(types.Part(inline_data=types.Blob(mime_type=mime_type, data=image_bytes)))
                logger.info(f"Loaded image {blob_id} into agent context")
            except Exception as e:
                logger.error(f"Failed to fetch blob {blob_id} from Goa: {e}")

    if not parts:
        parts.append(types.Part(text="[النظام: حدث خطأ في تحميل أو استخراج رسالة المستخدم. يرجى إخباره بذلك.]"))

    content = types.Content(role='user', parts=parts)
    
    # Run Agent
    response_parts = []
    try:
        events = runner.run_async(
            user_id=user_id,
            session_id=task_id,
            new_message=content
        )
        async for event in events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text and not getattr(part, 'thought', False):
                        response_parts.append(part.text)
            if event.is_final_response():
                break
                
        final_response = "".join(response_parts)
    except Exception as e:
        logger.exception("Agent execution failed")
        final_response = "عذراً، حدث خطأ أثناء التفكير في إجابة."

    # Post Answer
    await post_answer(task_id, question_event_id, final_response)


async def post_answer(task_id: str, question_id: str, text: str):
    """Posts an answer event to Goa."""
    payload = {
        "event_type": "answer",
        "content": {"text": text},
        "in_reply_to": question_id,
        "payload": {
            "answering": [question_id]
        }
    }
    resp = await _goa_request("POST", f"/tasks/{task_id}/events", json=payload)
    if resp.status_code == 201:
        logger.info(f"Answer posted for question {question_id}")
    else:
        logger.error(f"Failed to post answer: {resp.text}")


async def main_loop():
    logger.info("Starting Bulbul Agent Poller on Goa /pending...")
    
    while True:
        try:
            resp = await _goa_request("GET", "/pending")
            if resp.status_code == 200:
                pending_items = resp.json()
                
                for item in pending_items:
                    task_id = item["task_id"]
                    q_id = item["question_event_id"]
                    
                    # Fetch task events to get context
                    events = await get_goa_task_events(task_id)
                    
                    # Process it
                    await process_question(task_id, q_id, events)
                    
        except Exception as e:
            logger.error(f"Polling error: {e}")
            
        await asyncio.sleep(2.0)  # Poll every 2 seconds


if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Agent stopped.")
