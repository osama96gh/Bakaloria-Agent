# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Bulbul** is a personalized AI assistant Telegram bot built with Google ADK (Agent Development Kit) and Gemini models. The bot provides customizable educational assistance in Arabic, supporting text, voice, and image inputs. Key capabilities include:

- **Dynamic Persona System**: Users can customize the bot's name, role, personality, dialect, and instructions
- **User Memory Management**: Bot learns and stores facts about users across conversations
- **Multi-modal Input**: Handles text messages, photos (with vision), and voice messages (with transcription)
- **Persistent Sessions**: Goa-backed task/event history, persona, and memory, with Supabase still used for outreach data

## Development Commands

### Running the Bot

```bash
# Install dependencies (using uv)
uv pip install .

# Run bot locally
python bot.py

# Docker deployment
docker-compose up --build
```

### Environment Setup

Required environment variables in `.env`:
- `TELEGRAM_BOT_TOKEN`: From @BotFather
- `ANTHROPIC_API_KEY`: From Anthropic Console (legacy, may not be actively used)
- `GOA_API_KEY`: Goa participant key used by the Telegram service and as a fallback for the agent
- `GOA_AGENT_API_KEY`: Optional Goa participant key for the Bulbul agent; preferred for agent-owned persona/memory
- `SUPABASE_URL`: Supabase project URL, required for outreach
- `SUPABASE_SERVICE_KEY`: Service role key from Supabase, required for outreach
- `LOG_LEVEL`: Optional (default: INFO)

## Architecture

### Core Service Layer (`core/`)

The heart of the application is the **ADK Event Loop pattern** in `core/service.py`:

1. **Single Agent Instance**: One `Agent` object is created at module-level initialization with `instruction.md` as the prompt template
2. **State Injection**: User-specific persona and memory are injected into the agent's state at runtime (not in the prompt)
3. **Runner Pattern**: Each query creates a new `Runner` instance that executes the agent with the injected state
4. **Event Streaming**: Agent responses are streamed back as async events, filtering out thinking/reasoning parts

**Key insight**: The agent is stateless by design—personality comes from database-loaded state, not hardcoded prompts. This enables true per-user customization.

### Service Modules

- **`PersonaService`** (`persona_service.py`): Flexible Goa-backed key-value store for agent personality attributes. Any attribute can be stored (name, role, dialect, mission, etc.).

- **`MemoryService`** (`memory_service.py`): Manages user memories/facts in Goa memory with sequential fact IDs (fact-01, fact-02, etc.). Supports add/update/remove operations.

### Agent Tools (`core/tools/`)

Two tools available to the agent:

- **`update_persona`** (`persona_tool.py`): Allows agent to save its own personality configuration based on user preferences
- **`manage_memory`** (`memory_tool.py`): Allows agent to add/update/remove facts about the user

**Tool Context Injection**: Tools are initialized with current `user_id` via `init_persona_tool()` and `init_memory_tool()` before each agent invocation. This pattern allows stateless tool functions to access user context.

### Telegram Layer (`telegram_bot/`)

- **Handlers** (`handlers.py`):
  - Text messages → `handle_message()`
  - Photos → `handle_photo_message()` (downloads image, passes bytes to agent)
  - Voice → `handle_voice_message()` (downloads, transcribes with Gemini STT, passes text to agent)
  - All handlers use `send_reply_with_retry()` for timeout resilience
  - HTML formatting is used (not Markdown) - sanitized via `sanitize_html_for_telegram()`

- **Transcription** (`telegram_bot/transcription/`): Google Chirp 3 based STT for Arabic voice messages (max 2 minutes)

### Instruction Template (`core/instruction.md`)

Written in Arabic. Uses placeholder syntax like `{name?}` for runtime state injection. Critical sections:

- Agent persona fields (name, role, description, personality, dialect, etc.)
- User memories display (formatted list with fact IDs)
- Tool usage instructions (when to save memories vs persona)
- HTML formatting rules for Telegram (never use Markdown)

**Important**: The `?` suffix in placeholders makes them optional—empty values don't break the prompt.

## Persistence

### Goa

1. **Task/event log**: Conversation tasks, question/answer events, pending work, and blobs.
   - Normal Telegram chat uses `external_ref=telegram_{user_id}`.
   - Proactive outreach decisions use `external_ref=telegram_{user_id}_outreach`, are created as child tasks of the active chat task when Goa accepts `parent_task_id`, and close after each decision to avoid cluttering the user chat history with internal SKIP checks.
   - When processing an outreach child task, Bulbul loads a bounded slice of recent parent chat events (`OUTREACH_PARENT_CONTEXT_EVENTS`, default 30) so the outreach message can account for current session context without polluting the main task.

2. **`/memory` user facts**: User memory facts under namespaced keys:
   - `user:{user_id}:memory:{fact_id}`
   - Values are JSON documents containing `fact`, `user_id`, and `fact_id`

3. **`/memory` persona**: Agent persona values under namespaced keys:
   - `user:{user_id}:persona:{key}`
   - Values are JSON documents containing the persona `key` and `value`

### Supabase

1. **`user_engagement`**: Proactive outreach tracking
   - Stores platform user IDs, chat IDs, last interaction time, outreach preferences, and last outreach time

## Key Patterns

### Adding a New Platform (beyond Telegram)

1. Register or configure a Goa participant for the platform.
2. Use `POST /tasks/upsert` with an `external_ref` like `web_{platform_user_id}`.
3. Post user input as Goa `question` events targeted to the Bulbul participant.
4. Let `bulbul_agent.main` process pending Goa questions and write answers back as Goa `answer` events.

### Extending Persona Attributes

No schema changes needed—just update `instruction.md` with new placeholder and optionally modify agent's tool instructions. The agent will automatically start saving new attributes via `update_persona` tool.

### Adding New Agent Tools

1. Create tool function in `core/tools/` using ADK's function calling format
2. Add to agent's `tools` list in `service.py` initialization
3. Document tool usage in `instruction.md` (Arabic)

### Message Formatting

Always use HTML tags in agent responses: `<b>`, `<i>`, `<code>`, `<pre>`, `<a href="">`. Never use Markdown (`**`, `*`, `` ` ``). Telegram parser is strict—use `sanitize_html_for_telegram()` to escape special characters.

## Important Constraints

- **Voice messages**: 2-minute max duration (enforced in handler)
- **Telegram messages**: 4096 character limit (auto-split via `split_message()`)
- **Image support**: Photos only (not documents). Largest resolution is downloaded.
- **Supabase**: Outreach requires Supabase connection. Persona and user memories are read/written through Goa `/memory`.
- **ADK Runner**: Each `Runner` instance should only be used once—create new for each query
