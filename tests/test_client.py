"""Testes unitários do cliente VIO, sem acesso à rede."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from vio_api import (
    VioClient,
    VioEnvironmentError,
    VioNotFoundError,
    VioPaymentRequiredError,
    VioUnauthorizedError,
)


class VioClientTests(unittest.TestCase):
    def test_dotenv_configuration_and_default_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, ".env").write_text(
                'VIO_API_KEY="from-file"\nVIO_ENV=homologation # deployment mode\n', encoding="utf-8"
            )
            with patch("vio_api.client.Path.cwd", return_value=Path(directory)), patch.dict(
                os.environ, {}, clear=True
            ):
                client = VioClient()
            self.assertEqual(client.api_key, "from-file")
            self.assertEqual(client.base_url, "https://vio.api.br")
            self.assertEqual(client.environment, "homologation")

    def test_homologation_routes_are_blocked_in_production(self) -> None:
        client = VioClient(api_key="key", environment="production")
        for method in (client.get_results, client.get_photo, client.get_face, client.get_balance):
            with self.subTest(method=method.__name__), self.assertRaises(VioEnvironmentError):
                method("id") if method.__name__ != "get_balance" else method()

    def test_production_polling_returns_completed_second_attempt(self) -> None:
        client = VioClient(api_key="key", poll_interval=0, timeout=2)
        responses = iter([{"id": "abc", "status": "processing"}, {"id": "abc", "status": "completed", "data": {}}])
        with patch.object(client, "_request", side_effect=lambda *args, **kwargs: next(responses)), patch(
            "vio_api.client.time.monotonic", side_effect=[0.0, 0.0, 0.1, 0.1]
        ):
            result = client.read_qrcode("YWJj")
        self.assertEqual(result["status"], "completed")

    def test_polling_timeout_returns_last_processing_payload(self) -> None:
        client = VioClient(api_key="key", poll_interval=0, timeout=0)
        initial = {"id": "abc", "status": "processing"}
        with patch.object(client, "_request", return_value=initial):
            self.assertEqual(client.read_qrcode("YWJj"), initial)

    def test_http_status_errors_are_mapped(self) -> None:
        client = VioClient(api_key="key")
        errors = {
            401: VioUnauthorizedError,
            402: VioPaymentRequiredError,
            404: VioNotFoundError,
        }
        for status, error_type in errors.items():
            http_error = HTTPError("https://vio.api.br/", status, "failure", {}, None)
            with self.subTest(status=status), patch("vio_api.client.urlopen", side_effect=http_error):
                with self.assertRaises(error_type):
                    client.get_result("id")


if __name__ == "__main__":
    unittest.main()
