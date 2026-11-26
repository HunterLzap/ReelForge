import asyncio
import re

import httpx
import trafilatura
from duckduckgo_search import DDGS

from app.core.config import settings


async def search(query):
    cfg = settings()
    if cfg.tavily_api_key:
        try:
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
                hits = [
                    {
                        "title": x["title"],
                        "url": x["url"],
                        "snippet": extract_passages(
                            x.get("raw_content") or x["content"]
                        ),
                    }
                    for x in res.json()["results"]
                ]
                if hits:
                    return hits
        except (httpx.HTTPError, KeyError, ValueError):
            pass

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


async def material_text(url):
    """Fetch a bounded public HTTP resource. Pin each hop to a validated IP."""
    import ipaddress
    import socket

    original = httpx.URL(url)
    async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
        for _ in range(4):
            if original.scheme not in {"http", "https"} or original.userinfo:
                raise ValueError("需要公开网页地址")
            addresses = await asyncio.get_running_loop().getaddrinfo(
                original.host, original.port or 443, type=socket.SOCK_STREAM
            )
            ip = ipaddress.ip_address(addresses[0][4][0])
            if not ip.is_global or ip.is_multicast:
                raise ValueError("仅抓取公开网页")
            async with client.stream(
                "GET",
                original.copy_with(host=str(ip)),
                headers={"Host": original.netloc.decode()},
                extensions={"sni_hostname": original.host},
            ) as response:
                if response.is_redirect:
                    original = original.join(response.headers["location"])
                    continue
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes(65536):
                    body.extend(chunk)
                    if len(body) > 2_000_000:
                        break
                return await asyncio.to_thread(trafilatura.extract, bytes(body))
    return None


async def materials(text, offline):
    hits = []
    for line in dict.fromkeys(s.strip() for s in text.splitlines() if s.strip()):
        pattern = r"https?://[^\s<>\"，。；]+"
        note = re.sub(pattern, "", line).strip()
        urls = re.findall(pattern, line)
        if note:
            hits.append(
                {
                    "title": note[:40],
                    "url": None,
                    "snippet": note,
                    "credibility_note": "用户提供资料",
                }
            )
        for url in urls:
            body = None
            if not offline:
                try:
                    body = await material_text(url)
                except (OSError, ValueError, KeyError, httpx.HTTPError):
                    pass
            hits.append(
                {
                    "title": url,
                    "url": url,
                    "snippet": extract_passages(
                        body or note or "仅提供链接，未取得正文"
                    ),
                    "credibility_note": "用户提供资料"
                    if body
                    else "用户提供资料 · 未取得正文",
                }
            )
    return hits
