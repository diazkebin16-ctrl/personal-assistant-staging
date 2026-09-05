"""Durable, privacy-minimal checkpoint storage for internal Nano/Luna benchmarks."""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.app.ai_router.diagnostics import ProviderResponseStatus

BENCHMARK_SCHEMA_VERSION = 1
BENCHMARK_VERSION = "nano-luna-observability-v1"
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class BenchmarkStoreError(RuntimeError):
    """Fail-closed error for unsafe, missing, or corrupt benchmark state."""


class CheckpointState(StrEnum):
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"


class BenchmarkCallRecord(BaseModel):
    """One privacy-minimal benchmark call checkpoint; prompts and credentials are excluded."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    benchmark_run_id: str = Field(min_length=1, max_length=64)
    case_id: str = Field(min_length=1, max_length=128)
    requested_model: str = Field(min_length=1, max_length=128)
    reported_model: str | None = Field(default=None, max_length=128)
    checkpoint_state: CheckpointState
    normalized_status: ProviderResponseStatus | None = None
    incomplete_reason: str | None = Field(default=None, max_length=128)
    succeeded: bool | None = None
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    estimated_cost_microunits: int = Field(default=0, ge=0)
    output_text: str | None = Field(default=None, max_length=1_000_000)
    failure_category: str | None = Field(default=None, max_length=128)
    timestamp: datetime

    @model_validator(mode="after")
    def validate_checkpoint_shape(self) -> "BenchmarkCallRecord":
        if not _RUN_ID_PATTERN.fullmatch(self.benchmark_run_id):
            raise ValueError("Invalid benchmark_run_id")
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("Cached input tokens cannot exceed total input tokens")
        if self.reasoning_tokens > self.output_tokens:
            raise ValueError("Reasoning tokens cannot exceed total output tokens")
        if self.checkpoint_state is CheckpointState.IN_PROGRESS:
            if self.normalized_status is not None or self.succeeded is not None:
                raise ValueError("In-progress checkpoints cannot contain an outcome")
            if any(
                (
                    self.reported_model,
                    self.incomplete_reason,
                    self.output_text,
                    self.failure_category,
                )
            ):
                raise ValueError("In-progress checkpoints cannot contain response metadata")
            if any(
                (
                    self.input_tokens,
                    self.cached_input_tokens,
                    self.output_tokens,
                    self.reasoning_tokens,
                    self.latency_ms,
                    self.estimated_cost_microunits,
                )
            ):
                raise ValueError("In-progress checkpoints cannot contain usage metadata")
            return self

        if self.normalized_status is None or self.succeeded is None:
            raise ValueError("Finished checkpoints require normalized status and succeeded")
        if self.succeeded is not (self.normalized_status is ProviderResponseStatus.COMPLETED):
            raise ValueError("succeeded must match completed status")
        if (
            self.normalized_status is ProviderResponseStatus.INCOMPLETE
            and not self.incomplete_reason
        ):
            raise ValueError("Incomplete results require incomplete_reason")
        if self.normalized_status is ProviderResponseStatus.COMPLETED and not self.output_text:
            raise ValueError("Completed results require visible output")
        return self

    @property
    def key(self) -> tuple[str, str]:
        return (self.case_id, self.requested_model)


class BenchmarkAggregates(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    attempted_calls: int = Field(ge=0)
    finished_calls: int = Field(ge=0)
    completed_calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    estimated_cost_microunits: int = Field(ge=0)

    @classmethod
    def from_calls(cls, calls: tuple[BenchmarkCallRecord, ...]) -> "BenchmarkAggregates":
        finished = tuple(call for call in calls if call.checkpoint_state is CheckpointState.FINISHED)
        completed = tuple(
            call
            for call in finished
            if call.normalized_status is ProviderResponseStatus.COMPLETED
        )
        return cls(
            attempted_calls=len(calls),
            finished_calls=len(finished),
            completed_calls=len(completed),
            input_tokens=sum(call.input_tokens for call in finished),
            cached_input_tokens=sum(call.cached_input_tokens for call in finished),
            output_tokens=sum(call.output_tokens for call in finished),
            reasoning_tokens=sum(call.reasoning_tokens for call in finished),
            latency_ms=sum(call.latency_ms for call in finished),
            estimated_cost_microunits=sum(
                call.estimated_cost_microunits for call in finished
            ),
        )


class BenchmarkRunDocument(BaseModel):
    """Atomic run document suitable for checkpoint/recovery and later scoring."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = BENCHMARK_SCHEMA_VERSION
    benchmark_version: str = BENCHMARK_VERSION
    benchmark_run_id: str = Field(min_length=1, max_length=64)
    created_at: datetime
    updated_at: datetime
    calls: tuple[BenchmarkCallRecord, ...] = ()
    aggregates: BenchmarkAggregates

    @model_validator(mode="after")
    def validate_run(self) -> "BenchmarkRunDocument":
        if not _RUN_ID_PATTERN.fullmatch(self.benchmark_run_id):
            raise ValueError("Invalid benchmark_run_id")
        keys: set[tuple[str, str]] = set()
        for call in self.calls:
            if call.benchmark_run_id != self.benchmark_run_id:
                raise ValueError("Call belongs to a different benchmark run")
            if call.key in keys:
                raise ValueError("Duplicate case/model record in benchmark run")
            keys.add(call.key)
        if self.aggregates != BenchmarkAggregates.from_calls(self.calls):
            raise ValueError("Benchmark aggregates do not match call records")
        return self

    @classmethod
    def empty(cls, run_id: str, *, now: datetime | None = None) -> "BenchmarkRunDocument":
        timestamp = now or datetime.now(UTC)
        return cls(
            benchmark_run_id=run_id,
            created_at=timestamp,
            updated_at=timestamp,
            aggregates=BenchmarkAggregates.from_calls(()),
        )

    def record_for(self, case_id: str, requested_model: str) -> BenchmarkCallRecord | None:
        return next(
            (
                call
                for call in self.calls
                if call.case_id == case_id and call.requested_model == requested_model
            ),
            None,
        )


class BenchmarkResultStore:
    """One-file-per-run store using fsync + atomic replace after every checkpoint."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def create(self, run_id: str) -> BenchmarkRunDocument:
        path = self._result_path(run_id)
        if path.exists():
            raise BenchmarkStoreError("Benchmark run already exists; use --resume")
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=False)
        document = BenchmarkRunDocument.empty(run_id)
        self._atomic_write(path, document)
        return document

    def load(self, run_id: str) -> BenchmarkRunDocument:
        path = self._result_path(run_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            document = BenchmarkRunDocument.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise BenchmarkStoreError("Benchmark checkpoint is missing or corrupt") from exc
        if document.benchmark_run_id != run_id:
            raise BenchmarkStoreError("Benchmark run identity mismatch")
        return document

    def checkpoint(
        self,
        document: BenchmarkRunDocument,
        record: BenchmarkCallRecord,
    ) -> BenchmarkRunDocument:
        if record.benchmark_run_id != document.benchmark_run_id:
            raise BenchmarkStoreError("Cannot mix benchmark run identities")

        calls = list(document.calls)
        existing_index = next(
            (index for index, call in enumerate(calls) if call.key == record.key),
            None,
        )
        if existing_index is None:
            if record.checkpoint_state is not CheckpointState.IN_PROGRESS:
                raise BenchmarkStoreError("A call must be checkpointed before provider invocation")
            calls.append(record)
        else:
            existing = calls[existing_index]
            if existing.checkpoint_state is CheckpointState.FINISHED:
                raise BenchmarkStoreError("Finished benchmark calls are immutable")
            if record.checkpoint_state is not CheckpointState.FINISHED:
                raise BenchmarkStoreError("Duplicate in-progress checkpoint")
            calls[existing_index] = record

        call_tuple = tuple(calls)
        updated = document.model_copy(
            update={
                "updated_at": datetime.now(UTC),
                "calls": call_tuple,
                "aggregates": BenchmarkAggregates.from_calls(call_tuple),
            }
        )
        updated = BenchmarkRunDocument.model_validate(updated.model_dump(mode="python"))
        self._atomic_write(self._result_path(document.benchmark_run_id), updated)
        return updated

    def _result_path(self, run_id: str) -> Path:
        if not _RUN_ID_PATTERN.fullmatch(run_id):
            raise BenchmarkStoreError("Invalid benchmark run id")
        return self.root / run_id / "result.json"

    @staticmethod
    def _atomic_write(path: Path, document: BenchmarkRunDocument) -> None:
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        payload = json.dumps(
            document.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
        try:
            with temporary.open("xb") as handle:
                os.chmod(temporary, 0o600)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
