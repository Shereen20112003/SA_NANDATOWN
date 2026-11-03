from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
from pathlib import Path
from typing import Callable

from .azure import Completion, ProviderError
from .config import Deployment

logger = logging.getLogger(__name__)


class CocoStream:
    def __init__(self, on_token: Callable[[str], None]):
        self.on_token = on_token
        self.parts: list[str] = []
        self.length = 0
        self.result: dict | None = None

    def consume(self, line: str):
        if not line.strip():
            return
        if re.sub(r"\x1b\[[0-9;]*m", "", line).startswith("Note: another coco daemon"):
            logger.info("coco reused an alternate local daemon port.")
            return
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProviderError("coco returned malformed stream output. Check coco doctor.") from exc
        if not isinstance(item, dict):
            raise ProviderError("coco returned an invalid stream shape.")
        if item.get("type") == "stream_event":
            event = item.get("event")
            if not isinstance(event, dict):
                raise ProviderError("coco returned an invalid stream event.")
            if event.get("type") == "content_block_delta":
                delta = event.get("delta")
                if not isinstance(delta, dict):
                    raise ProviderError("coco returned an invalid content delta.")
                if delta.get("type") == "text_delta":
                    text = delta.get("text")
                    if not isinstance(text, str):
                        raise ProviderError("coco returned non-text output.")
                    self.length += len(text)
                    if self.length > 50000:
                        raise ProviderError("Model output exceeded the application limit.")
                    self.parts.append(text)
                    self.on_token(text)
        elif item.get("type") == "result":
            if self.result is not None:
                raise ProviderError("coco returned duplicate results.")
            self.result = item

    def completion(self) -> Completion:
        result = self.result
        if not result or result.get("is_error") is not False or result.get("subtype") != "success":
            raise ProviderError("coco did not complete successfully. Check coco status, login, and model access.")
        if result.get("num_turns") != 1 or result.get("stop_reason") != "end_turn":
            raise ProviderError("coco output was incomplete or exceeded the single-turn limit.")
        text = result.get("result")
        if not isinstance(text, str) or not text.strip() or len(text) > 50000:
            raise ProviderError("coco returned an empty or oversized result.")
        if self.parts and text != "".join(self.parts):
            raise ProviderError("coco's final result did not match its streamed output.")
        usage = result.get("usage")
        if not isinstance(usage, dict):
            raise ProviderError("coco did not report valid token usage.")
        keys = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
        if any(type(usage.get(key, 0)) is not int or usage.get(key, 0) < 0 for key in keys):
            raise ProviderError("coco returned invalid token counts.")
        if "input_tokens" not in usage or "output_tokens" not in usage:
            raise ProviderError("coco omitted input or output token counts.")
        incoming = sum(usage.get(key, 0) for key in keys if key != "output_tokens")
        outgoing = usage["output_tokens"]
        if not self.parts:
            self.on_token(text)
        # CLI chat models may wrap valid JSON in one Markdown block; retain raw streamed evidence.
        fenced = re.fullmatch(r"```(?:json)?[ \t]*\r?\n(.*)\r?\n```", text.strip(), re.DOTALL)
        if fenced:
            text = fenced[1]
        return Completion(text, {"prompt_tokens": incoming, "completion_tokens": outgoing,
                                 "total_tokens": incoming + outgoing})


class CocoClient:
    def __init__(self, runtime_dir: Path, timeout: float = 120):
        self.runtime_dir = runtime_dir
        self.timeout = timeout

    async def complete(self, deployment: Deployment, system: str, prompt: str,
                       on_token: Callable[[str], None]) -> Completion:
        if not deployment.executable:
            raise ProviderError("The coco executable is not configured.")
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
            env.pop(key, None)
        env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = "2200"
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        env["NO_COLOR"] = "1"
        command = [
            deployment.executable, "run", "--model", deployment.deployment,
            "-p", "--bare", "--tools", "", "--strict-mcp-config",
            "--mcp-config", '{"mcpServers":{}}', "--no-session-persistence",
            "--system-prompt", system, "--output-format", "stream-json",
            "--verbose", "--include-partial-messages", "--max-turns", "1",
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, cwd=self.runtime_dir, env=env, limit=1_000_000,
                start_new_session=os.name != "nt",
            )
        except (OSError, NotImplementedError) as exc:
            raise ProviderError("Could not start coco. Check its executable and the server's subprocess support.") from exc
        stream = CocoStream(on_token)

        async def send():
            process.stdin.write(prompt.encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()

        async def read():
            size = 0
            while line := await process.stdout.readline():
                size += len(line)
                if size > 2_000_000:
                    raise ProviderError("coco exceeded the stream size limit.")
                stream.consume(line.decode("utf-8"))

        async def drain_errors():
            # Do not export CLI diagnostics: they can contain account or credential details.
            size = 0
            while chunk := await process.stderr.read(8192):
                size += len(chunk)
                if size > 1_000_000:
                    raise ProviderError("coco exceeded the diagnostic output limit.")

        workers = [asyncio.create_task(task()) for task in (send, read, drain_errors)]
        try:
            async with asyncio.timeout(self.timeout):
                await asyncio.gather(*workers)
                code = await process.wait()
            if code:
                raise ProviderError(f"coco exited with code {code}. Run coco doctor to check access.")
            return stream.completion()
        except TimeoutError as exc:
            raise ProviderError("coco timed out. Check model availability and Copilot quota.") from exc
        except (UnicodeError, ValueError, BrokenPipeError, ConnectionResetError) as exc:
            raise ProviderError("The coco process returned an unreadable or interrupted stream.") from exc
        finally:
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            if process.returncode is None:
                if os.name == "nt":
                    killer = await asyncio.create_subprocess_exec(
                        "taskkill", "/PID", str(process.pid), "/T", "/F",
                        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                    )
                    await killer.wait()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                await process.communicate()
