import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock


os.environ.setdefault("GOA_API_KEY", "test-goa-key")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bulbul_agent.core.memory_service import MemoryService


class JsonResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class MemoryServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = MemoryService(goa_url="http://goa.test", goa_api_key="key")

    async def test_get_memories_reads_migrated_rich_values(self):
        self.service._request = AsyncMock(return_value=JsonResponse({
            "entries": [
                {
                    "key": "user:123:memory:fact-02",
                    "value": {"fact_id": "fact-02", "fact": "ثاني حقيقة"},
                },
                {
                    "key": "user:123:memory:fact-01",
                    "value": {
                        "type": "user_memory_fact",
                        "source": "supabase.user_memory",
                        "user_id": "123",
                        "fact_id": "fact-01",
                        "fact": "أول حقيقة",
                    },
                },
            ]
        }))

        memories = await self.service.get_memories("123")

        self.assertEqual(
            memories,
            [
                {"fact_id": "fact-01", "fact": "أول حقيقة"},
                {"fact_id": "fact-02", "fact": "ثاني حقيقة"},
            ],
        )
        self.service._request.assert_awaited_once_with(
            "GET",
            "/memory",
            params={"prefix": "user:123:memory:"},
        )

    async def test_add_memory_uses_next_fact_id_and_goa_key(self):
        self.service._request = AsyncMock(side_effect=[
            JsonResponse({
                "entries": [
                    {
                        "key": "user:123:memory:fact-02",
                        "value": {"fact_id": "fact-02", "fact": "قديم"},
                    }
                ]
            }),
            JsonResponse({"key": "user:123:memory:fact-03"}),
        ])

        fact_id = await self.service.add_memory("123", "جديد")

        self.assertEqual(fact_id, "fact-03")
        _, post_call = self.service._request.await_args_list
        self.assertEqual(post_call.args[:2], ("POST", "/memory"))
        self.assertEqual(post_call.kwargs["json"]["key"], "user:123:memory:fact-03")
        self.assertEqual(post_call.kwargs["json"]["value"]["fact"], "جديد")
        self.assertEqual(post_call.kwargs["json"]["value"]["fact_id"], "fact-03")

    async def test_update_memory_returns_false_when_missing(self):
        self.service._request = AsyncMock(return_value=JsonResponse({"entries": []}))

        updated = await self.service.update_memory("123", "fact-01", "نص")

        self.assertFalse(updated)
        self.service._request.assert_awaited_once_with(
            "GET",
            "/memory",
            params={"key": "user:123:memory:fact-01"},
        )

    async def test_update_memory_overwrites_existing_key(self):
        self.service._request = AsyncMock(side_effect=[
            JsonResponse({"entries": [{"key": "user:123:memory:fact-01"}]}),
            JsonResponse({"key": "user:123:memory:fact-01"}),
        ])

        updated = await self.service.update_memory("123", "fact-01", "محدث")

        self.assertTrue(updated)
        _, post_call = self.service._request.await_args_list
        self.assertEqual(post_call.args[:2], ("POST", "/memory"))
        self.assertEqual(post_call.kwargs["json"]["key"], "user:123:memory:fact-01")
        self.assertEqual(post_call.kwargs["json"]["value"]["fact"], "محدث")

    async def test_remove_memory_deletes_by_key(self):
        self.service._request = AsyncMock(return_value=JsonResponse({"deleted": 1}))

        removed = await self.service.remove_memory("123", "fact-01")

        self.assertTrue(removed)
        self.service._request.assert_awaited_once_with(
            "DELETE",
            "/memory",
            params={"key": "user:123:memory:fact-01"},
        )

    async def test_clear_memories_deletes_by_prefix(self):
        self.service._request = AsyncMock(return_value=JsonResponse({"deleted": 2}))

        await self.service.clear_memories("123")

        self.service._request.assert_awaited_once_with(
            "DELETE",
            "/memory",
            params={"prefix": "user:123:memory:"},
        )


if __name__ == "__main__":
    unittest.main()
