import asyncio
import re

import httpx
import trafilatura
from duckduckgo_search import DDGS

from app.core.config import settings


async def search(query):
    cfg = settings()
    if cfg.tavily_api_key:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(
                "https://api.tavily.com/search",
                headers={"Authorization": "Bearer " + cfg.tavily_api_key},
                json={
                    "query": query,
                    "max_results": cfg.max_search_results_per_query,
                    "include_raw_content": True,
                },
            )
            res.raise_for_status()
            return [
                {
                    "title": x["title"],
                    "url": x["url"],
                    "snippet": extract_passages(x.get("raw_content") or x["content"]),
                }
                for x in res.json()["results"]
            ]

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
                "snippet": extract_passages(snippet),
            }

        return await asyncio.gather(*(extract(hit) for hit in hits))


def extract_passages(text):
    paragraphs = [x.strip() for x in re.split(r"[\r\n]+|(?<=。)", text) if x.strip()]

    def score(p):
        return len(re.findall(r"\d{4}|\d+(?:\.\d+)?%?|相比|同比|环比|表示|指出|“", p))

    selected = sorted(enumerate(paragraphs), key=lambda pair: -score(pair[1]))[:12]
    return "\n".join(p for _, p in sorted(selected))[:3000]
