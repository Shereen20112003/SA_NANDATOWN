"""Transport doubles below are test fixtures, never application demo responses."""

import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from nanda_resilience.workbench.azure import AzureClient, Completion, ProviderError
from nanda_resilience.workbench.config import Deployment, load_deployments
from nanda_resilience.workbench.network import LiveNetwork
from nanda_resilience.workbench.schemas import Answer
from nanda_resilience.workbench.server import create_app
from nanda_resilience.workbench.sources import SourceError, fetch_source, validate_url
from nanda_resilience.workbench.store import Store
from pydantic import SecretStr

QUOTE = "Verified metadata does not prove availability."
SOURCE = f"<html><body><h1>Agent discovery</h1><p>{QUOTE} " \
         "Different agents can share a backend. Discovery identifies candidates; " \
         "testing their interactions reveals shared failures.</p></body></html>"


def event_stream(output, finish="stop"):
    text = json.dumps(output)
    chunks = [
        {"choices": [{"delta": {"content": text[:len(text)//2]}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": text[len(text)//2:]}, "finish_reason": finish}]},
        {"choices": [], "usage": {"prompt_tokens": 40, "completion_tokens": 30, "total_tokens": 70}},
    ]
    return "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"


class FixtureAzure:
    def __init__(self):
        self.calls = []
        self.fail_primary = False
        self.bad_quote = False
        self.bad_citation = False
        self.delay = False

    async def __call__(self, request):
        if request.method == "GET":
            return httpx.Response(200, text=SOURCE, headers={"content-type": "text/html"})
        self.calls.append(request)
        if self.delay:
            await asyncio.sleep(30)
        if self.fail_primary and request.url.host == "primary-test.openai.azure.com":
            return httpx.Response(503, json={"error": {"message": "fixture outage"}})
        body = json.loads(request.content)
        schema = json.loads(body["messages"][0]["content"].split("schema: ", 1)[1])
        prompt = json.loads(body["messages"][1]["content"])
        title = schema["title"]
        if title == "SourceNotes":
            result = {"summary": "Shared failures require testing.",
                      "claims": ["Discovery alone is insufficient."],
                      "quotes": ["invented quotation" if self.bad_quote else QUOTE]}
        elif title == "Brief":
            result = {"title": "Discovery and dependencies",
                      "answer": "Different agents can share a backend [S1].",
                      "findings": ["Agent identities are not independent services [S1]."],
                      "limitations": ["One source only."], "source_ids": ["S1"]}
        elif title == "Review":
            result = {"assessment": "supported", "issues": [],
                      "explanation": "The provided evidence supports the narrow conclusion."}
        elif title == "Challenges":
            result = {"cases": [
                {"name": f"Missing fact {i}", "prompt": "Can I return an opened item?",
                 "failure_type": "missing_context", "expected_behavior": "Ask for missing facts."}
                for i in range(prompt["count"])]}
        elif title == "Answer":
            result = {"answer": "Please provide the receipt and delivery date."}
        elif title == "Judgment":
            result = {"verdict": "pass", "failure_type": "none",
                      "explanation": "The answer asks for missing facts.",
                      "evidence_quote": "Please provide the receipt"}
        else:
            raise AssertionError(f"Unexpected schema {title}")
        if title == "Brief" and self.bad_citation:
            result["answer"] = "An unsupported source [S99]."
        return httpx.Response(200, text=event_stream(result),
                              headers={"content-type": "text/event-stream"})


@pytest.fixture
def configured(tmp_path, monkeypatch):
    for prefix in ("AZURE_OPENAI_", "AZURE_OPENAI_BACKUP_"):
        for field in ("ENDPOINT", "API_KEY", "DEPLOYMENT"):
            monkeypatch.delenv(prefix + field, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "AZURE_OPENAI_ENDPOINT=https://primary-test.openai.azure.com/\n"
        "AZURE_OPENAI_API_KEY=test-only-primary-key\n"
        "AZURE_OPENAI_DEPLOYMENT=test-deployment\n"
        "AZURE_OPENAI_BACKUP_ENDPOINT=https://backup-test.openai.azure.com/\n"
        "AZURE_OPENAI_BACKUP_API_KEY=test-only-backup-key\n"
        "AZURE_OPENAI_BACKUP_DEPLOYMENT=backup-deployment\n"
    )
    fixture = FixtureAzure()
    app = create_app(env, tmp_path / "state", httpx.MockTransport(fixture))
    with TestClient(app) as client:
        yield client, fixture, env


def payload(mode="research"):
    return {"mode": mode, "question": "Explain agent discovery and its limitations.",
            "sources": ["https://arxiv.org/abs/2507.14263"] if mode == "research" else [],
            "rubric": "Ask for missing facts; do not invent policy exceptions.",
            "reference": "A receipt and a delivery date are required.",
            "cases": 2, "policy": "dependency", "consent": True}


def completed(client, body):
    response = client.post("/api/runs", json=body)
    assert response.status_code == 202, response.text
    run_id = response.json()["id"]
    for _ in range(200):
        record = client.get(f"/api/runs/{run_id}").json()
        if record["status"] in {"complete", "failed", "cancelled"}:
            return record
        time.sleep(0.01)
    raise AssertionError("Fixture run did not finish")


def test_missing_configuration_is_explicit(tmp_path, monkeypatch):
    for prefix in ("AZURE_OPENAI_", "AZURE_OPENAI_BACKUP_"):
        for field in ("ENDPOINT", "API_KEY", "DEPLOYMENT"):
            monkeypatch.delenv(prefix + field, raising=False)
    with TestClient(create_app(tmp_path / "missing", tmp_path)) as client:
        assert client.get("/api/status").json()["configured"] is False
        assert client.post("/api/runs", json=payload()).status_code == 503
        assert client.get("/api/runs").json() == []


def test_status_never_exposes_keys(configured):
    client, _, _ = configured
    response = client.get("/api/status")
    assert response.json()["configured"]
    assert response.json()["can_failover"]
    assert "test-only" not in response.text


def test_research_runs_real_pipeline_with_fixture_transport(configured):
    client, fixture, _ = configured
    record = completed(client, payload())
    assert record["status"] == "complete", record["error"]
    result = record["result"]
    assert result["model_calls"] == 3
    assert len(fixture.calls) == 3
    assert result["usage"]["total_tokens"] == 210
    assert result["notes"][0]["quotes"] == [QUOTE]
    kinds = [event["kind"] for event in result["protocol"]["events"]]
    assert "card_registered" in kinds
    assert kinds.count("message_sent") == 6
    assert kinds.count("message_delivered") == 6
    export = client.get(f"/api/runs/{record['id']}/export")
    assert "test-only" not in export.text
    assert export.json()["result"]["brief"]["title"] == "Discovery and dependencies"
    events = client.get(f"/api/runs/{record['id']}/events")
    assert "event: finished" in events.text and '"kind": "token"' in events.text


def test_evaluation_generates_runs_and_judges_cases(configured):
    client, fixture, _ = configured
    record = completed(client, payload("evaluation"))
    assert record["status"] == "complete", record["error"]
    assert len(fixture.calls) == 6
    assert len(record["result"]["cases"]) == 2
    assert all(case["judgment"]["verdict"] == "pass" for case in record["result"]["cases"])
    assert "not ground-truth" in record["result"]["judgment_notice"]


def test_invalid_quote_fails_instead_of_fabricating_result(configured):
    client, fixture, _ = configured
    fixture.bad_quote = True
    record = completed(client, payload())
    assert record["status"] == "failed"
    assert "quotation" in record["error"]
    assert "brief" not in record["result"]


def test_invalid_inline_citation_fails_explicitly(configured):
    client, fixture, _ = configured
    fixture.bad_citation = True
    record = completed(client, payload())
    assert record["status"] == "failed"
    assert "inline citations" in record["error"]


def test_resource_pause_reroutes_and_no_request_reaches_disabled_resource(configured):
    client, fixture, _ = configured
    response = client.post("/api/resources", json={
        "resource": "primary-test.openai.azure.com", "disabled": True})
    assert response.status_code == 200
    record = completed(client, {**payload(), "policy": "price"})
    assert record["status"] == "complete", record["error"]
    assert all(call.url.host == "backup-test.openai.azure.com" for call in fixture.calls)
    export = client.get(f"/api/runs/{record['id']}/export").json()
    assert any(e["data"].get("state") == "failed" for e in export["events"])


def test_real_http_failure_triggers_backup(configured):
    client, fixture, _ = configured
    fixture.fail_primary = True
    record = completed(client, {**payload(), "policy": "price"})
    assert record["status"] == "complete", record["error"]
    assert {call.url.host for call in fixture.calls} == {
        "primary-test.openai.azure.com", "backup-test.openai.azure.com"}


def test_all_resources_disabled_fails_honestly(configured):
    client, fixture, _ = configured
    for name in ("primary-test.openai.azure.com", "backup-test.openai.azure.com"):
        client.post("/api/resources", json={"resource": name, "disabled": True})
    record = completed(client, payload())
    assert record["status"] == "failed"
    assert fixture.calls == []
    assert record["result"]["partial"]["model_calls"] == 0


def test_shared_host_pause_disables_both_deployments(configured):
    client, fixture, env = configured
    env.write_text(env.read_text().replace("backup-test.openai.azure.com",
                                          "primary-test.openai.azure.com"))
    assert not client.get("/api/status").json()["can_failover"]
    client.post("/api/resources", json={"resource": "primary-test.openai.azure.com",
                                       "disabled": True})
    record = completed(client, payload())
    assert record["status"] == "failed"
    assert not fixture.calls


def test_concurrency_limit_and_cancellation_preserve_partial_evidence(configured):
    client, fixture, _ = configured
    fixture.delay = True
    ids = [client.post("/api/runs", json=payload()).json()["id"] for _ in range(2)]
    assert client.post("/api/runs", json=payload()).status_code == 409
    for _ in range(100):
        if len(fixture.calls) == 2:
            break
        time.sleep(0.01)
    assert len(fixture.calls) == 2
    for run_id in ids:
        assert client.post(f"/api/runs/{run_id}/cancel").status_code == 200
    for run_id in ids:
        for _ in range(100):
            record = client.get(f"/api/runs/{run_id}").json()
            if record["status"] == "cancelled":
                break
            time.sleep(0.01)
        assert record["status"] == "cancelled"
        assert record["result"]["partial"]["model_calls"] == 1
        assert "billable" in record["error"]
        events = client.get(f"/api/runs/{run_id}/export").json()["events"]
        assert any(e["kind"] == "agent" and e["data"]["state"] == "cancelled" for e in events)


def test_draft_does_not_modify_original_model_evidence(configured):
    client, _, _ = configured
    record = completed(client, payload())
    original = record["result"]["brief"]["answer"]
    response = client.post(f"/api/runs/{record['id']}/draft", json={"text": "My edited version."})
    assert response.json() == {"saved": True}
    loaded = client.get(f"/api/runs/{record['id']}").json()
    assert loaded["draft"] == "My edited version."
    assert loaded["result"]["brief"]["answer"] == original


@pytest.mark.parametrize("consent", [False, 1, "true", None])
def test_billing_consent_is_required(configured, consent):
    client, fixture, _ = configured
    assert client.post("/api/runs", json={**payload(), "consent": consent}).status_code == 422
    assert fixture.calls == []


def test_cross_origin_mutation_is_rejected(configured):
    client, fixture, _ = configured
    response = client.post("/api/runs", json=payload(), headers={"Origin": "https://example.com"})
    assert response.status_code == 403
    assert fixture.calls == []


@pytest.mark.parametrize("url", [
    "http://arxiv.org/abs/123", "https://127.0.0.1/", "https://localhost/",
    "https://arxiv.org.evil.example/", "https://user:password@arxiv.org/",
    "https://arxiv.org:8080/", "file:///etc/passwd",
    "https://[broken/", "https://arxiv.org:bad/",
])
def test_sources_reject_unapproved_locations(url):
    with pytest.raises(SourceError):
        validate_url(url)


def test_redirect_cannot_escape_supported_hosts():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(302, headers={"location": "https://127.0.0.1/"}))) as client:
            with pytest.raises(SourceError):
                await fetch_source(client, "https://arxiv.org/abs/123", "S1")
    asyncio.run(run())


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500])
def test_azure_errors_are_explicit_and_do_not_leak_secrets(status):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(status, json={"error": "secret-body"}))) as client:
            deployment = Deployment("primary", "https://test.openai.azure.com", "model",
                                    SecretStr("secret-key"), 1)
            with pytest.raises(ProviderError) as error:
                await AzureClient(client).complete(deployment, "JSON", "task", lambda text: None)
            assert str(status) in str(error.value)
            assert "secret" not in str(error.value)
    asyncio.run(run())


def test_truncated_azure_output_is_not_accepted():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, text=event_stream({"answer": "partial"}, finish="length"),
                    headers={"content-type": "text/event-stream"}))) as client:
            with pytest.raises(ProviderError, match="incomplete"):
                await AzureClient(client).complete(
                    Deployment("primary", "https://test.openai.azure.com", "model", SecretStr("test"), 1),
                    "JSON", "task", lambda text: None)
    asyncio.run(run())


@pytest.mark.parametrize("chunk", [
    [], {"choices": None}, {"choices": [None]}, {"choices": [{"delta": None}]},
    {"choices": [{"delta": {"content": 0}}]}, {"choices": [], "usage": []},
    {"choices": [], "usage": {"total_tokens": "30"}},
])
def test_malformed_stream_shapes_are_provider_errors(chunk):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, text=f"data: {json.dumps(chunk)}\n\n",
                                               headers={"content-type": "text/event-stream"}))) as client:
            with pytest.raises(ProviderError):
                await AzureClient(client).complete(
                    Deployment("primary", "https://test.openai.azure.com", "model", SecretStr("test"), 1),
                    "JSON", "task", lambda text: None)
    asyncio.run(run())


@pytest.mark.parametrize("endpoint", ["https://[broken", "https://test.openai.azure.com:bad",
                                      "https://unrelated.example", "http://test.openai.azure.com"])
def test_bad_configuration_returns_safe_error(tmp_path, endpoint):
    deployments, errors = load_deployments(tmp_path / "absent", {
        "AZURE_OPENAI_ENDPOINT": endpoint, "AZURE_OPENAI_API_KEY": "test-key-not-for-output",
        "AZURE_OPENAI_DEPLOYMENT": "test",
    })
    assert not deployments and errors
    assert "test-key-not-for-output" not in str(errors)


def test_call_budget_and_reservations():
    class FixtureCompletion:
        async def complete(self, deployment, system, prompt, on_token):
            return Completion('{"answer":"Fixture answer, not a live model response."}', {})

    async def run():
        network = LiveNetwork([
            Deployment("primary", "https://test.openai.azure.com", "model", SecretStr("test"), 1)
        ], FixtureCompletion(), "dependency", lambda kind, data: None, set())
        for index in range(12):
            await network.request("target", f"test-{index}", "Synthetic fixture task", Answer)
        with pytest.raises(ProviderError, match="12-call"):
            await network.request("target", "over-budget", "Synthetic fixture task", Answer)
        assert network.calls == 12
        assert not network.coordinator.reservations
        assert not network.coordinator.owners
        assert not any(network.coordinator.inflight.values())
    asyncio.run(run())


def test_restart_interrupts_all_stale_runs_not_only_recent_history(tmp_path):
    store = Store(tmp_path / "test.sqlite3")
    oldest = store.create(payload())
    for _ in range(101):
        run_id = store.create(payload())
        store.update(run_id, "complete", {"fixture": True})
    restarted = Store(store.path)
    restarted.interrupt_stale()
    assert restarted.get(oldest)["status"] == "interrupted"
    assert len(restarted.list()) == 100


@pytest.mark.parametrize("content_type,body,message", [
    ("application/pdf", b"%PDF-1.0", "not PDFs"),
    ("text/plain", b"x" * 1_000_001, "1 MB"),
    ("text/plain", b"Too short", "enough readable text"),
], ids=["pdf", "oversized", "insufficient-text"])
def test_source_limits(content_type, body, message):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=body,
                                               headers={"content-type": content_type}))) as client:
            with pytest.raises(SourceError, match=message):
                await fetch_source(client, "https://arxiv.org/abs/123", "S1")
    asyncio.run(run())


def test_shared_host_is_one_resource(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "AZURE_OPENAI_ENDPOINT=https://shared.openai.azure.com/openai/v1/\n"
        "AZURE_OPENAI_API_KEY=unit-test-key\nAZURE_OPENAI_DEPLOYMENT=one\n"
        "AZURE_OPENAI_BACKUP_ENDPOINT=https://shared.openai.azure.com/\n"
        "AZURE_OPENAI_BACKUP_API_KEY=unit-test-key\nAZURE_OPENAI_BACKUP_DEPLOYMENT=two\n"
    )
    deployments, errors = load_deployments(path, {})
    assert not errors
    assert len(deployments) == 2
    assert len({deployment.resource for deployment in deployments}) == 1


def test_static_application_is_light_and_does_not_require_external_assets(configured):
    client, _, _ = configured
    html = client.get("/")
    assert html.status_code == 200
    assert "Nanda Workbench" in html.text
    assert "unsafe-inline" not in html.headers["content-security-policy"]
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/app.css").status_code == 200
    assert client.get("/.env").status_code == 404


def test_invalid_event_cursor_and_unknown_run(configured):
    client, _, _ = configured
    assert client.get("/api/runs/missing").status_code == 404
    record = completed(client, payload())
    assert client.get(f"/api/runs/{record['id']}/events",
                      headers={"Last-Event-ID": "invalid"}).status_code == 400
