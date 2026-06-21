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

## Hugging Face Candidate Metadata

Structured candidate inventory: `configs/models/candidates.yaml`.

Captured for task `FINK-MR-02` at `2026-06-21T21:18:54+09:00` from
`BASE_COMMIT=1feb4ac2377577e1e580fdc3a75e6b643d5ec238`.

The inventory records only public metadata for model research. It does not
download weights, read `.env`, record token values, or authorize a remote
runtime API. Shell network access was blocked in this sandbox by name-resolution
failure; future refreshes should use the approved cached Hugging Face token via
`scripts/model_research/run_with_hf_auth.sh`.

| Role | Candidate | HF repo | License | Gated | Pinned revision | Size |
|------|-----------|---------|---------|-------|-----------------|------|
| OCR/layout | `paddleocr_vl` | `PaddlePaddle/PaddleOCR-VL` | `apache-2.0` | false | `baee27eebcbf26cdeab160116679d765f13a3f27` | 2.16 GB |
| OCR fallback | `qwen3_vl_4b` | `Qwen/Qwen3-VL-4B-Instruct` | `apache-2.0` | false | `ebb281ec70b05090aa6165b016eac8ec08e71b17` | 8.89 GB |
| Embedding | `qwen3_embedding_0_6b` | `Qwen/Qwen3-Embedding-0.6B` | `apache-2.0` | false | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` | 1.21 GB |
| Embedding baseline | `bge_m3` | `BAAI/bge-m3` | `mit` | false | `5617a9f61b028005a4858fdac845db406aefb181` | 4.59 GB |
| Reranker | `qwen3_reranker_0_6b` | `Qwen/Qwen3-Reranker-0.6B` | `apache-2.0` | false | `e61197ed45024b0ed8a2d74b80b4d909f1255473` | 1.21 GB |
| Explanation | `qwen3_4b` | `Qwen/Qwen3-4B` | `apache-2.0` | false | `1cfa9a7208912126459214e8b04321603b3df60c` | 8.06 GB |
| Optional explanation | `qwen3_8b` | `Qwen/Qwen3-8B` | `apache-2.0` | false | `b968826d9c46dd6066d109eabc6255188de91218` | 16.4 GB |

Metadata policy outcome:

- All candidates are public and recorded as ungated at capture.
- All declared licenses are within the open-license floor enforced by
  `model_license_floor`.
- Every candidate has a full 40-character pinned revision under `main`.
- All listed sizes are below the configured 20 GB automated-download cap, though
  any future download remains subject to the open-license floor and storage
  privacy boundary.
- `BAAI/bge-m3` includes pickle-bearing `.pt/.bin` files in the repository;
  prefer safetensors or non-pickle assets if that baseline is selected.

Paper note for `04_data_and_implementation.md`: report that the local model
shortlist was inventoried from Hugging Face metadata on 2026-06-21, with all
candidates public/ungated, open-allowlisted (`apache-2.0` or `mit`), pinned to
exact revisions, and kept as metadata-only public records. State that weights
are not committed and runtime analysis remains offline/local-first.

## Download-Size Dry Runs

Structured dry-run record: `configs/models/download_size_dry_runs.yaml`.
Validator gate:
`python3 scripts/model_research/model_size_dry_run_records.py --validate`.

Captured for task `FINK-MR-03` at `2026-06-21T21:29:34+09:00` from
`BASE_COMMIT=3513ab115ebdb177b040bffaa8011fe1a4878115`.

The dry run is metadata-only. It records the exact FINK-MR-02 pinned revision
for each candidate, an estimated disk size in decimal bytes, and an explicit
`downloaded_weight_files=false` flag. It does not call `snapshot_download`,
load a model, write into `$PRIVATE_ROOT/models`, or place weights in public Git.

| Role | Candidate | Exact revision | Estimated disk size |
|------|-----------|----------------|---------------------|
| OCR/layout | `paddleocr_vl` | `baee27eebcbf26cdeab160116679d765f13a3f27` | 2,156,679,874 bytes |
| OCR fallback | `qwen3_vl_4b` | `ebb281ec70b05090aa6165b016eac8ec08e71b17` | 8,890,000,000 bytes |
| Embedding | `qwen3_embedding_0_6b` | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` | 1,210,000,000 bytes |
| Embedding baseline | `bge_m3` | `5617a9f61b028005a4858fdac845db406aefb181` | 4,590,000,000 bytes |
| Reranker | `qwen3_reranker_0_6b` | `e61197ed45024b0ed8a2d74b80b4d909f1255473` | 1,210,000,000 bytes |
| Explanation | `qwen3_4b` | `1cfa9a7208912126459214e8b04321603b3df60c` | 8,060,000,000 bytes |
| Optional explanation | `qwen3_8b` | `b968826d9c46dd6066d109eabc6255188de91218` | 16,400,000,000 bytes |

Dry-run policy outcome:

- Total candidate storage estimate: 42,516,679,874 decimal bytes.
- Largest candidate: `qwen3_8b` at 16,400,000,000 bytes.
- Every candidate remains below the configured 20 GB per-download cap.
- Current Git tracking scan finds no model-weight files with the recorded weight
  suffixes.

Paper note for `04_data_and_implementation.md`: report that FINK-MR-03 recorded
metadata-only download-size dry runs for seven open, public, pinned model
candidates. The dry-run total is 42.516679874 GB decimal, the largest individual
candidate is `qwen3_8b` at 16.4 GB, and no model weights were downloaded or
entered Git.

## Open-License Shortlist

Structured shortlist: `configs/models/open_license_shortlist.yaml`.

Captured for task `FINK-MR-04` at `2026-06-21T21:40:52+09:00` from
`BASE_COMMIT=101765b7a06d87b7bbe7428d8b5379debe0235ac`.

FINK-MR-04 applies the `public_open` floor to the FINK-MR-02 candidate metadata
and FINK-MR-03 size dry runs. A model is accepted only when its recorded license
is in the open allowlist, it is public and ungated, it is not private or
disabled, it has a pinned exact revision, and a metadata-only size dry run is
recorded. Unknown, missing, gated, custom, other, noncommercial, and
research-only licenses are rejected by default.

| Role | Candidate | HF repo | License | Exact revision | Size | Shortlist decision |
|------|-----------|---------|---------|----------------|------|--------------------|
| OCR/layout | `paddleocr_vl` | `PaddlePaddle/PaddleOCR-VL` | `apache-2.0` | `baee27eebcbf26cdeab160116679d765f13a3f27` | 2.156679874 GB | accepted_public_open |
| OCR fallback | `qwen3_vl_4b` | `Qwen/Qwen3-VL-4B-Instruct` | `apache-2.0` | `ebb281ec70b05090aa6165b016eac8ec08e71b17` | 8.89 GB | accepted_public_open |
| Embedding | `qwen3_embedding_0_6b` | `Qwen/Qwen3-Embedding-0.6B` | `apache-2.0` | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` | 1.21 GB | accepted_public_open |
| Embedding baseline | `bge_m3` | `BAAI/bge-m3` | `mit` | `5617a9f61b028005a4858fdac845db406aefb181` | 4.59 GB | accepted_public_open |
| Reranker | `qwen3_reranker_0_6b` | `Qwen/Qwen3-Reranker-0.6B` | `apache-2.0` | `e61197ed45024b0ed8a2d74b80b4d909f1255473` | 1.21 GB | accepted_public_open |
| Explanation | `qwen3_4b` | `Qwen/Qwen3-4B` | `apache-2.0` | `1cfa9a7208912126459214e8b04321603b3df60c` | 8.06 GB | accepted_public_open |
| Optional explanation | `qwen3_8b` | `Qwen/Qwen3-8B` | `apache-2.0` | `b968826d9c46dd6066d109eabc6255188de91218` | 16.4 GB | accepted_public_open |

Shortlist outcome:

- Accepted: 7 candidates; rejected: 0 candidates.
- Accepted licenses: 6 `apache-2.0`, 1 `mit`.
- Every accepted candidate is public and ungated, below the 20 GB configured
  per-download cap, and pinned to an exact revision.
- This is a metadata-only shortlist for private download planning. It does not
  authorize a remote runtime API and does not place model weights in Git.
- `BAAI/bge-m3` remains accepted under `mit`, but carries the existing security
  note to prefer safetensors or non-pickle assets if selected.

Paper note for `04_data_and_implementation.md`: report that FINK-MR-04 filtered
seven model candidates through the `public_open` floor; all seven were accepted,
zero were rejected, and future unknown, missing, gated, custom, other,
noncommercial, or research-only licenses remain rejected by default. The
shortlist is metadata-only and preserves the no-weight-in-public-Git boundary.
