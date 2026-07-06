"""Local Bulbul smoke-test entrypoint.

The Telegram service is now the production entrypoint. This module remains for
manual local checks without the old Goa poller.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from dotenv import load_dotenv

from bulbul_agent.core.local_runtime import ask_local_agent

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    load_dotenv()
    prompt = " ".join(sys.argv[1:]).strip() or "عرّفني على نفسك باختصار."
    result = await ask_local_agent(user_id="local", text=prompt)
    if result.get("status") != "success":
        raise RuntimeError(result.get("error") or "Bulbul failed")
    print(result.get("response", ""))


if __name__ == "__main__":
    asyncio.run(main())
