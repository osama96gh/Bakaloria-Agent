# Copyright 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""ADK Tool for updating agent persona configuration."""

import json
import logging
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from ..persona_service import PersonaService

logger = logging.getLogger(__name__)

# Global references set at runtime
_persona_service: "PersonaService" = None
_current_user_id: str = None


def init_persona_tool(persona_service: "PersonaService", user_id: str) -> None:
    """
    Initialize the persona tool with service and user context.

    Must be called before each agent interaction to set the context.

    Args:
        persona_service: The PersonaService instance to use
        user_id: The current user's ID
    """
    global _persona_service, _current_user_id
    _persona_service = persona_service
    _current_user_id = user_id


async def update_persona(updates: str) -> Dict[str, Any]:
    """
    Save persona attributes to remember for future conversations.

    Use this tool to save any preferences the user shares about how you should
    behave, your name, role, personality, expertise areas, language preferences, etc.

    Examples:
    - {"name": "سارة"} - save your name
    - {"role": "مدرسة رياضيات"} - save your role
    - {"personality": "ودود ومرح"} - save personality description
    - {"dialect": "syrian", "mission": "مساعدة الطلاب"} - save multiple values

    You can use any keys that make sense. Common keys:
    - name: Your name (what the user calls you)
    - role: Your role/job description
    - personality: Your personality traits
    - mission: Your purpose/mission statement
    - dialect: Language dialect (syrian, egyptian, gulf, standard)
    - instructions: Custom instructions from the user
    - description: A description of who you are

    Args:
        updates: JSON string containing key-value pairs to save.
                 Example: '{"name": "سارة", "role": "معلمة"}'

    Returns:
        Status object with saved keys or error message
    """
    global _persona_service, _current_user_id

    if not _persona_service or not _current_user_id:
        logger.error("Persona tool not initialized - missing service or user_id")
        return {
            "status": "error",
            "message": "خدمة الشخصية غير متاحة حالياً",
            "saved_keys": []
        }

    try:
        # Parse the JSON updates
        updates_dict = json.loads(updates)

        if not isinstance(updates_dict, dict):
            return {
                "status": "error",
                "message": "يجب أن تكون التحديثات كائن JSON",
                "saved_keys": []
            }

        if not updates_dict:
            return {
                "status": "success",
                "message": "لم يتم تحديد أي قيم للحفظ",
                "saved_keys": []
            }

        # Save to Supabase via PersonaService
        await _persona_service.set_values(_current_user_id, updates_dict)

        saved_keys = list(updates_dict.keys())
        logger.info(f"Updated persona for user {_current_user_id}: {saved_keys}")

        return {
            "status": "success",
            "message": f"تم حفظ: {', '.join(saved_keys)}",
            "saved_keys": saved_keys
        }

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in update_persona: {e}")
        return {
            "status": "error",
            "message": f"JSON غير صالح: {str(e)}",
            "saved_keys": []
        }
    except Exception as e:
        logger.error(f"Error in update_persona: {e}")
        return {
            "status": "error",
            "message": f"خطأ في حفظ الشخصية: {str(e)}",
            "saved_keys": []
        }
