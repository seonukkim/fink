from __future__ import annotations

import contextlib
import importlib
import io
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import tomllib


ROOT = Path(__file__).resolve().parents[2]


def _load_web_app():
    src_root = ROOT / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module("fink.web.app")


WEB_APP = _load_web_app()


def _pyproject() -> dict[str, object]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


class PackagingMetadataTests(unittest.TestCase):
    def test_project_is_installable_src_namespace_package(self) -> None:
        config = _pyproject()

        self.assertEqual(config["build-system"]["build-backend"], "setuptools.build_meta")
        tool_config = config.get("tool", {})
        self.assertNotEqual(tool_config.get("uv", {}).get("package"), False)

        find_config = tool_config["setuptools"]["packages"]["find"]
        self.assertEqual(find_config["where"], ["src"])
        self.assertEqual(find_config["include"], ["fink*"])
        self.assertTrue(find_config["namespaces"])

    def test_web_extra_and_console_script_are_declared(self) -> None:
        project = _pyproject()["project"]

        self.assertEqual(project["scripts"]["fink-web"], "fink.web.app:run")
        web_extra = set(project["optional-dependencies"]["web"])
        self.assertEqual(
            web_extra,
            {"fastapi>=0.115", "uvicorn>=0.30", "python-multipart>=0.0.9"},
        )

        core_dependencies = set(project["dependencies"])
        self.assertEqual(core_dependencies, {"pyyaml>=6"})
        heavy_names = {"paddleocr", "torch", "transformers", "qwen", "easyocr"}
        self.assertFalse(
            any(
                dependency.lower().split("=", maxsplit=1)[0] in heavy_names
                for dependency in core_dependencies
            )
        )


class WebCliTests(unittest.TestCase):
    def test_help_exits_zero_without_importing_uvicorn(self) -> None:
        with (
            self.assertRaises(SystemExit) as raised,
            contextlib.redirect_stdout(io.StringIO()) as stdout,
        ):
            WEB_APP.run(["--help"])

        self.assertEqual(raised.exception.code, 0)
        help_text = stdout.getvalue()
        self.assertIn("--host", help_text)
        self.assertIn("--port", help_text)
        self.assertIn("--allow-lan", help_text)

    def test_invalid_port_is_rejected_nonzero(self) -> None:
        with (
            self.assertRaises(SystemExit) as raised,
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            WEB_APP.run(["--port", "0"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("port must be between 1 and 65535", stderr.getvalue())

    def test_wildcard_host_is_rejected_nonzero_even_with_lan_ack(self) -> None:
        with (
            self.assertRaises(SystemExit) as raised,
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            WEB_APP.run(["--host", "0.0.0.0", "--allow-lan", "--trusted-lan-ack"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("not a wildcard host", stderr.getvalue())

    def test_valid_loopback_cli_invokes_uvicorn_with_app_factory(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_run(app: object, **kwargs: object) -> None:
            calls.append({"app": app, **kwargs})

        fake_uvicorn = types.SimpleNamespace(run=fake_run)
        with patch.dict(sys.modules, {"uvicorn": fake_uvicorn}):
            status = WEB_APP.run(["--host", "127.0.0.1", "--port", "8765"])

        self.assertEqual(status, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["host"], "127.0.0.1")
        self.assertEqual(calls[0]["port"], 8765)
        self.assertIsNone(calls[0]["log_config"])
        self.assertTrue(callable(calls[0]["app"]))

    def test_module_main_delegates_to_cli_run(self) -> None:
        web_main = importlib.import_module("fink.web.__main__")

        with patch.object(web_main, "run", return_value=17):
            self.assertEqual(web_main.main(), 17)


if __name__ == "__main__":
    unittest.main()
