"""Model providers (orchestration §6, §35; DECISIONS.md "Environment and inference").

`ModelProvider` is the protocol the runner depends on. `A9Provider` is the local
OpenAI-compatible adapter for the A9 gateway and structurally defeats its three deviations:
every request opens with a unique `run_id` line (no shared sessions), the response's `model`
is verified against the request (no silent substitution), and client-side tool definitions are
never sent (structured output is prompt-requested JSON). `FakeModelProvider` drives CI.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx


class ProviderError(RuntimeError):
    pass


class ModelUnavailable(ProviderError):
    """409 (model not loaded) past the retry budget, or 503 past it."""


@dataclass
class ModelRequest:
    run_id: uuid.UUID
    profile: str
    model: str
    system: str
    user: str
    max_tokens: int = 400
    temperature: float = 0.6
    json_mode: bool = True
    history: list[dict[str, str]] = field(
        default_factory=list
    )  # repair turns only; never campaign memory

    def messages(self) -> list[dict[str, str]]:
        # The run_id line is the first thing in the first user message: A9 keys sessions on it.
        first = f"run_id: {self.run_id}\n\n{self.user}"
        return [
            {"role": "system", "content": self.system},
            {"role": "user", "content": first},
            *self.history,
        ]


@dataclass
class ModelResponse:
    text: str
    model_echo: str | None
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None
    model_mismatch: bool = False
    finish_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class ModelProvider(Protocol):
    name: str

    async def generate(self, request: ModelRequest) -> ModelResponse: ...

    def stream(self, request: ModelRequest) -> AsyncIterator[str]: ...


# ---------------------------------------------------------------------------------------------
# A9 / OpenAI-compatible
# ---------------------------------------------------------------------------------------------


class A9Provider:
    name = "a9"

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        client_name: str = "ai-ttrpg",
        max_concurrent: int = 2,
        timeout_s: float = 240.0,
        busy_retries: int = 6,
        not_loaded_wait_s: float = 120.0,
        not_loaded_retries: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}", "X-A9-Client": client_name},
            timeout=timeout_s,
            transport=transport,
        )
        self._sem = asyncio.Semaphore(max_concurrent)
        self.busy_retries = busy_retries
        self.not_loaded_wait_s = not_loaded_wait_s
        self.not_loaded_retries = not_loaded_retries

    async def aclose(self) -> None:
        await self._client.aclose()

    def _body(self, req: ModelRequest, *, stream: bool = False) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": req.model,
            "messages": req.messages(),
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        }
        if req.json_mode:
            body["response_format"] = {"type": "json_object"}
        if stream:
            body["stream"] = True
        return body

    async def _post_with_retries(self, body: dict[str, Any]) -> httpx.Response:
        not_loaded = 0
        for attempt in range(self.busy_retries + self.not_loaded_retries + 1):
            r = await self._client.post("/chat/completions", json=body)
            if r.status_code == 503:
                if attempt >= self.busy_retries:
                    raise ModelUnavailable("A9 busy")
                await asyncio.sleep(float(r.headers.get("Retry-After", "5")))
                continue
            if r.status_code == 409:
                not_loaded += 1
                if not_loaded > self.not_loaded_retries:
                    raise ModelUnavailable(f"model {body['model']} not loaded")
                await asyncio.sleep(
                    min(
                        float(r.headers.get("Retry-After", self.not_loaded_wait_s)),
                        self.not_loaded_wait_s,
                    )
                )
                continue
            if r.status_code >= 400:
                raise ProviderError(f"A9 {r.status_code}: {r.text[:300]}")
            return r
        raise ModelUnavailable("A9 unavailable")

    async def generate(self, req: ModelRequest) -> ModelResponse:
        async with self._sem:
            t0 = time.perf_counter()
            r = await self._post_with_retries(self._body(req))
            latency = int((time.perf_counter() - t0) * 1000)
        data = r.json()
        usage = data.get("usage") or {}
        echo = data.get("model")
        return ModelResponse(
            text=data["choices"][0]["message"]["content"] or "",
            model_echo=echo,
            latency_ms=latency,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            cached_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
            model_mismatch=echo is not None and echo != req.model,
            finish_reason=data["choices"][0].get("finish_reason"),
            raw={
                "id": data.get("id"),
                "a9": data.get("a9"),
                "finish_reason": data["choices"][0].get("finish_reason"),
            },
        )

    async def stream(self, req: ModelRequest) -> AsyncIterator[str]:
        async with self._sem:
            async with self._client.stream(
                "POST", "/chat/completions", json=self._body(req, stream=True)
            ) as r:
                if r.status_code >= 400:
                    raise ProviderError(f"A9 {r.status_code}")
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    chunk = json.loads(payload)
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue  # the final usage-only chunk (stream_options) has no choices
                    delta = (choices[0].get("delta") or {}).get("content")
                    if delta:
                        yield delta


# ---------------------------------------------------------------------------------------------
# Deterministic fake for CI
# ---------------------------------------------------------------------------------------------

Responder = Callable[[ModelRequest], str | dict[str, Any]]


@dataclass
class FakeCall:
    request: ModelRequest
    response_text: str


class FakeModelProvider:
    """Fixture-driven. Register a canned response per role (the role is passed in the profile
    slot by the runner as `role` metadata; here we key on `request.system`'s first line, which
    the prompt repository guarantees is `# role: <name>`), or a responder callable."""

    name = "fake"

    def __init__(self, *, latency_ms: int = 0) -> None:
        self._by_role: dict[str, list[str | dict[str, Any] | Responder]] = {}
        self._default: Responder | None = None
        self.calls: list[FakeCall] = []
        self.latency_ms = latency_ms
        self.model_echo = "fake/model"

    @staticmethod
    def role_of(req: ModelRequest) -> str:
        first = req.system.splitlines()[0] if req.system else ""
        return first.replace("# role:", "").strip() if first.startswith("# role:") else "unknown"

    def register(self, role: str, response: str | dict[str, Any] | Responder) -> FakeModelProvider:
        """Queue a response for a role; the last registered response repeats once the queue is
        exhausted, so a single registration answers every call."""
        self._by_role.setdefault(role, []).append(response)
        return self

    def set_default(self, responder: Responder) -> None:
        self._default = responder

    def _pick(self, req: ModelRequest) -> str:
        role = self.role_of(req)
        queue = self._by_role.get(role)
        if queue:
            item = queue.pop(0) if len(queue) > 1 else queue[0]
        elif self._default is not None:
            item = self._default
        else:
            raise ProviderError(f"FakeModelProvider: no fixture registered for role {role!r}")
        if callable(item):
            item = item(req)
        return item if isinstance(item, str) else json.dumps(item)

    async def generate(self, req: ModelRequest) -> ModelResponse:
        if self.latency_ms:
            await asyncio.sleep(self.latency_ms / 1000)
        text = self._pick(req)
        self.calls.append(FakeCall(req, text))
        return ModelResponse(
            text=text,
            model_echo=self.model_echo,
            latency_ms=self.latency_ms,
            prompt_tokens=len(req.system + req.user) // 4,
            completion_tokens=len(text) // 4,
            cached_tokens=0,
        )

    async def stream(self, req: ModelRequest) -> AsyncIterator[str]:
        text = self._pick(req)
        self.calls.append(FakeCall(req, text))
        for i in range(0, len(text), 24):
            if self.latency_ms:
                await asyncio.sleep(self.latency_ms / 1000 / max(1, len(text) // 24))
            yield text[i : i + 24]
