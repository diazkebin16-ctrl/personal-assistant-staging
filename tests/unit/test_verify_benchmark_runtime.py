"""Offline-only tests for the Railway runtime benchmark verifier."""

import asyncio
import json
from pathlib import Path

from backend.app.ai_router.benchmark_store import (
    BenchmarkResultStore,
    CheckpointState,
)
from scripts import verify_benchmark_runtime as verifier


def test_complete_persists_fake_provider_result(tmp_path: Path) -> None:
    assert asyncio.run(verifier._run_complete(tmp_path, "runtime-complete")) == 0
    document = BenchmarkResultStore(tmp_path).load("runtime-complete")
    assert document.aggregates.attempted_calls == 1
    assert document.aggregates.finished_calls == 1
    assert document.aggregates.completed_calls == 1
    call = document.calls[0]
    assert call.case_id == "greeting"
    assert call.requested_model == "gpt-5-nano"
    assert call.reported_model == "gpt-5-nano"
    assert call.output_text == "FAKE_PROVIDER_OK"
    assert call.input_tokens == 12
    assert call.cached_input_tokens == 4
    assert call.output_tokens == 3
    assert call.reasoning_tokens == 0


def test_complete_result_contains_no_prompt_or_credentials(tmp_path: Path) -> None:
    assert asyncio.run(verifier._run_complete(tmp_path, "runtime-private")) == 0
    raw = (tmp_path / "runtime-private" / "result.json").read_text(encoding="utf-8")
    assert "Hola, ¿cómo estás?" not in raw
    assert "OPENAI_API_KEY" not in raw
    assert "api_key" not in raw
    assert "credential" not in raw
    assert "secret" not in raw


def test_crash_persists_finished_and_in_progress_records(tmp_path: Path) -> None:
    assert asyncio.run(verifier._run_crash(tmp_path, "runtime-crash")) == 0
    document = BenchmarkResultStore(tmp_path).load("runtime-crash")
    assert document.aggregates.attempted_calls == 2
    assert document.aggregates.finished_calls == 1
    assert document.calls[0].checkpoint_state is CheckpointState.FINISHED
    assert document.calls[0].case_id == "greeting"
    assert document.calls[1].checkpoint_state is CheckpointState.IN_PROGRESS
    assert document.calls[1].case_id == "simple_fact"


def test_resume_refuses_ambiguous_checkpoint_without_provider_call(
    tmp_path: Path,
) -> None:
    assert asyncio.run(verifier._run_crash(tmp_path, "runtime-resume")) == 0
    before = (tmp_path / "runtime-resume" / "result.json").read_bytes()
    assert verifier._run_resume(tmp_path, "runtime-resume") == 0
    after = (tmp_path / "runtime-resume" / "result.json").read_bytes()
    assert after == before


def test_two_runtime_run_ids_are_isolated(tmp_path: Path) -> None:
    assert asyncio.run(verifier._run_complete(tmp_path, "runtime-a")) == 0
    assert asyncio.run(verifier._run_complete(tmp_path, "runtime-b")) == 0
    first = BenchmarkResultStore(tmp_path).load("runtime-a")
    second = BenchmarkResultStore(tmp_path).load("runtime-b")
    assert first.benchmark_run_id == "runtime-a"
    assert second.benchmark_run_id == "runtime-b"


def test_resume_missing_or_corrupt_state_fails_closed(tmp_path: Path) -> None:
    assert verifier._run_resume(tmp_path, "missing-run") == 2
    corrupt_dir = tmp_path / "corrupt-run"
    corrupt_dir.mkdir()
    (corrupt_dir / "result.json").write_text("{partial", encoding="utf-8")
    assert verifier._run_resume(tmp_path, "corrupt-run") == 2


def test_runtime_harness_has_no_model_credential_dependency() -> None:
    source = Path(verifier.__file__).read_text(encoding="utf-8")
    assert "get_settings" not in source
    assert "OpenAIProvider" not in source
    assert "OPENAI_API_KEY" not in source
    assert "FakeProvider" in source


def test_persisted_payload_is_structured_and_recoverable(tmp_path: Path) -> None:
    assert asyncio.run(verifier._run_complete(tmp_path, "runtime-json")) == 0
    payload = json.loads((tmp_path / "runtime-json" / "result.json").read_text(encoding="utf-8"))
    assert payload["benchmark_run_id"] == "runtime-json"
    assert payload["aggregates"]["attempted_calls"] == 1
    assert payload["calls"][0]["checkpoint_state"] == "finished"
