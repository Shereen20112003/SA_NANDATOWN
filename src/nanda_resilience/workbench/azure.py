from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Callable, Protocol

import httpx

from .config import Deployment


class ProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool = False, group_failure: bool = False):
        super().__init__(message)
        self.retryable = retryable
        self.group_failure = group_failure


@dataclass
class Completion:
    text: str
    usage: dict


class ModelClient(Protocol):
    async def complete(self, deployment: Deployment, system: str, prompt: str,
                       on_token: Callable[[str], None]) -> Completion: ...


class AzureClient:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def complete(self, deployment: Deployment, system: str, prompt: str,
                       on_token: Callable[[str], None]) -> Completion:
        payload = {
            "model": deployment.deployment,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
            "max_completion_tokens": 2200,
            "response_format": {"type": "json_object"},
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        parts, usage, finish = [], {}, None
        output_length = 0
        try:
            async with asyncio.timeout(90):
                async with self.client.stream(
                    "POST", deployment.endpoint + "/openai/v1/chat/completions",
                    headers={"api-key": deployment.key.get_secret_value()},
                    json=payload, timeout=60,
                ) as response:
                    if response.status_code != 200:
                        status = response.status_code
                        guidance = {
                            401: "Check the API key and resource endpoint.",
                            403: "Check resource permissions or network access.",
                            404: "Check the resource endpoint and deployment name.",
                            400: "Use a deployment supporting chat completions and JSON mode.",
                            429: "Azure quota or rate limit was reached.",
                        }.get(status, "Azure could not complete the request.")
                        raise ProviderError(f"Azure HTTP {status}. {guidance}",
                                            retryable=status in {429, 500, 502, 503, 504},
                                            group_failure=status in {429, 500, 502, 503, 504})
                    if "text/event-stream" not in response.headers.get("content-type", ""):
                        raise ProviderError("Azure did not return the requested event stream.")
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError as exc:
                            raise ProviderError("Azure returned a malformed stream event.") from exc
                        if not isinstance(chunk, dict):
                            raise ProviderError("Azure returned an invalid stream shape.")
                        if chunk.get("error"):
                            raise ProviderError("Azure reported an error inside its response stream.")
                        if chunk.get("usage") is not None:
                            usage = chunk["usage"]
                            if not isinstance(usage, dict) or any(
                                type(usage[key]) is not int or usage[key] < 0
                                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                                if key in usage
                            ):
                                raise ProviderError("Azure returned invalid usage metadata.")
                        choices = chunk.get("choices", [])
                        if not isinstance(choices, list):
                            raise ProviderError("Azure returned invalid stream choices.")
                        for choice in choices:
                            if not isinstance(choice, dict) or not isinstance(choice.get("delta"), dict):
                                raise ProviderError("Azure returned an invalid stream delta.")
                            token = choice["delta"].get("content")
                            if token is None:
                                token = ""
                            if not isinstance(token, str):
                                raise ProviderError("Azure returned non-text content.")
                            if token:
                                parts.append(token)
                                output_length += len(token)
                                if output_length > 50000:
                                    raise ProviderError("Model output exceeded the application limit.")
                                on_token(token)
                            if choice.get("finish_reason"):
                                finish = choice["finish_reason"]
        except (httpx.HTTPError, TimeoutError) as exc:
            raise ProviderError("Azure connection timed out or failed.",
                                retryable=True, group_failure=True) from exc
        if finish != "stop" or not parts:
            raise ProviderError(f"Azure response was incomplete (finish reason: {finish or 'missing'}).")
        return Completion("".join(parts), usage)
