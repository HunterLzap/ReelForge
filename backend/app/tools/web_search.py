import asyncio

import httpx
import trafilatura
from duckduckgo_search import DDGS

from app.core.config import settings


async def search(query):
    def lookup():
        with DDGS(timeout=10) as engine:
            return list(
                engine.text(query, max_results=settings().max_search_results_per_query)
            )

    hits = await asyncio.to_thread(lookup)
    async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:

        async def extract(hit):
            snippet = hit.get("body", "")
            try:
                response = await client.get(hit["href"])
                response.raise_for_status()
                snippet = (
                    await asyncio.to_thread(trafilatura.extract, response.text)
                    or snippet
                )
            except (httpx.HTTPError, ValueError):
                pass
            return {
                "title": hit["title"],
                "url": hit["href"],
                "snippet": snippet[:3000],
            }

        return await asyncio.gather(*(extract(hit) for hit in hits))
