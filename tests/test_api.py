import asyncio

import httpx

from app.api import pipeline
from app.api.stream import stream
from app.db.database import init
from app.main import app


async def test_api_approvals_edit_and_export():
    from app.core.config import settings

    mount = app.routes[-1].app
    mount.directory = settings().workspace_dir
    mount.all_directories = [str(mount.directory)]
    await init()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://local"
    ) as client:
        assert (await client.get("/docs")).status_code == 200
        assert (
            await client.post("/api/projects", json={"topic": " "})
        ).status_code == 422
        response = await client.post(
            "/api/projects", json={"topic": "核对清单", "target_format": "cards_3_4"}
        )
        assert response.status_code == 201
        pid = response.json()["id"]
        path = "/api/projects/" + pid
        assert (await client.get("/api/projects")).json()[0]["id"] == pid
        assert (await client.post(path + "/approve")).status_code == 409

        async def step(action, status):
            assert (await client.post(path + "/" + action)).status_code == 202
            await asyncio.wait_for(pipeline.tasks[pid], 90)
            data = (await client.get(path)).json()
            assert data["status"] == status
            return data

        await step("run", "WAITING_OUTLINE")
        data = await step("approve", "WAITING_STORYBOARD")
        scene_path = path + "/scenes/" + data["scenes"][0]["id"]
        assert (
            await client.patch(scene_path, json={"visual_payload": {}})
        ).status_code == 422
        assert (
            await client.patch(scene_path, json={"narration": "请检查。"})
        ).status_code == 200
        data = await step("approve", "COMPLETED")
        assert (await client.get("/workspace/" + pid + "/output/cards/01.png")).headers[
            "content-type"
        ] == "image/png"
        assert (await client.get("/workspace/reelforge.db")).status_code == 404
        assert (
            await client.patch(scene_path, json={"narration": "再次检查。"})
        ).status_code == 200
        await step("rebuild", "COMPLETED")

        class Connected:
            async def is_disconnected(self):
                return False

        events = stream(pid, Connected(), data["logs"][-1]["id"])
        try:
            assert "EDITOR" in await anext(events)
        finally:
            await events.aclose()
