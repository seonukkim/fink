#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
from copy import deepcopy
from typing import Any

from scripts.agent_loop._common import (
    BACKLOG_PATH,
    REPO_ROOT,
    STATE_PATH,
    current_commit,
    dump_yaml,
    icml_template_hashes,
    load_backlog,
    load_human_gates,
    load_state,
    load_yaml,
    now_utc,
    select_eligible_task,
    sha256_file,
    write_json,
    write_text,
)

MODEL_TASKS: list[dict[str, Any]] = [
    {
        "id": "FINK-MR-01",
        "phase": "MR",
        "priority": "P1",
        "depends_on": [],
        "scope": "S",
        "allowed_paths": ["docs/model-card.md", "configs/models/", "scripts/model_research/"],
        "description": "Record hardware and software inventory for local model research.",
        "acceptance_criteria": [
            "Inventory records CPU, memory, GPU, OS, Python, and local runtime constraints."
        ],
        "machine_gates": ["model_research_metadata_parse"],
        "paper_sections": ["04_data_and_implementation.md"],
        "human_gate": None,
        "status": "READY",
    },
    {
        "id": "FINK-MR-02",
        "phase": "MR",
        "priority": "P1",
        "depends_on": ["FINK-MR-01"],
        "scope": "M",
        "allowed_paths": ["configs/models/", "docs/model-card.md", "scripts/model_research/"],
        "description": (
            "Inventory Hugging Face metadata, licenses, gated status, and exact revisions."
        ),
        "acceptance_criteria": [
            "Every candidate has metadata, license, gated status, and pinned revision."
        ],
        "machine_gates": ["open_license_policy_check"],
        "paper_sections": ["04_data_and_implementation.md"],
        "human_gate": "MODEL_METADATA_NETWORK_APPROVED",
        "status": "READY",
    },
    {
        "id": "FINK-MR-03",
        "phase": "MR",
        "priority": "P1",
        "depends_on": ["FINK-MR-02"],
        "scope": "S",
        "allowed_paths": ["configs/models/", "docs/model-card.md", "scripts/model_research/"],
        "description": "Record download-size dry runs without downloading weights.",
        "acceptance_criteria": [
            "Dry-run records exact revisions and estimated disk size; no model weights enter Git."
        ],
        "machine_gates": ["model_size_dry_run_records"],
        "paper_sections": ["04_data_and_implementation.md"],
        "human_gate": "MODEL_METADATA_NETWORK_APPROVED",
        "status": "READY",
    },
    {
        "id": "FINK-MR-04",
        "phase": "MR",
        "priority": "P1",
        "depends_on": ["FINK-MR-03"],
        "scope": "S",
        "allowed_paths": ["configs/models/", "docs/model-card.md"],
        "description": "Produce an open-license filtered shortlist using the public_open floor.",
        "acceptance_criteria": [
            "Unknown, missing, gated, custom, noncommercial, and research-only licenses are "
            "rejected by default."
        ],
        "machine_gates": ["open_license_shortlist"],
        "paper_sections": ["04_data_and_implementation.md"],
        "human_gate": "MODEL_LICENSES_APPROVED",
        "status": "READY",
    },
    {
        "id": "FINK-MR-05",
        "phase": "MR",
        "priority": "P1",
        "depends_on": ["FINK-MR-04"],
        "scope": "M",
        "allowed_paths": ["docs/model-card.md", "scripts/model_research/"],
        "description": "Download selected private model weights only after human approval.",
        "acceptance_criteria": [
            "Weights are stored under PRIVATE_ROOT/models or Hugging Face cache, never Git."
        ],
        "machine_gates": ["model_weight_tracking_scan"],
        "paper_sections": ["04_data_and_implementation.md"],
        "human_gate": "MODEL_DOWNLOAD_APPROVED",
        "status": "READY",
    },
    {
        "id": "FINK-MR-06",
        "phase": "MR",
        "priority": "P1",
        "depends_on": ["FINK-MR-05"],
        "scope": "M",
        "allowed_paths": ["docs/model-card.md", "tests/model_research/", "scripts/model_research/"],
        "description": "Run offline local-load smoke tests for approved model profiles.",
        "acceptance_criteria": [
            "Selected models load with runtime offline flags and no remote API calls."
        ],
        "machine_gates": ["model_offline_load_smoke"],
        "paper_sections": ["04_data_and_implementation.md"],
        "human_gate": None,
        "status": "READY",
    },
    {
        "id": "FINK-MR-07",
        "phase": "MR",
        "priority": "P1",
        "depends_on": ["FINK-MR-06"],
        "scope": "M",
        "allowed_paths": ["docs/model-card.md", "tests/model_research/"],
        "description": (
            "Benchmark OCR extraction for money, percentages, dates, durations, and article "
            "numbers."
        ),
        "acceptance_criteria": [
            "Benchmark summary uses synthetic/sanitized inputs and records exact model revisions."
        ],
        "machine_gates": ["ocr_benchmark_summary"],
        "paper_sections": ["05_experiments.md"],
        "human_gate": None,
        "status": "READY",
    },
    {
        "id": "FINK-MR-08",
        "phase": "MR",
        "priority": "P1",
        "depends_on": ["FINK-MR-06"],
        "scope": "M",
        "allowed_paths": ["docs/model-card.md", "tests/model_research/"],
        "description": "Benchmark Korean/English retrieval consistency.",
        "acceptance_criteria": [
            "KO and EN paired queries resolve to the same canonical IDs on "
            "synthetic/sanitized data."
        ],
        "machine_gates": ["ko_en_retrieval_benchmark"],
        "paper_sections": ["05_experiments.md"],
        "human_gate": None,
        "status": "READY",
    },
    {
        "id": "FINK-MR-09",
        "phase": "MR",
        "priority": "P1",
        "depends_on": ["FINK-MR-06"],
        "scope": "M",
        "allowed_paths": ["docs/model-card.md", "tests/model_research/"],
        "description": "Benchmark local explanation quality while preserving evidence boundaries.",
        "acceptance_criteria": [
            "Local LLM explains retrieved evidence but does not create legal evidence or set "
            "production risk scores."
        ],
        "machine_gates": ["local_explanation_boundary_test"],
        "paper_sections": ["05_experiments.md", "08_responsible_ai.md"],
        "human_gate": None,
        "status": "READY",
    },
    {
        "id": "FINK-MR-10",
        "phase": "MR",
        "priority": "P1",
        "depends_on": ["FINK-MR-07", "FINK-MR-08", "FINK-MR-09"],
        "scope": "S",
        "allowed_paths": ["docs/model-card.md", "configs/models/"],
        "description": (
            "Write selected-profile report with licenses, revisions, configs, and benchmark "
            "summaries."
        ),
        "acceptance_criteria": [
            "Public Git contains only model IDs, licenses, revisions, configs, benchmark "
            "summaries, and selected profiles."
        ],
        "machine_gates": ["selected_profile_report"],
        "paper_sections": ["04_data_and_implementation.md", "05_experiments.md"],
        "human_gate": "MODEL_PROFILE_APPROVED",
        "status": "READY",
    },
]


def spec_task_to_loop(task: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(task)
    result["source"] = "docs/specs/08_IMPLEMENTATION_BACKLOG.yaml"
    result["status"] = "READY"
    return result


def sync_backlog() -> None:
    spec = load_yaml(REPO_ROOT / "docs" / "specs" / "08_IMPLEMENTATION_BACKLOG.yaml")
    tasks = [spec_task_to_loop(task) for task in spec["tasks"]]
    tasks.extend(deepcopy(MODEL_TASKS))
    data = {
        "schema_version": 1,
        "generated_from": "docs/specs/08_IMPLEMENTATION_BACKLOG.yaml",
        "generated_at": now_utc(),
        "source_sha256": sha256_file(
            REPO_ROOT / "docs" / "specs" / "08_IMPLEMENTATION_BACKLOG.yaml"
        ),
        "status_legend": {
            "READY": "candidate status; dependencies and gates are still checked at selection time",
            "DONE": "accepted and committed on main",
            "BLOCKED": "failed or exhausted and rolled back within allowed paths",
        },
        "tasks": tasks,
    }
    write_text(BACKLOG_PATH, dump_yaml(data))


def initial_state() -> None:
    data = {
        "schema_version": 1,
        "created_at": now_utc(),
        "active_task": None,
        "path_locks": {},
        "last_run_id": None,
        "last_run_dir": None,
        "last_verdict": None,
        "latest_successful_commit": current_commit(),
        "base_commit": current_commit(),
        "round": 0,
        "icml_template_hashes": icml_template_hashes(),
    }
    write_json(STATE_PATH, data)


def update_loop_md() -> None:
    backlog = load_backlog()
    gates = load_human_gates()
    state = load_state()
    selection = select_eligible_task(backlog, gates, state)
    next_task = selection.task["id"] if selection else "none"
    gate_rows = []
    for gate_id, gate in gates.get("gates", {}).items():
        status = gate.get("status", "UNKNOWN")
        approved = gate.get("approved")
        notes = gate.get("notes", "")
        gate_rows.append(f"| {gate_id} | {status} | {approved} | {notes} |")
    done = [task["id"] for task in backlog["tasks"] if task.get("status") == "DONE"]
    blocked = [task["id"] for task in backlog["tasks"] if task.get("status") == "BLOCKED"]
    lines = [
        "# FInk Agent Loop Status",
        "",
        f"- Generated: `{now_utc()}`",
        "- Current branch: `main`",
        f"- Base commit: `{state.get('base_commit')}`",
        f"- Latest successful commit: `{state.get('latest_successful_commit')}`",
        f"- Active task: `{state.get('active_task') or 'none'}`",
        f"- Round: `{state.get('round', 0)}`",
        f"- Claude verdict: `{state.get('last_verdict') or 'none'}`",
        f"- Latest run path: `{state.get('last_run_dir') or '.fink/runs/<RUN_ID>/<TASK_ID>'}`",
        "",
        "## Gates",
        "",
        "- Branch gate: main only.",
        "- Clean tree gate: enforced at task start by `loop_once.sh`.",
        "- Machine gates: `bash scripts/agent_loop/run_gates.sh`.",
        "- Paper-sync status: scaffold ledgers present; no measured results claimed.",
        "- Fixes: none pending in bootstrap scaffold.",
        "",
        "## Human Gates",
        "",
        "| Gate | Status | Approved | Notes |",
        "|---|---|---:|---|",
        *gate_rows,
        "",
        "## Tasks",
        "",
        f"- Next eligible task: `{next_task}`",
        f"- Done count: `{len(done)}`",
        f"- Blocked count: `{len(blocked)}`",
        "- Next task selection order: highest priority, shortest scope, lexical task ID.",
        "",
        "## Operator Commands",
        "",
        "```bash",
        "# single task / single queue",
        "bash scripts/agent_loop/loop_once.sh",
        "bash scripts/agent_loop/loop_run.sh scripts/agent_loop/queue.s1.txt 8",
        "# all queues in dependency order (s0 -> models -> s1 -> s2 -> s3)",
        "bash scripts/agent_loop/run_all_queues.sh --dry-run",
        "bash scripts/agent_loop/run_all_queues.sh --max-tasks-per-queue 20",
        "# drain the WHOLE backlog at once (every phase S0..S8 + MR)",
        "bash scripts/agent_loop/run_backlog.sh --dry-run",
        "bash scripts/agent_loop/run_backlog.sh --max-tasks 100",
        "# stop the loop after the current task",
        "touch loop/STOP",
        "```",
    ]
    write_text(REPO_ROOT / "LOOP.md", "\n".join(lines) + "\n")


def run() -> None:
    parser = argparse.ArgumentParser(description="Generate or refresh FInk loop docs/state.")
    parser.add_argument("--sync-backlog", action="store_true")
    parser.add_argument("--init-state", action="store_true")
    parser.add_argument("--loop-md", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if args.all or args.sync_backlog:
        sync_backlog()
    if args.all or args.init_state:
        initial_state()
    if args.all or args.loop_md:
        update_loop_md()


if __name__ == "__main__":
    run()
