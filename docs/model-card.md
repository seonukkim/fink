# FInk Model Card

Status: scaffold.

FInk does not require a remote runtime model. Any future local model may explain
retrieved evidence but must not create legal evidence, directly set production
risk scores, or fabricate financial impact.

Model research policy:

- Default license floor: `public_open`.
- Automatically eligible licenses: Apache-2.0, MIT, BSD, ISC, CC0, and
  CC-BY-4.0 style licenses.
- Unknown, missing, gated, custom, noncommercial, and research-only licenses are
  rejected by default.
- Public Git may contain only model IDs, licenses, pinned revisions, configs,
  benchmark summaries, and selected profiles.
- Weights live under `$PRIVATE_ROOT/models` or the Hugging Face cache, never Git.
- The Hugging Face token is loaded only through
  `scripts/model_research/run_with_hf_auth.sh` and is never printed, logged,
  copied, documented, or committed.

Automated enforcement (HD-12): the open-source-only floor and the no-tracked-weights
rule are enforced on every loop task by the `model_license_floor` machine gate,
which anchors the allowlist (so it cannot be widened by editing config) and rejects
any non-allowlisted declared license or any tracked weight file. Model downloads run
only for allowlisted models within `max_download_size_gb`; the human MODEL_* gates
are auto-resolved by this policy rather than per-download sign-off.

## Local Model-Research Inventory

Structured inventory: `configs/models/local_inventory.yaml`.
Parser gate: `python3 scripts/model_research/model_research_metadata_parse.py`.

Captured for task `FINK-MR-01` at `2026-06-21T21:05:00+09:00` from
`BASE_COMMIT=5acba4e5d12e34a147de80267e47b2d6eff0d4af`.

- CPU: AMD Ryzen 9 9950X 16-Core Processor, `x86_64`, 16 physical cores /
  32 logical CPUs, WSL2 hypervisor vendor Microsoft, with AVX2 and AVX-512
  features available.
- Memory: 61Gi total RAM, 59Gi available at capture, 16Gi swap.
- GPU: no usable GPU is exposed to the current local session. `nvidia-smi` is
  present, but NVML reports GPU access blocked by the operating system; no
  `/dev/dxg` or `/dev/nvidia*` nodes were visible, and `lspci` is unavailable.
  CUDA toolkit `nvcc` is installed at release 12.0 / V12.0.140, but current
  model-research runs must be treated as CPU-only until GPU access is restored
  and this inventory is refreshed.
- OS: Ubuntu 24.04.3 LTS (Noble Numbat) on Linux
  `6.6.114.1-microsoft-standard-WSL2`, environment `WSL2`.
- Python: CPython 3.12.3 at `/bin/python3`; pip 24.0.
- Disk context: repository and `/tmp` shared a filesystem with 299Gi available
  at capture. Automated download planning still uses the stricter
  `configs/models/candidates.yaml` cap of 20Gi per approved download.

Local runtime constraints:

- Runtime analysis must not require a remote LLM, cloud RAG, external legal
  search, telemetry, cloud OCR, or runtime model download.
- Model weights stay under `$PRIVATE_ROOT/models` or the Hugging Face cache;
  public Git records metadata, configs, benchmark summaries, and selected
  profiles only.
- The Hugging Face token is loaded only through
  `scripts/model_research/run_with_hf_auth.sh`; this inventory did not read the
  token value and does not record private paths or secrets.
- Offline model runs should use the private runtime flags
  `HF_HUB_DISABLE_TELEMETRY=1`, `DO_NOT_TRACK=1`,
  `FINK_RUNTIME_REMOTE_API_ALLOWED=false`, `FINK_RUNTIME_OFFLINE=true`, and
  `FINK_MODEL_DOWNLOAD_ALLOWED=false`.
- Current benchmark planning should assume CPU-only execution, bounded by the
  61Gi memory inventory and the 20Gi configured download cap, unless a later
  accepted task records restored GPU access.

Paper note for `04_data_and_implementation.md`: summarize this environment as a
local WSL2 Ubuntu 24.04 research host with Ryzen 9 9950X CPU, 61Gi memory,
blocked GPU access, Python 3.12.3, no remote runtime API dependency, and
CPU-only local-first constraints at capture time.
