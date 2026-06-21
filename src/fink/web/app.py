from __future__ import annotations

import argparse
import html
import ipaddress
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

DEFAULT_LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

PRIVACY_BANNER = (
    "Local-only session. Contract uploads and OCR text stay on this device; "
    "no telemetry, cloud OCR, remote LLM, or external legal search is used."
)
NOT_LEGAL_ADVICE_BANNER = (
    "FInk reports Contractual Financial Review Priority only. It is not legal advice "
    "and not a fraud, illegality, validity, unfairness, or guaranteed-loss verdict."
)
TRUSTED_LAN_WARNING = (
    "Trusted-LAN mode exposes this local server only to devices on the same private "
    "network. Use it only on a network you control, and stop the server when finished."
)
DISCLOSURE_ITEMS = (
    "Review priority is not a legal, fraud, validity, unfairness, or guaranteed-loss verdict.",
    "Figures are scenario estimates from user assumptions, not guaranteed losses.",
    "Official-source grounding is UNVERIFIED pending A0 confirmation.",
    "Korean source language is canonical; English UI text is a generated aid.",
)

LAN_CONFIRMATION_TEXT = "I understand this is a trusted-LAN-only local server."
_BLOCKED_BIND_HOSTS = frozenset({"0.0.0.0", "::", ""})


@dataclass(frozen=True)
class WebBindSettings:
    host: str = DEFAULT_LOOPBACK_HOST
    port: int = DEFAULT_PORT
    lan_enabled: bool = False
    trusted_lan_warning: str = ""
    trusted_lan_warning_acknowledged: bool = False

    @property
    def base_url(self) -> str:
        return f"http://{_format_host_for_url(self.host)}:{self.port}"

    def public_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "base_url": self.base_url,
            "lan_enabled": self.lan_enabled,
            "trusted_lan_warning": self.trusted_lan_warning,
            "trusted_lan_warning_acknowledged": self.trusted_lan_warning_acknowledged,
            "local_only": True,
        }


class WebBindingError(ValueError):
    """Raised when the requested web bind mode would expose FInk too broadly."""


def resolve_bind_settings(
    *,
    host: str | None = None,
    port: int = DEFAULT_PORT,
    allow_lan: bool = False,
    trusted_lan_ack: bool = False,
) -> WebBindSettings:
    """Resolve the server bind address with loopback as the safe default."""

    _validate_port(port)
    requested = (host or DEFAULT_LOOPBACK_HOST).strip()
    if not allow_lan:
        if requested not in {DEFAULT_LOOPBACK_HOST, "localhost", "::1"}:
            raise WebBindingError("LAN binding requires explicit allow_lan opt-in")
        return WebBindSettings(host=DEFAULT_LOOPBACK_HOST, port=port)

    if not trusted_lan_ack:
        raise WebBindingError("trusted-LAN warning must be acknowledged before LAN binding")
    if requested in _BLOCKED_BIND_HOSTS:
        raise WebBindingError("bind to a specific private LAN interface, not a wildcard host")
    if requested in {DEFAULT_LOOPBACK_HOST, "localhost", "::1"}:
        raise WebBindingError("LAN mode requires a private LAN interface address")
    if not _is_private_interface(requested):
        raise WebBindingError("LAN mode requires a private or link-local interface address")
    return WebBindSettings(
        host=requested,
        port=port,
        lan_enabled=True,
        trusted_lan_warning=TRUSTED_LAN_WARNING,
        trusted_lan_warning_acknowledged=True,
    )


def render_index_html(settings: WebBindSettings | None = None) -> str:
    """Render the local-only responsive UI shell without external assets."""

    bind = settings or resolve_bind_settings()
    lan_warning = (
        f'<p class="banner banner-warning" role="status">{html.escape(bind.trusted_lan_warning)}</p>'
        if bind.lan_enabled
        else ""
    )
    disclosures = "\n".join(
        f"<li>{html.escape(item)}</li>"
        for item in (PRIVACY_BANNER, NOT_LEGAL_ADVICE_BANNER, *DISCLOSURE_ITEMS)
    )
    return f"""<!doctype html>
<html lang="ko" data-default-locale="ko" data-local-only="true">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <title>FInk Local Review</title>
  <style>{_css()}</style>
</head>
<body>
  <a class="skip-link" href="#workspace">Skip to workspace</a>
  <header class="topbar">
    <div>
      <p class="eyebrow">FInk local-first review</p>
      <h1>계약상 금융 검토 우선도</h1>
      <p class="subtitle">Contractual Financial Review Priority</p>
    </div>
    <nav class="locale-toggle" aria-label="Locale">
      <button type="button" aria-pressed="true">KO</button>
      <button type="button" aria-pressed="false">EN generated</button>
    </nav>
  </header>

  <section class="disclosure-bar" aria-label="Persistent privacy and disclaimer banners">
    <p class="banner banner-privacy">{html.escape(PRIVACY_BANNER)}</p>
    <p class="banner banner-advice">{html.escape(NOT_LEGAL_ADVICE_BANNER)}</p>
    {lan_warning}
  </section>

  <main id="workspace" class="workspace">
    <section class="input-pane" aria-labelledby="input-heading">
      <div class="section-heading">
        <p class="eyebrow">Local input</p>
        <h2 id="input-heading">검토할 계약 자료</h2>
      </div>
      <div class="upload-grid" aria-label="Input modes">
        <label class="upload-tile">
          <span>Camera</span>
          <input type="file" accept="image/*" capture="environment" aria-label="Capture pages">
        </label>
        <label class="upload-tile">
          <span>Image</span>
          <input type="file" accept="image/png,image/jpeg,image/webp,image/heic,image/heif" aria-label="Choose image">
        </label>
        <label class="upload-tile">
          <span>PDF</span>
          <input type="file" accept="application/pdf" aria-label="Choose PDF">
        </label>
      </div>
      <label class="paste-label" for="paste-box">Paste clause text</label>
      <textarea id="paste-box" rows="8" spellcheck="false"></textarea>
      <div class="action-row">
        <button type="button">Analyze locally</button>
        <button type="button" class="secondary">Clear now</button>
      </div>
      <p class="hint">PDFs, images, OCR text, and paste text remain ephemeral local session data.</p>
    </section>

    <section class="report-pane" aria-labelledby="report-heading">
      <div class="section-heading">
        <p class="eyebrow">Preview report</p>
        <h2 id="report-heading">Four separate dimensions</h2>
      </div>
      <div class="dimension-grid">
        <article>
          <h3>Review Priority</h3>
          <output aria-label="Review priority score">0 / 100</output>
        </article>
        <article>
          <h3>Monetary Exposure</h3>
          <p>Low / base / high scenario ranges stay separate by exposure type.</p>
        </article>
        <article>
          <h3>Time Exposure</h3>
          <p>Typed timing fields and pathway labels appear here.</p>
        </article>
        <article>
          <h3>Evidence &amp; OCR Confidence</h3>
          <p>UNVERIFIED source status and OCR confidence appear here.</p>
        </article>
      </div>
      <aside class="export-disclosures" aria-label="Report and export disclosures">
        <h3>Report disclosures</h3>
        <ul>
          {disclosures}
        </ul>
      </aside>
    </section>
  </main>

  <footer>
    <span>Serving from {html.escape(bind.base_url)}</span>
    <span>{html.escape("LAN opt-in enabled" if bind.lan_enabled else "Loopback only")}</span>
  </footer>
</body>
</html>
"""


def create_app(settings: WebBindSettings | None = None) -> Any:
    """Create the local web app.

    A real FastAPI app is returned when FastAPI is installed. The lightweight
    ASGI fallback keeps smoke tests and local rendering available in minimal
    offline environments without adding an out-of-scope dependency here.
    """

    bind = settings or resolve_bind_settings()
    try:
        return _create_fastapi_app(bind)
    except ModuleNotFoundError as exc:
        if exc.name not in {"fastapi", "fastapi.responses"}:
            raise
        return LocalASGIApp(bind)


def _create_fastapi_app(settings: WebBindSettings) -> Any:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse

    app = FastAPI(
        title="FInk Local Web",
        version="0.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.middleware("http")
    async def add_local_security_headers(request: Any, call_next: Any) -> Any:
        response = await call_next(request)
        _apply_security_headers(response.headers)
        return response

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(render_index_html(settings))

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        return JSONResponse(_health_payload(settings))

    @app.get("/privacy")
    def privacy() -> JSONResponse:
        return JSONResponse(_privacy_payload(settings))

    return app


class LocalASGIApp:
    """Small ASGI fallback for dependency-minimal local smoke tests."""

    def __init__(self, settings: WebBindSettings) -> None:
        self.settings = settings

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await _send_response(send, 404, b"Not found", "text/plain; charset=utf-8")
            return
        method = scope.get("method", "GET")
        path = scope.get("path", "/")
        if method != "GET":
            await _send_response(send, 405, b"Method not allowed", "text/plain; charset=utf-8")
            return
        if path == "/":
            await _send_response(
                send,
                200,
                render_index_html(self.settings).encode("utf-8"),
                "text/html; charset=utf-8",
            )
            return
        if path == "/healthz":
            await _send_response(
                send,
                200,
                json.dumps(_health_payload(self.settings)).encode("utf-8"),
                "application/json",
            )
            return
        if path == "/privacy":
            await _send_response(
                send,
                200,
                json.dumps(_privacy_payload(self.settings)).encode("utf-8"),
                "application/json",
            )
            return
        await _send_response(send, 404, b"Not found", "text/plain; charset=utf-8")


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the FInk local FastAPI web app.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--allow-lan", action="store_true")
    parser.add_argument("--trusted-lan-ack", action="store_true")
    args = parser.parse_args(argv)
    settings = resolve_bind_settings(
        host=args.host,
        port=args.port,
        allow_lan=args.allow_lan,
        trusted_lan_ack=args.trusted_lan_ack,
    )
    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        raise SystemExit("uvicorn is required to run the FastAPI server") from exc
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_config=None)
    return 0


def _health_payload(settings: WebBindSettings) -> dict[str, Any]:
    return {
        "status": "ok",
        "local_only": True,
        "outbound_network_clients": 0,
        "bind": settings.public_dict(),
    }


def _privacy_payload(settings: WebBindSettings) -> dict[str, Any]:
    return {
        "privacy_banner": PRIVACY_BANNER,
        "not_legal_advice_banner": NOT_LEGAL_ADVICE_BANNER,
        "disclosures": DISCLOSURE_ITEMS,
        "lan": settings.public_dict(),
    }


def _css() -> str:
    return """
:root {
  color-scheme: light;
  --ink: #151a22;
  --muted: #4a5565;
  --line: #c7cfda;
  --panel: #ffffff;
  --canvas: #f4f7fb;
  --accent: #006d77;
  --accent-strong: #014f56;
  --warn-bg: #fff3cd;
  --warn-ink: #5a4100;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--canvas);
  color: var(--ink);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.5;
}
.skip-link {
  position: absolute;
  left: 1rem;
  top: -5rem;
  background: var(--ink);
  color: #fff;
  padding: .75rem 1rem;
  z-index: 3;
}
.skip-link:focus { top: 1rem; }
.topbar, footer {
  display: flex;
  gap: 1rem;
  justify-content: space-between;
  align-items: center;
  padding: 1rem clamp(1rem, 4vw, 2rem);
  background: var(--panel);
  border-bottom: 1px solid var(--line);
}
h1, h2, h3, p { margin-top: 0; }
h1 { margin-bottom: .15rem; font-size: 1.75rem; }
h2 { font-size: 1.25rem; }
h3 { font-size: 1rem; }
.eyebrow {
  margin-bottom: .25rem;
  color: var(--accent-strong);
  font-size: .8rem;
  font-weight: 700;
  text-transform: uppercase;
}
.subtitle, .hint, article p, footer { color: var(--muted); }
.locale-toggle, .action-row, .upload-grid {
  display: flex;
  gap: .75rem;
  flex-wrap: wrap;
}
button, input, textarea {
  font: inherit;
  min-height: 44px;
}
button {
  border: 1px solid var(--accent-strong);
  background: var(--accent);
  color: #fff;
  padding: .65rem 1rem;
  border-radius: 6px;
  font-weight: 700;
}
button.secondary, .locale-toggle button {
  background: #fff;
  color: var(--accent-strong);
}
button:focus-visible, input:focus-visible, textarea:focus-visible, a:focus-visible {
  outline: 3px solid #ffbf47;
  outline-offset: 2px;
}
.disclosure-bar {
  position: sticky;
  top: 0;
  z-index: 2;
  display: grid;
  gap: .5rem;
  padding: .75rem clamp(1rem, 4vw, 2rem);
  background: #e8f3f4;
  border-bottom: 1px solid var(--line);
}
.banner {
  margin: 0;
  padding: .7rem .85rem;
  border-left: 4px solid var(--accent);
  background: #fff;
}
.banner-warning {
  color: var(--warn-ink);
  background: var(--warn-bg);
  border-left-color: #b7791f;
}
.workspace {
  display: grid;
  gap: 1rem;
  padding: 1rem;
}
.input-pane, .report-pane {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 1rem;
}
.upload-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
  margin-bottom: 1rem;
}
.upload-tile {
  display: grid;
  gap: .5rem;
  min-height: 7rem;
  align-content: center;
  padding: 1rem;
  border: 1px dashed var(--accent);
  border-radius: 8px;
  background: #f9fcfd;
}
.paste-label {
  display: block;
  margin-bottom: .35rem;
  font-weight: 700;
}
textarea {
  width: 100%;
  min-height: 9rem;
  resize: vertical;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: .75rem;
}
.action-row { margin-top: 1rem; }
.dimension-grid {
  display: grid;
  gap: .75rem;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
}
article {
  min-height: 8rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 1rem;
}
output {
  display: block;
  font-size: 1.75rem;
  font-weight: 800;
}
.export-disclosures {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--line);
}
.export-disclosures li { margin-bottom: .4rem; }
footer {
  border-top: 1px solid var(--line);
  border-bottom: 0;
}
@media (min-width: 900px) {
  .workspace {
    grid-template-columns: minmax(20rem, .9fr) minmax(28rem, 1.1fr);
    align-items: start;
    padding: 1.5rem 2rem;
  }
  .disclosure-bar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 640px) {
  .topbar, footer {
    align-items: stretch;
    flex-direction: column;
  }
  .locale-toggle button, .action-row button {
    flex: 1 1 10rem;
  }
}
"""


def _validate_port(port: int) -> None:
    if port < 1 or port > 65535:
        raise WebBindingError("port must be between 1 and 65535")


def _format_host_for_url(host: str) -> str:
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        return host
    if parsed.version == 6:
        return f"[{host}]"
    return host


def _is_private_interface(host: str) -> bool:
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError as exc:
        raise WebBindingError("LAN host must be a literal private interface address") from exc
    return bool(parsed.is_private or parsed.is_link_local)


def _apply_security_headers(headers: Any) -> None:
    headers["Cache-Control"] = "no-store"
    headers["Referrer-Policy"] = "no-referrer"
    headers["X-Content-Type-Options"] = "nosniff"
    headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "connect-src 'self'; "
        "base-uri 'none'; "
        "form-action 'self'"
    )


async def _send_response(
    send: Callable[[dict[str, Any]], Awaitable[None]],
    status: int,
    body: bytes,
    content_type: str,
) -> None:
    headers = {
        "content-type": content_type,
        "content-length": str(len(body)),
    }
    _apply_security_headers(headers)
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (key.lower().encode("ascii"), value.encode("utf-8"))
                for key, value in headers.items()
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


if __name__ == "__main__":
    raise SystemExit(run())
