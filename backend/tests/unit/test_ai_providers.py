"""Providers: deterministic fake; A9 adapter request shaping, retries, echo verification."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from app.ai.providers import (
    A9Provider,
    FakeModelProvider,
    ModelRequest,
    ModelUnavailable,
    ProviderError,
)

pytestmark = pytest.mark.unit


def req(system="# role: ai_player\nrules", user="hello", **kw) -> ModelRequest:
    return ModelRequest(
        run_id=uuid.uuid4(),
        profile="balanced_reasoning",
        model="ttrpg/local-general",
        system=system,
        user=user,
        **kw,
    )


async def test_fake_provider_keys_on_role_and_queues_fixtures():
    fake = FakeModelProvider()
    fake.register("ai_player", {"decision_summary": "first"}).register("ai_player", "second")
    fake.register("narrator", lambda r: f"echo:{r.user}")
    a = await fake.generate(req())
    b = await fake.generate(req())
    c = await fake.generate(req())  # last fixture repeats
    assert (
        json.loads(a.text)["decision_summary"] == "first"
        and b.text == "second"
        and c.text == "second"
    )
    n = await fake.generate(req(system="# role: narrator\n", user="x"))
    assert n.text == "echo:x" and len(fake.calls) == 4
    with pytest.raises(ProviderError):
        await fake.generate(req(system="# role: unknown_role\n"))
    chunks = [
        d async for d in fake.stream(req(system="# role: narrator\n", user="stream me please now"))
    ]
    assert "".join(chunks) == "echo:stream me please now"


def _transport(handler):
    return httpx.MockTransport(handler)


async def test_a9_request_shape_defeats_sessions_and_sends_no_tools():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={
                "model": "ttrpg/local-general",
                "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "prompt_tokens_details": {"cached_tokens": 8},
                },
            },
        )

    p = A9Provider(
        "http://a9.test/v1", "a9_secret", client_name="ai-ttrpg", transport=_transport(handler)
    )
    r = req(json_mode=True)
    resp = await p.generate(r)
    body = seen["body"]
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1]["content"].startswith(f"run_id: {r.run_id}\n")  # unique first line
    assert body["response_format"] == {"type": "json_object"} and "tools" not in body
    assert (
        seen["headers"]["authorization"] == "Bearer a9_secret"
        and seen["headers"]["x-a9-client"] == "ai-ttrpg"
    )
    assert (
        resp.model_echo == "ttrpg/local-general"
        and not resp.model_mismatch
        and resp.cached_tokens == 8
    )
    await p.aclose()


async def test_a9_flags_model_substitution_and_retries_busy_then_gives_up_on_not_loaded():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, headers={"Retry-After": "0"})
        return httpx.Response(
            200,
            json={
                "model": "ttrpg/other-model",
                "choices": [{"message": {"content": "ok"}}],
                "usage": {},
            },
        )

    p = A9Provider("http://a9.test/v1", "t", transport=_transport(handler))
    resp = await p.generate(req(json_mode=False))
    assert calls["n"] == 2 and resp.model_mismatch and resp.model_echo == "ttrpg/other-model"

    def not_loaded(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, headers={"Retry-After": "0"}, json={"detail": "swapped out"})

    p2 = A9Provider(
        "http://a9.test/v1",
        "t",
        transport=_transport(not_loaded),
        not_loaded_wait_s=0.01,
        not_loaded_retries=1,
    )
    with pytest.raises(ModelUnavailable):
        await p2.generate(req())
    await p.aclose()
    await p2.aclose()


async def test_a9_streams_sse_deltas():
    def handler(request: httpx.Request) -> httpx.Response:
        lines = [
            'data: {"choices":[{"delta":{"content":"The "}}]}',
            'data: {"choices":[{"delta":{"content":"rain."}}]}',
            "data: [DONE]",
        ]
        return httpx.Response(
            200, text="\n".join(lines) + "\n", headers={"content-type": "text/event-stream"}
        )

    p = A9Provider("http://a9.test/v1", "t", transport=_transport(handler))
    assert "".join([d async for d in p.stream(req(json_mode=False))]) == "The rain."
    await p.aclose()


async def test_transport_errors_become_provider_errors_and_reads_scale_with_budget() -> None:
    import httpx

    from app.ai.providers import A9Provider, ModelRequest, ProviderError

    def boom(request):
        raise httpx.ReadTimeout("slow", request=request)

    p = A9Provider("http://a9/v1", "t", transport=httpx.MockTransport(boom))
    req = ModelRequest(
        run_id=__import__("uuid").uuid4(),
        profile="deep_world_author",
        model="ttrpg/local-general",
        system="s",
        user="u",
        max_tokens=4096,
    )
    try:
        await p.generate(req)
        raise AssertionError("expected ProviderError")
    except ProviderError as exc:
        assert "timed out" in str(exc)
    finally:
        await p.aclose()
    assert A9Provider.read_timeout_for(4096, 240.0) > 300
    assert A9Provider.read_timeout_for(400, 240.0) == 240.0
