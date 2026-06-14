import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock


os.environ.setdefault("GOA_API_KEY", "test-goa-key")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bulbul_agent.core.persona_service import PersonaService


class JsonResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class PersonaServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = PersonaService(goa_url="http://goa.test", goa_api_key="key")

    async def test_get_persona_reads_rich_and_direct_values(self):
        self.service._request = AsyncMock(return_value=JsonResponse({
            "entries": [
                {
                    "key": "user:123:persona:name",
                    "value": {
                        "type": "agent_persona_value",
                        "key": "name",
                        "value": "بلبل",
                    },
                },
                {
                    "key": "user:123:persona:dialect",
                    "value": "syrian",
                },
            ]
        }))

        persona = await self.service.get_persona("123")

        self.assertEqual(persona, {"name": "بلبل", "dialect": "syrian"})
        self.service._request.assert_awaited_once_with(
            "GET",
            "/memory",
            params={"prefix": "user:123:persona:"},
        )

    async def test_get_value_returns_none_when_missing(self):
        self.service._request = AsyncMock(return_value=JsonResponse({"entries": []}))

        value = await self.service.get_value("123", "name")

        self.assertIsNone(value)
        self.service._request.assert_awaited_once_with(
            "GET",
            "/memory",
            params={"key": "user:123:persona:name"},
        )

    async def test_set_value_upserts_goa_memory(self):
        self.service._request = AsyncMock(return_value=JsonResponse({"ok": True}))

        await self.service.set_value("123", "role", "مساعد")

        self.service._request.assert_awaited_once()
        args, kwargs = self.service._request.await_args
        self.assertEqual(args[:2], ("POST", "/memory"))
        self.assertEqual(kwargs["json"]["key"], "user:123:persona:role")
        self.assertEqual(kwargs["json"]["value"]["key"], "role")
        self.assertEqual(kwargs["json"]["value"]["value"], "مساعد")

    async def test_set_values_upserts_each_value(self):
        self.service._request = AsyncMock(return_value=JsonResponse({"ok": True}))

        await self.service.set_values("123", {"name": "بلبل", "dialect": "syrian"})

        self.assertEqual(self.service._request.await_count, 2)

    async def test_delete_value_deletes_by_key(self):
        self.service._request = AsyncMock(return_value=JsonResponse({"deleted": 1}))

        await self.service.delete_value("123", "name")

        self.service._request.assert_awaited_once_with(
            "DELETE",
            "/memory",
            params={"key": "user:123:persona:name"},
        )

    async def test_reset_persona_deletes_by_prefix(self):
        self.service._request = AsyncMock(return_value=JsonResponse({"deleted": 3}))

        await self.service.reset_persona("123")

        self.service._request.assert_awaited_once_with(
            "DELETE",
            "/memory",
            params={"prefix": "user:123:persona:"},
        )


if __name__ == "__main__":
    unittest.main()
