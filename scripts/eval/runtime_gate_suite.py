from __future__ import annotations

import argparse
import base64
import contextlib
import json
import socket
import sys
import tempfile
import time
import tracemalloc
import zlib
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if SRC_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, SRC_ROOT.as_posix())

from fink import ingest as INGEST  # noqa: E402
from fink import schemas as SCHEMAS  # noqa: E402


TASK_ID = "FINK-S5-06"
SUITE_ID = "runtime_gate_suite"
RESULT_LOG_PATH = Path(__file__).with_name("runtime_gate_suite_results.json")
PAPER_SECTIONS = (
    "05_experiments.md",
    "06_results.md",
    "08_responsible_ai.md",
)
REGISTERED_GATE_IDS = (
    "offline_integration_test",
    "privacy_redaction_test",
    "latency_memory_run",
)
METRIC_IDS = ("EV-LAT", "EV-MEM", "EV-OFFLINE", "EV-PRIV")

SYNTHETIC_PDF_FILENAME = "creator-contract-upload.pdf"
SYNTHETIC_PASTE_FILENAME = "paste.txt"
SYNTHETIC_CONTRACT_TEXT = (
    "SYNTHETIC_PRIVATE_CONTRACT_MARKER gross sales 1,200,000 KRW "
    "revenue share 30% payment due 45 days"
)
SYNTHETIC_OCR_TEXT = (
    "SYNTHETIC_PRIVATE_OCR_MARKER gross sales 900,000 KRW "
    "revenue share 25% payment due 30 days"
)
PRIVATE_MARKERS_FOR_TESTS = (
    SYNTHETIC_CONTRACT_TEXT,
    SYNTHETIC_OCR_TEXT,
    SYNTHETIC_PDF_FILENAME,
    "SYNTHETIC_PRIVATE_CONTRACT_MARKER",
    "SYNTHETIC_PRIVATE_OCR_MARKER",
)


@dataclass(frozen=True)
class RuntimeObservation:
    input_mode: str
    accepted: bool
    page_count: int
    extracted_term_count: int
    workspace_removed: bool
    stored_artifact_removed: bool
    log_surfaces: tuple[str, ...]
    private_markers: tuple[str, ...]


@dataclass(frozen=True)
class Measurement:
    label: str
    latency_seconds: float
    peak_memory_bytes: int
    observation: RuntimeObservation


@dataclass
class NetworkBlocker:
    attempts: int = 0

    @contextlib.contextmanager
    def block(self) -> Iterator[None]:
        def blocked_connect(_sock: socket.socket, _address: object) -> None:
            self.attempts += 1
            raise RuntimeError("network access blocked")

        def blocked_connect_ex(_sock: socket.socket, _address: object) -> int:
            self.attempts += 1
            raise RuntimeError("network access blocked")

        def blocked_create_connection(*_args: object, **_kwargs: object) -> socket.socket:
            self.attempts += 1
            raise RuntimeError("network access blocked")

        with (
            patch.object(socket.socket, "connect", blocked_connect),
            patch.object(socket.socket, "connect_ex", blocked_connect_ex),
            patch.object(socket, "create_connection", blocked_create_connection),
        ):
            yield


def run_runtime_gate_suite() -> dict[str, Any]:
    blocker = NetworkBlocker()
    runtime_error: str | None = None
    measurements: list[Measurement] = []

    with tempfile.TemporaryDirectory(prefix="fink-s5-06-") as tmp:
        tmpdir = Path(tmp)
        upload_root = tmpdir / "uploads"
        pdf_path = tmpdir / SYNTHETIC_PDF_FILENAME
        pdf_path.write_bytes(
            _pdf_bytes(
                (SYNTHETIC_CONTRACT_TEXT, None),
                ocr_hints=("", SYNTHETIC_OCR_TEXT),
                flate_pages={0},
            )
        )

        try:
            with blocker.block():
                measurements.append(
                    _measure(
                        "pdf_pipeline",
                        lambda: _run_pdf_pipeline(upload_root, pdf_path),
                    )
                )
                measurements.append(
                    _measure(
                        "paste_pipeline",
                        lambda: _run_paste_pipeline(upload_root, SYNTHETIC_CONTRACT_TEXT),
                    )
                )
        except Exception as exc:  # pragma: no cover - exercised only on gate failure.
            runtime_error = type(exc).__name__

    observations = tuple(measurement.observation for measurement in measurements)
    cases = [
        _offline_case(blocker, observations, runtime_error),
        _privacy_case(observations),
        _latency_memory_case(measurements),
    ]
    passed = sum(1 for case in cases if case["status"] == "PASS")
    failed = len(cases) - passed
    return {
        "suite": SUITE_ID,
        "task_id": TASK_ID,
        "paper_sections": list(PAPER_SECTIONS),
        "registered_gates": list(REGISTERED_GATE_IDS),
        "metrics": {
            "EV-OFFLINE": _metric_status(cases, "EV-OFFLINE"),
            "EV-PRIV": _metric_status(cases, "EV-PRIV"),
            "EV-LAT": _metric_status(cases, "EV-LAT"),
            "EV-MEM": _metric_status(cases, "EV-MEM"),
        },
        "summary": {
            "total": len(cases),
            "passed": passed,
            "failed": failed,
            "ok": failed == 0,
        },
        "cases": cases,
    }


def write_result_log(result: Mapping[str, Any], path: Path | str = RESULT_LOG_PATH) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def _run_pdf_pipeline(upload_root: Path, pdf_path: Path) -> RuntimeObservation:
    with INGEST.EphemeralIngestSession(upload_root=upload_root) as session:
        ingested = session.ingest_pdf(
            pdf_path,
            original_filename=SYNTHETIC_PDF_FILENAME,
            content_type="application/pdf",
        )
        report = ingested.build_report()
        workspace = session.workspace
        stored_path = ingested.stored_path
        derived_paths = tuple(ingested.derived_paths)
        log_surfaces = _log_surfaces(ingested, report)
        accepted = ingested.document is not None and (
            ingested.document.validation_status is SCHEMAS.ValidationStatus.ACCEPTED
        )
        page_count = ingested.document.page_count if ingested.document is not None else 0
        private_markers = (
            SYNTHETIC_CONTRACT_TEXT,
            SYNTHETIC_OCR_TEXT,
            SYNTHETIC_PDF_FILENAME,
            pdf_path.as_posix(),
            workspace.as_posix(),
            *((path.as_posix() for path in derived_paths)),
            *((stored_path.as_posix(),) if stored_path is not None else ()),
        )

    return RuntimeObservation(
        input_mode="pdf",
        accepted=accepted,
        page_count=page_count,
        extracted_term_count=len(ingested.extracted_terms),
        workspace_removed=not workspace.exists(),
        stored_artifact_removed=_all_removed(stored_path, *derived_paths),
        log_surfaces=log_surfaces,
        private_markers=private_markers,
    )


def _run_paste_pipeline(upload_root: Path, text: str) -> RuntimeObservation:
    with INGEST.EphemeralIngestSession(upload_root=upload_root) as session:
        ingested = session.ingest_paste(text)
        report = ingested.build_report()
        workspace = session.workspace
        stored_path = ingested.stored_path
        log_surfaces = _log_surfaces(ingested, report)
        private_markers = (
            text,
            "SYNTHETIC_PRIVATE_CONTRACT_MARKER",
            SYNTHETIC_PASTE_FILENAME,
            workspace.as_posix(),
            *((stored_path.as_posix(),) if stored_path is not None else ()),
        )

    return RuntimeObservation(
        input_mode="paste",
        accepted=True,
        page_count=0,
        extracted_term_count=len(ingested.extracted_terms),
        workspace_removed=not workspace.exists(),
        stored_artifact_removed=_all_removed(stored_path),
        log_surfaces=log_surfaces,
        private_markers=private_markers,
    )


def _measure(label: str, fn: Callable[[], RuntimeObservation]) -> Measurement:
    tracemalloc.start()
    started = time.perf_counter()
    try:
        observation = fn()
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        elapsed = time.perf_counter() - started
        tracemalloc.stop()
    return Measurement(
        label=label,
        latency_seconds=elapsed,
        peak_memory_bytes=peak,
        observation=observation,
    )


def _offline_case(
    blocker: NetworkBlocker,
    observations: Sequence[RuntimeObservation],
    runtime_error: str | None,
) -> dict[str, Any]:
    observed = {
        "network_attempts": blocker.attempts,
        "runtime_error": runtime_error,
        "accepted_runs": sum(1 for item in observations if item.accepted),
        "workspace_removed_runs": sum(1 for item in observations if item.workspace_removed),
        "stored_artifact_removed_runs": sum(
            1 for item in observations if item.stored_artifact_removed
        ),
    }
    expected = {
        "network_attempts": 0,
        "runtime_error": None,
        "accepted_runs": 2,
        "workspace_removed_runs": 2,
        "stored_artifact_removed_runs": 2,
    }
    return {
        "id": "offline_integration_test",
        "metrics": ["EV-OFFLINE"],
        "description": "Synthetic PDF and paste runs complete with socket connection APIs blocked.",
        "status": "PASS" if observed == expected else "FAIL",
        "tolerance": "exact",
        "expected": expected,
        "observed": observed,
    }


def _privacy_case(observations: Sequence[RuntimeObservation]) -> dict[str, Any]:
    findings = _privacy_findings(observations)
    observed = {
        "surface_count": sum(len(item.log_surfaces) for item in observations),
        "leak_count": len(findings),
        "leak_types": sorted({finding["kind"] for finding in findings}),
        "input_modes": [item.input_mode for item in observations],
    }
    expected = {
        "leak_count": 0,
        "input_modes": ["pdf", "paste"],
    }
    ok = observed["leak_count"] == 0 and observed["input_modes"] == expected["input_modes"]
    return {
        "id": "privacy_redaction_test",
        "metrics": ["EV-PRIV"],
        "description": (
            "Log/export surfaces omit synthetic contract text, raw filenames, and temp paths."
        ),
        "status": "PASS" if ok else "FAIL",
        "tolerance": "exact",
        "expected": expected,
        "observed": observed,
    }


def _latency_memory_case(measurements: Sequence[Measurement]) -> dict[str, Any]:
    per_run = [
        {
            "label": item.label,
            "latency_seconds": round(item.latency_seconds, 9),
            "peak_memory_bytes": item.peak_memory_bytes,
            "input_mode": item.observation.input_mode,
            "page_count": item.observation.page_count,
            "extracted_term_count": item.observation.extracted_term_count,
        }
        for item in measurements
    ]
    latency_values = [item.latency_seconds for item in measurements]
    memory_values = [item.peak_memory_bytes for item in measurements]
    observed = {
        "measured_runs": len(measurements),
        "max_latency_seconds": round(max(latency_values, default=0.0), 9),
        "max_peak_memory_bytes": max(memory_values, default=0),
        "per_run": per_run,
    }
    ok = (
        observed["measured_runs"] == 2
        and all(value >= 0.0 for value in latency_values)
        and all(value > 0 for value in memory_values)
    )
    return {
        "id": "latency_memory_run",
        "metrics": ["EV-LAT", "EV-MEM"],
        "description": "Synthetic local runs record wall-clock latency and peak Python allocation.",
        "status": "PASS" if ok else "FAIL",
        "tolerance": "measurement present; no performance threshold asserted",
        "expected": {
            "measured_runs": 2,
            "latency_seconds": "present",
            "peak_memory_bytes": "present",
        },
        "observed": observed,
    }


def _privacy_findings(observations: Sequence[RuntimeObservation]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for observation in observations:
        surfaces = "\n".join(observation.log_surfaces)
        for marker in observation.private_markers:
            if marker and marker in surfaces:
                findings.append({"input_mode": observation.input_mode, "kind": "private_marker"})
        if "/tmp/" in surfaces or "\\AppData\\" in surfaces:
            findings.append({"input_mode": observation.input_mode, "kind": "temp_path"})
    return findings


def _metric_status(cases: Sequence[Mapping[str, Any]], metric_id: str) -> dict[str, Any]:
    metric_cases = [case for case in cases if metric_id in case["metrics"]]
    passed = sum(1 for case in metric_cases if case["status"] == "PASS")
    failed = len(metric_cases) - passed
    return {
        "total": len(metric_cases),
        "passed": passed,
        "failed": failed,
        "ok": failed == 0,
    }


def _log_surfaces(ingested: Any, report: Any) -> tuple[str, ...]:
    return (
        _json_surface(ingested.to_log_record()),
        _json_surface(ingested.request.to_log_dict()),
        _json_surface(report.to_log_dict()),
    )


def _json_surface(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _all_removed(*paths: Path | None) -> bool:
    return all(path is None or not path.exists() for path in paths)


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _hint(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")


def _pdf_bytes(
    page_texts: Sequence[str | None],
    *,
    ocr_hints: Sequence[str] | None = None,
    flate_pages: set[int] | None = None,
) -> bytes:
    hints = tuple(ocr_hints or ())
    flated = flate_pages or set()
    object_chunks = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
    ]
    kids: list[str] = []
    for idx, text in enumerate(page_texts):
        page_obj = 3 + idx * 2
        content_obj = page_obj + 1
        kids.append(f"{page_obj} 0 R")
        object_chunks.append(
            (
                f"{page_obj} 0 obj\n"
                f"<< /Type /Page /Parent 2 0 R /Contents {content_obj} 0 R >>\n"
                f"endobj\n"
            ).encode("ascii")
        )
        if text is None:
            stream = b"q\n/Im0 Do\nQ"
        else:
            stream = f"BT ({_pdf_escape(text)}) Tj ET".encode("utf-8")
        if idx in flated:
            stream = zlib.compress(stream)
            header = (
                f"{content_obj} 0 obj\n"
                f"<< /Length {len(stream)} /Filter /FlateDecode >>\n"
            )
        else:
            header = f"{content_obj} 0 obj\n<< /Length {len(stream)} >>\n"
        object_chunks.append(
            header.encode("ascii")
            + b"stream\n"
            + stream
            + b"\nendstream\nendobj\n"
        )

    pages_obj = (
        f"2 0 obj\n<< /Type /Pages /Count {len(page_texts)} "
        f"/Kids [{' '.join(kids)}] >>\nendobj\n"
    ).encode("ascii")
    comments = b""
    for idx, text in enumerate(hints):
        if text:
            comments += f"% FINK-OCR-HINT page={idx} text={_hint(text)}\n".encode("ascii")
    return b"%PDF-1.4\n" + pages_obj + b"".join(object_chunks) + comments + b"%%EOF\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run FINK-S5-06 runtime gate suite.")
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULT_LOG_PATH,
        help="Path for the JSON result log.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Also print the JSON result to stdout.",
    )
    args = parser.parse_args(argv)

    result = run_runtime_gate_suite()
    log_path = write_result_log(result, args.output)
    if args.stdout:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"{SUITE_ID}: {'PASS' if result['summary']['ok'] else 'FAIL'}; log={log_path}")
    return 0 if result["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
