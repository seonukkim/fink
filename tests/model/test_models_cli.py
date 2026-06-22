from __future__ import annotations

import unittest
from io import StringIO
from unittest import mock

from fink.models import download


class ModelsCliTests(unittest.TestCase):
    def test_list_prints_core_model_ids_and_gguf_target(self) -> None:
        with (
            mock.patch.dict("sys.modules", {"huggingface_hub": None}),
            mock.patch("sys.stdout", new_callable=StringIO) as stdout,
        ):
            code = download.main(["list"])

        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Qwen/Qwen3-Embedding-0.6B", output)
        self.assertIn("Qwen/Qwen3-Reranker-0.6B", output)
        self.assertIn("Qwen/Qwen3-1.7B-GGUF", output)
        self.assertIn("qwen3-1_7b-instruct-q4_k_m.gguf", output)

    def test_dry_run_without_enable_flag_prints_instruction_without_importing_hub(self) -> None:
        with (
            mock.patch.dict("os.environ", {"FINK_MODEL_DOWNLOAD_ALLOWED": ""}, clear=False),
            mock.patch.dict("sys.modules", {"huggingface_hub": None}),
            mock.patch("sys.stdout", new_callable=StringIO) as stdout,
        ):
            code = download.main(["download", "--dry-run"])

        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Set FINK_MODEL_DOWNLOAD_ALLOWED=true", output)
        self.assertIn("uv run fink-models download", output)
        self.assertNotIn("WOULD download", output)


if __name__ == "__main__":
    unittest.main()
