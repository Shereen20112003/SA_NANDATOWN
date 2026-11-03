"""Local subprocess fixtures; no coco credentials or cloud calls are used."""

import asyncio
import json
import sys

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from nanda_resilience.workbench.azure import ProviderError
from nanda_resilience.workbench.coco import CocoClient, CocoStream
from nanda_resilience.workbench.config import Deployment, load_deployments
from nanda_resilience.workbench.schemas import Answer
from nanda_resilience.workbench.server import create_app
from pydantic import ValidationError


def result(text='{"answer":"Fixture answer."}'):
    return {"type": "result", "subtype": "success", "is_error": False,
            "num_turns": 1, "stop_reason": "end_turn", "result": text,
            "usage": {"input_tokens": 10, "output_tokens": 8,
                      "cache_read_input_tokens": 3, "cache_creation_input_tokens": 2}}


def delta(text):
    return {"type": "stream_event", "event": {"type": "content_block_delta",
                                             "delta": {"type": "text_delta", "text": text}}}


def test_stream_and_cached_usage():
    tokens = []
    stream = CocoStream(tokens.append)
    stream.consume("Note: another coco daemon is running")
    stream.consume("\x1b[2mNote: another coco daemon is running\x1b[0m")
    text = result()["result"]
    stream.consume(json.dumps(delta(text)))
    stream.consume(json.dumps(result()))
    completion = stream.completion()
    assert tokens == [text]
    assert completion.text == text
    assert completion.usage == {"prompt_tokens": 15, "completion_tokens": 8, "total_tokens": 23}


@pytest.mark.parametrize("changes", [
    {"is_error": True}, {"subtype": "error_max_turns"}, {"stop_reason": "max_tokens"},
    {"num_turns": 2}, {"result": ""}, {"usage": None},
    {"usage": {"input_tokens": -1, "output_tokens": 2}},
    {"usage": {"input_tokens": True, "output_tokens": 2}},
    {"usage": {"input_tokens": 1}},
])
def test_result_validation(changes):
    stream = CocoStream(lambda text: None)
    stream.consume(json.dumps({**result(), **changes}))
    with pytest.raises(ProviderError):
        stream.completion()


@pytest.mark.parametrize("line", [
    "not-json", "[]", '{"type":"stream_event","event":[]}',
    '{"type":"stream_event","event":{"type":"content_block_delta","delta":null}}',
    json.dumps(delta(5)),
])
def test_malformed_stream(line):
    with pytest.raises(ProviderError):
        CocoStream(lambda text: None).consume(line)


def test_missing_duplicate_mismatched_results():
    stream = CocoStream(lambda text: None)
    with pytest.raises(ProviderError):
        stream.completion()
    stream.consume(json.dumps(result()))
    with pytest.raises(ProviderError, match="duplicate"):
        stream.consume(json.dumps(result()))
    mismatch = CocoStream(lambda text: None)
    mismatch.consume(json.dumps(delta("different")))
    mismatch.consume(json.dumps(result()))
    with pytest.raises(ProviderError, match="match"):
        mismatch.completion()


def test_output_limit():
    with pytest.raises(ProviderError, match="limit"):
        CocoStream(lambda text: None).consume(json.dumps(delta("a" * 50001)))


def test_fenced_json_preserves_raw_evidence_and_validates_the_payload():
    tokens = []
    raw = '```json\n{"answer":"Fixture answer."}\n```'
    stream = CocoStream(tokens.append)
    stream.consume(json.dumps(delta(raw)))
    stream.consume(json.dumps(result(raw)))
    completion = stream.completion()
    assert Answer.model_validate_json(completion.text).answer == "Fixture answer."
    assert tokens == [raw]


@pytest.mark.parametrize("text", [
    'Some prose\n```json\n{"answer":"Fixture."}\n```',
    '```json\n{"answer":"Fixture."}\n```\nExtra prose',
    '```json\n{"wrong_field":"Fixture."}\n```',
])
def test_fence_handling_does_not_accept_prose_or_wrong_schema(text):
    stream = CocoStream(lambda text: None)
    stream.consume(json.dumps(result(text)))
    with pytest.raises(ValidationError):
        Answer.model_validate_json(stream.completion().text)


def test_coco_configuration_does_not_require_or_expose_cloud_keys(tmp_path):
    deployments, errors = load_deployments(tmp_path / "absent", {
        "WORKBENCH_PROVIDER": "coco", "COCO_MODEL": "claude-haiku-4-5",
        "COCO_EXECUTABLE": sys.executable,
        "AZURE_OPENAI_API_KEY": "test-key-not-for-coco",
    })
    assert not errors
    assert len(deployments) == 1
    deployment = deployments[0]
    assert deployment.provider == "coco"
    assert deployment.resource == "copilot-via-coco"
    assert deployment.key.get_secret_value() == ""
    assert "test-key" not in json.dumps(deployment.public())
    assert "executable" not in deployment.public()


@pytest.mark.parametrize("overrides", [
    {"WORKBENCH_PROVIDER": "other"}, {"COCO_MODEL": ""},
    {"COCO_MODEL": "--bad-model"}, {"COCO_EXECUTABLE": "missing-executable"},
])
def test_invalid_configuration(tmp_path, overrides):
    deployments, errors = load_deployments(tmp_path / "absent", {
        "WORKBENCH_PROVIDER": "coco", "COCO_MODEL": "test-model",
        "COCO_EXECUTABLE": sys.executable, **overrides,
    })
    assert not deployments and errors


@pytest.fixture
def fake_cli(monkeypatch):
    real_spawn = asyncio.create_subprocess_exec
    launches = []
    processes = []

    def install(script):
        async def spawn(*args, **kwargs):
            if args[0] == "taskkill":
                return await real_spawn(*args, **kwargs)
            launches.append((args, kwargs))
            process = await real_spawn(sys.executable, "-c", script, **kwargs)
            processes.append(process)
            return process
        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)

    return install, launches, processes


def deployment():
    return Deployment("primary", "", "test-model", SecretStr(""), 1, "coco", sys.executable)


def test_subprocess_isolation_streaming_and_stdin(tmp_path, fake_cli, monkeypatch):
    install, launches, _ = fake_cli
    monkeypatch.setenv("ANTHROPIC_API_KEY", "never-send-this")
    install(
        "import sys,json; prompt=sys.stdin.read(); assert prompt=='synthetic task'; "
        f"print({json.dumps(delta(result()['result']))!r},flush=True); "
        f"print({json.dumps(result())!r},flush=True)"
    )
    tokens = []
    completion = asyncio.run(CocoClient(tmp_path).complete(
        deployment(), "system fixture", "synthetic task", tokens.append))
    assert completion.text == result()["result"]
    assert tokens == [result()["result"]]
    args, kwargs = launches[0]
    assert args[args.index("--tools") + 1] == ""
    assert args[args.index("--mcp-config") + 1] == '{"mcpServers":{}}'
    assert args[args.index("--max-turns") + 1] == "1"
    assert {"--bare", "--no-session-persistence", "--strict-mcp-config"} <= set(args)
    assert "synthetic task" not in args
    assert kwargs["cwd"] == tmp_path
    assert "ANTHROPIC_API_KEY" not in kwargs["env"]
    assert kwargs["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "2200"


@pytest.mark.parametrize("script", [
    "import sys; sys.stdin.read(); sys.stderr.write('private-test-token'); sys.exit(7)",
    "import sys; sys.stdin.read(); print('private-test-token')",
    "import sys; sys.stdin.read()",
])
def test_cli_failures_are_explicit_without_diagnostic_secrets(tmp_path, fake_cli, script):
    install, _, _ = fake_cli
    install(script)
    with pytest.raises(ProviderError) as error:
        asyncio.run(CocoClient(tmp_path).complete(
            deployment(), "fixture", "synthetic task", lambda text: None))
    assert "private-test-token" not in str(error.value)


def test_cli_timeout_reaps_process(tmp_path, fake_cli):
    install, _, processes = fake_cli
    install("import time; time.sleep(30)")
    with pytest.raises(ProviderError, match="timed out"):
        asyncio.run(CocoClient(tmp_path, timeout=0.15).complete(
            deployment(), "fixture", "synthetic task", lambda text: None))
    assert processes[0].returncode is not None


def test_cli_cancel_reaps_process(tmp_path, fake_cli):
    install, _, processes = fake_cli
    install("import time; time.sleep(30)")

    async def run():
        task = asyncio.create_task(CocoClient(tmp_path).complete(
            deployment(), "fixture", "synthetic task", lambda text: None))
        while not processes:
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert processes[0].returncode is not None
    asyncio.run(run())


def test_coco_api_runs_real_subprocess_fixture_and_resource_fault(tmp_path, fake_cli):
    install, launches, _ = fake_cli
    install(
        "import sys; sys.stdin.read(); "
        f"print({json.dumps(delta(result()['result']))!r},flush=True); "
        f"print({json.dumps(result())!r},flush=True)"
    )
    env = tmp_path / ".env"
    env.write_text(f"WORKBENCH_PROVIDER=coco\nCOCO_MODEL=test-model\nCOCO_EXECUTABLE={sys.executable}\n")
    app = create_app(env, tmp_path / "state", httpx.MockTransport(
        lambda request: httpx.Response(200, text="Public fixture source text. " * 20,
                                       headers={"content-type": "text/plain"})))
    body = {"mode": "research", "question": "Explain the fixture source text.",
            "sources": ["https://arxiv.org/abs/123"], "consent": True}
    with TestClient(app) as client:
        status = client.get("/api/status").json()
        assert status["configured"] and status["provider"] == "coco"
        assert not status["can_failover"]
        run_id = client.post("/api/runs", json=body).json()["id"]
        events = client.get(f"/api/runs/{run_id}/events")
        assert "event: finished" in events.text
        record = client.get(f"/api/runs/{run_id}").json()
        # A valid Answer is still invalid SourceNotes: no fabricated successful brief.
        assert record["status"] == "failed"
        assert "schema" in record["error"]
        assert record["result"]["partial"]["provider"] == "coco"
        assert record["result"]["partial"]["model_calls"] == 1
        assert len(launches) == 1
        assert client.post("/api/resources", json={
            "resource": "copilot-via-coco", "disabled": True}).status_code == 200
        paused_id = client.post("/api/runs", json=body).json()["id"]
        client.get(f"/api/runs/{paused_id}/events")
        paused = client.get(f"/api/runs/{paused_id}").json()
        assert paused["status"] == "failed"
        assert paused["result"]["partial"]["model_calls"] == 0
        assert len(launches) == 1
