#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

fail() {
  printf 'clean_clone_web: %s\n' "$*" >&2
  exit 1
}

log() {
  printf '\n== %s ==\n' "$*"
}

source_branch="$(git rev-parse --abbrev-ref HEAD)"
[[ "$source_branch" == "main" ]] || fail "expected branch main, found $source_branch"

source_status="$(git status --short)"
[[ -z "$source_status" ]] || fail "source worktree must be clean before cloning committed tree"

source_head="$(git rev-parse HEAD)"
tmp_parent="$(mktemp -d "${TMPDIR:-/tmp}/fink-clean-clone-web.XXXXXX")"
clone_dir="$tmp_parent/clone"
runtime_root="$tmp_parent/.fink/clean_clone_web"
inputs_dir="$runtime_root/inputs"
logs_dir="$runtime_root/logs"
server_log="$logs_dir/fink-web.log"
clone_log="$logs_dir/git-clone.log"
uv_log="$logs_dir/uv-sync.log"
import_log="$logs_dir/import.log"
network_log="$logs_dir/network-attempts.log"
uv_cache_root="${FINK_UV_CACHE_DIR:-$runtime_root/uv-cache}"
wheelhouse_dir="$runtime_root/wheelhouse"
server_pid=""

mkdir -p "$inputs_dir" "$logs_dir" "$uv_cache_root"

stop_server() {
  if [[ -n "${server_pid:-}" ]] && kill -0 "$server_pid" 2>/dev/null; then
    kill -TERM "$server_pid" 2>/dev/null || true
    for _ in {1..40}; do
      if ! kill -0 "$server_pid" 2>/dev/null; then
        wait "$server_pid" 2>/dev/null || true
        server_pid=""
        return
      fi
      sleep 0.25
    done
    kill -KILL "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
    server_pid=""
  fi
}

cleanup() {
  status=$?
  stop_server
  rm -rf "$inputs_dir"
  rm -rf "$clone_dir"
  if [[ "$status" -eq 0 ]]; then
    rm -rf "$tmp_parent"
  else
    printf 'clean_clone_web: logs retained under %s\n' "$runtime_root" >&2
  fi
}
trap cleanup EXIT

run_in_clone() {
  (cd "$clone_dir" && env -u PYTHONPATH "$@")
}

assert_source_unchanged() {
  [[ "$(git -C "$repo_root" rev-parse HEAD)" == "$source_head" ]] \
    || fail "source repository HEAD changed during smoke run"
  [[ -z "$(git -C "$repo_root" status --short)" ]] \
    || fail "source repository mutated during smoke run"
}

assert_no_tracked_weights() {
  local tracked_weight=""
  while IFS= read -r -d '' tracked_path; do
    case "$tracked_path" in
      *.bin|*.ckpt|*.gguf|*.h5|*.onnx|*.pt|*.pth|*.safetensors|*.tflite)
        tracked_weight="$tracked_path"
        break
        ;;
    esac
  done < <(git -C "$clone_dir" ls-files -z)
  [[ -z "$tracked_weight" ]] || fail "tracked model weight found in clone: $tracked_weight"
}

write_network_guard() {
  local guard_c="$runtime_root/network_guard.c"
  local guard_so="$runtime_root/network_guard.so"
  cat > "$guard_c" <<'C'
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <dlfcn.h>
#include <errno.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>

static int (*real_connect_fn)(int, const struct sockaddr *, socklen_t) = NULL;
static ssize_t (*real_sendto_fn)(int, const void *, size_t, int, const struct sockaddr *, socklen_t) = NULL;

static void resolve_symbols(void) {
  if (real_connect_fn == NULL) {
    real_connect_fn = dlsym(RTLD_NEXT, "connect");
  }
  if (real_sendto_fn == NULL) {
    real_sendto_fn = dlsym(RTLD_NEXT, "sendto");
  }
}

static int is_loopback_address(const struct sockaddr *addr) {
  if (addr == NULL) {
    return 1;
  }
  if (addr->sa_family == AF_UNIX || addr->sa_family == AF_UNSPEC) {
    return 1;
  }
  if (addr->sa_family == AF_INET) {
    const struct sockaddr_in *in = (const struct sockaddr_in *)addr;
    unsigned long host_order = ntohl(in->sin_addr.s_addr);
    return ((host_order >> 24) & 0xff) == 127;
  }
  if (addr->sa_family == AF_INET6) {
    const struct sockaddr_in6 *in6 = (const struct sockaddr_in6 *)addr;
    return IN6_IS_ADDR_LOOPBACK(&in6->sin6_addr);
  }
  return 0;
}

static void record_attempt(const char *call_name, const struct sockaddr *addr) {
  const char *path = getenv("FINK_NETWORK_GUARD_LOG");
  if (path == NULL || path[0] == '\0') {
    return;
  }
  FILE *handle = fopen(path, "a");
  if (handle == NULL) {
    return;
  }
  char target[INET6_ADDRSTRLEN] = "unknown";
  if (addr != NULL && addr->sa_family == AF_INET) {
    const struct sockaddr_in *in = (const struct sockaddr_in *)addr;
    inet_ntop(AF_INET, &in->sin_addr, target, sizeof(target));
    fprintf(handle, "%s family=AF_INET target=%s port=%u\n", call_name, target, ntohs(in->sin_port));
  } else if (addr != NULL && addr->sa_family == AF_INET6) {
    const struct sockaddr_in6 *in6 = (const struct sockaddr_in6 *)addr;
    inet_ntop(AF_INET6, &in6->sin6_addr, target, sizeof(target));
    fprintf(handle, "%s family=AF_INET6 target=%s port=%u\n", call_name, target, ntohs(in6->sin6_port));
  } else {
    fprintf(handle, "%s family=%d target=%s\n", call_name, addr == NULL ? -1 : addr->sa_family, target);
  }
  fclose(handle);
}

int connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
  resolve_symbols();
  if (!is_loopback_address(addr)) {
    record_attempt("connect", addr);
    errno = ENETUNREACH;
    return -1;
  }
  return real_connect_fn(sockfd, addr, addrlen);
}

ssize_t sendto(int sockfd, const void *buf, size_t len, int flags, const struct sockaddr *dest_addr, socklen_t addrlen) {
  resolve_symbols();
  if (!is_loopback_address(dest_addr)) {
    record_attempt("sendto", dest_addr);
    errno = ENETUNREACH;
    return -1;
  }
  return real_sendto_fn(sockfd, buf, len, flags, dest_addr, addrlen);
}
C
  cc -shared -fPIC "$guard_c" -ldl -o "$guard_so"
  printf '%s\n' "$guard_so"
}

build_cached_wheelhouse() {
  python3 - "$wheelhouse_dir" <<'PY'
from __future__ import annotations

import email.parser
import re
import sys
import zipfile
from pathlib import Path

archive_root = Path.home() / ".cache" / "uv" / "archive-v0"
wheelhouse = Path(sys.argv[1])
wanted = {
    "annotated-doc",
    "annotated-types",
    "anyio",
    "attrs",
    "click",
    "colorama",
    "fastapi",
    "h11",
    "idna",
    "iniconfig",
    "jsonschema",
    "jsonschema-specifications",
    "packaging",
    "pluggy",
    "pydantic",
    "pydantic-core",
    "pygments",
    "pytest",
    "python-multipart",
    "pyyaml",
    "referencing",
    "rpds-py",
    "setuptools",
    "sniffio",
    "starlette",
    "typing-extensions",
    "typing-inspection",
    "uvicorn",
}


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def wheel_distribution(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9.]+", "_", name).strip("_")


if not archive_root.exists():
    raise SystemExit(f"uv archive cache not found: {archive_root}")

wheelhouse.mkdir(parents=True, exist_ok=True)
created = 0
for dist_info in archive_root.glob("*/*.dist-info"):
    metadata_path = dist_info / "METADATA"
    wheel_path = dist_info / "WHEEL"
    if not metadata_path.exists() or not wheel_path.exists():
        continue

    metadata = email.parser.Parser().parsestr(
        metadata_path.read_text(encoding="utf-8", errors="replace")
    )
    name = metadata.get("Name") or dist_info.name.removesuffix(".dist-info").rsplit("-", 1)[0]
    version = (
        metadata.get("Version")
        or dist_info.name.removesuffix(".dist-info").rsplit("-", 1)[1]
    )
    if normalized(name) not in wanted:
        continue

    wheel_metadata = email.parser.Parser().parsestr(
        wheel_path.read_text(encoding="utf-8", errors="replace")
    )
    tag = (wheel_metadata.get_all("Tag") or ["py3-none-any"])[0]
    output = wheelhouse / f"{wheel_distribution(name)}-{version}-{tag}.whl"
    if output.exists():
        continue

    root = dist_info.parent
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in root.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())
    created += 1

if not any(wheelhouse.glob("*.whl")):
    raise SystemExit("uv archive cache did not contain packages for the web extra")
print(f"wheelhouse_ready created={created}")
PY
}

free_loopback_port() {
  python3 - <<'PY'
import socket

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
}

write_synthetic_inputs() {
  local paste_json="$inputs_dir/paste.json"
  local pdf_path="$inputs_dir/synthetic-upload.pdf"
  python3 - "$paste_json" "$pdf_path" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

paste_path = Path(sys.argv[1])
pdf_path = Path(sys.argv[2])
paste_payload = {
    "locale": "ko",
    "paste_text": (
        "제3조(정산) 정산은 매 분기 종료일로부터 90일 이내에 지급하며, "
        "회사는 일반 경비를 공제할 수 있다.\n"
        "제5조(위약금) 계약 위반 시 위약금을 부과한다."
    ),
}
paste_path.write_text(json.dumps(paste_payload, ensure_ascii=False), encoding="utf-8")

text = "Revenue share 10 percent. Payment due 30 days."
stream = f"BT ({text}) Tj ET"
body = (
    "%PDF-1.4\n"
    "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    "2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n"
    "3 0 obj\n<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>\nendobj\n"
    f"4 0 obj\n<< /Length {len(stream)} >>\n"
    f"stream\n{stream}\nendstream\nendobj\n"
    "%%EOF\n"
)
pdf_path.write_bytes(body.encode("utf-8"))
PY
}

validate_success_payloads() {
  python3 - "$logs_dir/healthz.json" "$logs_dir/paste-response.json" "$logs_dir/upload-response.json" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path


def load(path: str) -> dict[str, object]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"{path} did not contain a JSON object")
    return data


health = load(sys.argv[1])
if health.get("status") != "ok":
    raise AssertionError(f"healthz status was not ok: {health!r}")
if health.get("local_only") is not True:
    raise AssertionError("healthz did not report local_only=true")
if health.get("outbound_network_clients") != 0:
    raise AssertionError("healthz did not report zero outbound clients")
bind = health.get("bind")
if not isinstance(bind, dict) or bind.get("host") != "127.0.0.1":
    raise AssertionError(f"server was not bound to loopback: {bind!r}")
if bind.get("lan_enabled") is not False:
    raise AssertionError("trusted-LAN mode must be off for the clean-clone smoke")


def validate_analysis(name: str, payload: dict[str, object]) -> None:
    if "error_code" in payload:
        raise AssertionError(f"{name} returned structured error: {payload!r}")
    if payload.get("local_only") is not True:
        raise AssertionError(f"{name} did not report local_only=true")
    if payload.get("grounding") != "UNVERIFIED":
        raise AssertionError(f"{name} did not use graceful UNVERIFIED grounding")
    if not isinstance(payload.get("clause_count"), int) or payload["clause_count"] < 1:
        raise AssertionError(f"{name} did not analyze at least one clause")
    dimensions = payload.get("dimensions")
    if not isinstance(dimensions, dict):
        raise AssertionError(f"{name} did not return dimensions")
    for key in ("review_priority", "monetary", "time", "confidence"):
        if key not in dimensions:
            raise AssertionError(f"{name} missing dimension {key}")
    review_priority = dimensions["review_priority"]
    monetary = dimensions["monetary"]
    confidence = dimensions["confidence"]
    if not isinstance(review_priority, dict) or review_priority.get("score") != 0:
        raise AssertionError(f"{name} no-model/unverified fallback did not keep score at 0")
    if not isinstance(monetary, dict) or monetary.get("present") is not False:
        raise AssertionError(f"{name} invented monetary output without assumptions")
    if not isinstance(confidence, dict) or "overall_confidence" not in confidence:
        raise AssertionError(f"{name} missing confidence structure")


validate_analysis("paste", load(sys.argv[2]))
validate_analysis("multipart upload", load(sys.argv[3]))
PY
}

log "local clone of committed main"
git clone --local --no-hardlinks --branch main --single-branch "$repo_root" "$clone_dir" \
  >"$clone_log" 2>&1
[[ "$(git -C "$clone_dir" rev-parse HEAD)" == "$source_head" ]] \
  || fail "clone HEAD does not match source HEAD"
[[ ! -e "$clone_dir/.fink" ]] || fail "clean clone unexpectedly contains .fink private data"
assert_no_tracked_weights

log "uv sync --extra web"
if ! run_in_clone env UV_CACHE_DIR="$uv_cache_root" uv sync --extra web >"$uv_log" 2>&1; then
  {
    echo
    echo "primary uv sync failed; trying cached offline wheelhouse"
    build_cached_wheelhouse
    run_in_clone env UV_CACHE_DIR="$uv_cache_root" \
      uv sync --extra web --no-index --find-links "$wheelhouse_dir"
  } >>"$uv_log" 2>&1 || {
    tail -n 120 "$uv_log" >&2 || true
    fail "uv sync --extra web failed"
  }
fi

log "import installed web package without PYTHONPATH"
run_in_clone env UV_CACHE_DIR="$uv_cache_root" uv run --no-env-file --no-sync python - <<'PY' >"$import_log" 2>&1
import fink.web.app
import fink.web.upload

print("import_ok")
PY
grep -q "import_ok" "$import_log" || fail "installed import check failed"

log "start fink-web on loopback"
guard_so="$(write_network_guard)"
port="$(free_loopback_port)"
: > "$network_log"
(
  cd "$clone_dir"
  env -u PYTHONPATH \
    FINK_RUNTIME_OFFLINE=1 \
    HF_DATASETS_OFFLINE=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    FINK_NETWORK_GUARD_LOG="$network_log" \
    LD_PRELOAD="$guard_so" \
    UV_CACHE_DIR="$uv_cache_root" \
    uv run --no-env-file --no-sync fink-web --host 127.0.0.1 --port "$port"
) >"$server_log" 2>&1 &
server_pid=$!

ready=0
for _ in {1..120}; do
  if ! kill -0 "$server_pid" 2>/dev/null; then
    tail -n 80 "$server_log" >&2 || true
    fail "fink-web exited before readiness"
  fi
  if curl -fsS --max-time 1 "http://127.0.0.1:$port/healthz" \
    -o "$logs_dir/healthz.json" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.25
done
[[ "$ready" -eq 1 ]] || fail "fink-web readiness timed out"

log "synthetic paste and multipart upload"
write_synthetic_inputs
curl -fsS --max-time 10 \
  -H "content-type: application/json" \
  --data-binary "@$inputs_dir/paste.json" \
  "http://127.0.0.1:$port/api/analyze" \
  -o "$logs_dir/paste-response.json"
curl -fsS --max-time 10 \
  -F "locale=en" \
  -F "contract_file=@$inputs_dir/synthetic-upload.pdf;type=application/pdf;filename=synthetic-upload.pdf" \
  "http://127.0.0.1:$port/api/analyze" \
  -o "$logs_dir/upload-response.json"
validate_success_payloads

log "clean shutdown and runtime-offline assertion"
stop_server
[[ ! -s "$network_log" ]] || {
  cat "$network_log" >&2
  fail "runtime attempted outbound network access"
}
assert_source_unchanged

echo "CLEAN_CLONE_WEB_SMOKE_OK"
