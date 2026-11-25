from time import monotonic

from app.core.llm_client import LLMClient
from app.db import repository as repo


class BaseAgent:
    def __init__(self):
        self.llm = LLMClient()

    async def run(self, pid, *args):
        start = monotonic()
        summary = ""
        try:
            result = await self.process(*args)
            return result
        except Exception as exc:
            summary = str(exc)
            raise
        finally:
            await repo.stage(
                pid,
                type(self).__name__,
                not summary,
                self.llm.usage,
                round((monotonic() - start) * 1000),
                summary or "已完成",
            )
