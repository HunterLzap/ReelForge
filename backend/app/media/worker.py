"""Isolate blocking encoders so cancelling a pipeline stops its media processes."""

import asyncio
import json
import os
import signal
import sys
from contextlib import suppress
from pathlib import Path


async def run_command(args, *, cwd=None, env=None):
    process = await asyncio.create_subprocess_exec(
        *map(str, args),
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=os.name == "posix",
    )
    try:
        # Bound CLI progress logs in memory even for long exports.
        tail = b""
        while chunk := await process.stdout.read(16 * 1024):
            tail = (tail + chunk)[-8192:]
        if await process.wait():
            raise RuntimeError(tail.decode(errors="replace"))
    except asyncio.CancelledError:
        if process.returncode is None:
            with suppress(ProcessLookupError):
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
        await process.wait()
        raise


async def run(operation, *args):
    from contextlib import AsyncExitStack

    from app.media.limits import slot
    from app.services.storage_manager import guard

    async with AsyncExitStack() as stack:
        await stack.enter_async_context(slot("render"))
        if operation == "cards":
            await stack.enter_async_context(slot("browser"))
        await asyncio.to_thread(guard)
        return await _run(operation, *args)


async def _run(operation, *args):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.media.worker",
        operation,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=os.name == "posix",
    )
    try:
        stdout, stderr = await process.communicate(
            json.dumps(args, default=str).encode()
        )
    except asyncio.CancelledError:
        with suppress(ProcessLookupError):
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise RuntimeError(stderr.decode(errors="replace")[-1800:])
    return json.loads(stdout)


def main():
    operation = sys.argv[1]
    args = json.load(sys.stdin)
    if operation == "encode":
        from app.media import assembler, tts

        path, text, project = args
        folder = Path(path)
        result = asyncio.run(
            tts.narrate(
                folder,
                text,
                project["voice"],
                project["target_format"],
                project["speech_rate"],
                project["subtitle_style"],
            )
        )
        assembler.clip(folder)
    elif operation == "cards":
        from app.media.renderer import render_batch

        project, jobs, count = args
        render_batch(project, [(Path(path), scene) for path, scene in jobs], count)
        result = None
    elif operation == "export":
        from app.pipeline.orchestrator import export

        export(*args)
        result = None
    else:
        raise ValueError(operation)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
