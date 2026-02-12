# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Bulbul** is a personalized AI assistant Telegram bot built with Google ADK (Agent Development Kit) and Gemini models. The bot provides customizable educational assistance in Arabic, supporting text, voice, and image inputs. Key capabilities include:

- **Dynamic Persona System**: Users can customize the bot's name, role, personality, dialect, and instructions
- **User Memory Management**: Bot learns and stores facts about users across conversations
- **Multi-modal Input**: Handles text messages, photos (with vision), and voice messages (with transcription)
- **Persistent Sessions**: Supabase-backed storage for conversations, personas, and memories across platforms

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
- `SUPABASE_URL`: Supabase project URL
- `SUPABASE_SERVICE_KEY`: Service role key from Supabase
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

- **`PersonaService`** (`persona_service.py`): Flexible key-value store for agent personality attributes. Any attribute can be stored (name, role, dialect, mission, etc.). Values are JSON-serialized if complex.

- **`MemoryService`** (`memory_service.py`): Manages user memories/facts with sequential fact IDs (fact-01, fact-02, etc.). Supports add/update/remove operations.

- **`SupabaseSessionService`** (`supabase_session_service.py`): Implements ADK's session interface for Supabase. Stores conversation history in `adk_sessions` table with JSONB state.

### Agent Tools (`core/tools/`)

Two tools available to the agent:

- **`update_persona`** (`persona_tool.py`): Allows agent to save its own personality configuration based on user preferences
- **`manage_memory`** (`memory_tool.py`): Allows agent to add/update/remove facts about the user

**Tool Context Injection**: Tools are initialized with current `user_id` via `init_persona_tool()` and `init_memory_tool()` before each agent invocation. This pattern allows stateless tool functions to access user context.

### Telegram Layer (`telegram_bot/`)

- **`SessionManager`** (`session_manager.py`): Maps platform user IDs (Telegram user IDs) to ADK session IDs. Stores mappings in `platform_user_sessions` table. Provides in-memory fallback if Supabase unavailable.

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

## Database Schema (Supabase)

### Required Tables

1. **`agent_persona`**: Key-value persona storage
   - Primary key: `(user_id, key)`
   - Columns: `user_id`, `key`, `value` (TEXT), `updated_at`

2. **`user_memory`**: User facts/memories
   - Primary key: `(user_id, fact_id)`
   - Columns: `user_id`, `fact_id`, `fact`, `updated_at`

3. **`platform_user_sessions`**: Session mapping
   - Columns: `platform`, `platform_user_id`, `session_id`, `is_active`, `updated_at`

4. **`adk_sessions`**: ADK conversation history (managed by SupabaseSessionService)
   - Columns: `id`, `app_name`, `user_id`, `state` (JSONB), `messages` (JSONB array), timestamps

## Key Patterns

### Adding a New Platform (beyond Telegram)

1. Create a new session manager instance: `SessionManager(platform="web")`
2. Map platform user IDs to ADK sessions using `get_or_create_session()` and `store_session()`
3. Call `process_agent_query()` from `core/service.py` with `user_id` as string
4. The shared agent instance and services work across all platforms

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
- **Supabase**: All services require Supabase connection—no in-memory fallback for persona/memory (only for session mapping)
- **ADK Runner**: Each `Runner` instance should only be used once—create new for each query
