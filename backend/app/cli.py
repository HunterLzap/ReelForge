import asyncio

import typer

from app.db import repository as repo
from app.db.database import init
from app.pipeline.orchestrator import folder, run
from app.schemas.project import FormatType, ProjectCreate

app = typer.Typer()


@app.command()
def demo(
    topic: str = typer.Option(...), target_format: FormatType = FormatType.landscape
):
    async def execute():
        await init()
        p = await repo.create(
            ProjectCreate(topic=topic, target_format=target_format, auto_approve=True)
        )
        await run(p["id"])
        typer.echo(
            folder(p["id"])
            / "output"
            / ("cards.zip" if target_format == FormatType.cards else "final.mp4")
        )

    asyncio.run(execute())


@app.command()
def rebuild(project_id: str):
    async def execute():
        await init()
        if (await repo.project(project_id))["status"] != "COMPLETED":
            raise typer.BadParameter("仅支持已完成项目")
        await run(project_id, "rebuild")

    asyncio.run(execute())


if __name__ == "__main__":
    app()
