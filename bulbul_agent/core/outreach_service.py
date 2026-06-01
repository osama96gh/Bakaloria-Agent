"""Proactive outreach service for Bulbul.

Tracks user engagement and decides when to proactively reach out
to users who have been inactive, using the agent's persona and
memory context to craft personalized messages.
"""

import logging
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from supabase import create_client, Client

logger = logging.getLogger(__name__)


class OutreachService:
    """Manages user engagement tracking and proactive outreach decisions."""

    def __init__(self, supabase_url: str, supabase_key: str) -> None:
        self._client: Client = create_client(supabase_url, supabase_key)

    def update_interaction(
        self, platform: str, platform_user_id: str, chat_id: int
    ) -> None:
        """Record a user interaction (called on every incoming message).

        Upserts into user_engagement to track latest activity and chat_id.
        """
        try:
            self._client.table("user_engagement").upsert(
                {
                    "platform": platform,
                    "platform_user_id": platform_user_id,
                    "chat_id": chat_id,
                    "last_interaction_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="platform,platform_user_id",
            ).execute()
        except Exception as e:
            logger.error(f"Failed to update interaction for user {platform_user_id}: {e}")

    def get_outreach_candidates(
        self,
        platform: str,
        inactivity_hours: int = 6,
        cooldown_hours: int = 24,
    ) -> List[Dict[str, Any]]:
        """Find users eligible for proactive outreach.

        Returns users who:
        - Have been inactive for at least `inactivity_hours`
        - Haven't received outreach in the last `cooldown_hours`
        - Have outreach_enabled = TRUE
        """
        try:
            now = datetime.now(timezone.utc)
            inactivity_cutoff = now.isoformat()
            cooldown_cutoff = now.isoformat()

            # Use raw SQL via RPC for the time comparison,
            # or use Supabase filters with computed timestamps
            # We'll query all enabled users and filter in Python for clarity
            result = (
                self._client.table("user_engagement")
                .select("*")
                .eq("platform", platform)
                .eq("outreach_enabled", True)
                .execute()
            )

            if not result.data:
                return []

            candidates = []
            for row in result.data:
                last_interaction = datetime.fromisoformat(
                    row["last_interaction_at"].replace("Z", "+00:00")
                )
                hours_since_interaction = (now - last_interaction).total_seconds() / 3600

                if hours_since_interaction < inactivity_hours:
                    continue

                # Check cooldown
                if row.get("last_outreach_at"):
                    last_outreach = datetime.fromisoformat(
                        row["last_outreach_at"].replace("Z", "+00:00")
                    )
                    hours_since_outreach = (now - last_outreach).total_seconds() / 3600
                    if hours_since_outreach < cooldown_hours:
                        continue

                candidates.append(row)

            logger.info(
                f"Found {len(candidates)} outreach candidates for platform {platform}"
            )
            return candidates

        except Exception as e:
            logger.error(f"Failed to get outreach candidates: {e}")
            return []

    def record_outreach(self, platform: str, platform_user_id: str) -> None:
        """Record that outreach was sent to a user."""
        try:
            self._client.table("user_engagement").update(
                {"last_outreach_at": datetime.now(timezone.utc).isoformat()}
            ).eq("platform", platform).eq(
                "platform_user_id", platform_user_id
            ).execute()
        except Exception as e:
            logger.error(
                f"Failed to record outreach for user {platform_user_id}: {e}"
            )


# Module-level singleton
_supabase_url = os.getenv("SUPABASE_URL")
_supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

outreach_service: Optional[OutreachService] = None
if _supabase_url and _supabase_key:
    outreach_service = OutreachService(
        supabase_url=_supabase_url,
        supabase_key=_supabase_key,
    )
