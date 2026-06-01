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

"""ADK Tool for managing user memories."""

import logging
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from ..memory_service import MemoryService

logger = logging.getLogger(__name__)

# Global references set at runtime
_memory_service: "MemoryService" = None
_current_user_id: str = None


def init_memory_tool(memory_service: "MemoryService", user_id: str) -> None:
    """
    Initialize the memory tool with service and user context.

    Must be called before each agent interaction to set the context.

    Args:
        memory_service: The MemoryService instance to use
        user_id: The current user's ID
    """
    global _memory_service, _current_user_id
    _memory_service = memory_service
    _current_user_id = user_id


async def manage_memory(action: str, fact: str = "", fact_id: str = "") -> Dict[str, Any]:
    """
    Manage memories about the user to remember across conversations.

    Use this tool to store, update, or remove facts you learn about the user.
    Memories persist across all sessions and help you personalize interactions.
    These are facts ABOUT THE USER, not about you (use update_persona for that).

    Actions:
    - "add": Save a new fact about the user (fact_id is auto-generated)
    - "update": Modify an existing fact (requires fact_id and new fact text)
    - "remove": Delete a fact (requires fact_id)

    What to store (by category):
    - Personal: name, age, location. Example: "اسمه أحمد، من دمشق"
    - Interests: hobbies, topics they ask about. Example: "مهتم بالبرمجة"
    - Preferences: communication style, detail level. Example: "يفضل الإجابات المختصرة"
    - Context: current goals, projects, deadlines. Example: "يشتغل على مشروع تخرج"

    Fact format guidelines:
    - Write concise, atomic facts (one idea per fact)
    - Good: "مبرمج Python" — one clear fact
    - Good: "يحب القهوة التركية" — one clear fact
    - Bad: "مبرمج Python يحب القهوة وعنده مشروع" — too many ideas in one fact

    When to store: important, lasting information that will help future interactions.
    When NOT to store: transient details, things obvious from context, trivial info.

    Args:
        action: The operation to perform: "add", "update", or "remove"
        fact: The fact text (required for add/update). Write in Arabic, keep concise.
        fact_id: The fact identifier (required for update/remove, format: fact-XX)

    Returns:
        Status object with operation result
    """
    global _memory_service, _current_user_id

    if not _memory_service or not _current_user_id:
        logger.error("Memory tool not initialized - missing service or user_id")
        return {
            "status": "error",
            "message": "خدمة الذاكرة غير متاحة حالياً"
        }

    try:
        if action == "add":
            if not fact:
                return {
                    "status": "error",
                    "message": "يجب تحديد الحقيقة للإضافة"
                }
            new_fact_id = await _memory_service.add_memory(_current_user_id, fact)
            logger.info(f"Added memory {new_fact_id} for user {_current_user_id}")
            return {
                "status": "success",
                "message": f"تم حفظ الذاكرة: {new_fact_id}",
                "fact_id": new_fact_id
            }

        elif action == "update":
            if not fact_id:
                return {
                    "status": "error",
                    "message": "يجب تحديد fact_id للتحديث"
                }
            if not fact:
                return {
                    "status": "error",
                    "message": "يجب تحديد الحقيقة الجديدة"
                }
            success = await _memory_service.update_memory(_current_user_id, fact_id, fact)
            if success:
                logger.info(f"Updated memory {fact_id} for user {_current_user_id}")
                return {
                    "status": "success",
                    "message": f"تم تحديث الذاكرة: {fact_id}"
                }
            return {
                "status": "error",
                "message": f"لم يتم العثور على الذاكرة: {fact_id}"
            }

        elif action == "remove":
            if not fact_id:
                return {
                    "status": "error",
                    "message": "يجب تحديد fact_id للحذف"
                }
            success = await _memory_service.remove_memory(_current_user_id, fact_id)
            if success:
                logger.info(f"Removed memory {fact_id} for user {_current_user_id}")
                return {
                    "status": "success",
                    "message": f"تم حذف الذاكرة: {fact_id}"
                }
            return {
                "status": "error",
                "message": f"لم يتم العثور على الذاكرة: {fact_id}"
            }

        else:
            return {
                "status": "error",
                "message": f"إجراء غير معروف: {action}. استخدم add أو update أو remove"
            }

    except Exception as e:
        logger.error(f"Error in manage_memory: {e}")
        return {
            "status": "error",
            "message": f"خطأ في إدارة الذاكرة: {str(e)}"
        }
