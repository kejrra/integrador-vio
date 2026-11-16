"""Cliente HTTP para a API VIO, usando somente a biblioteca padrão."""

import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .errors import (
    VioApiError,
    VioBadRequestError,
    VioEnvironmentError,
    VioNotFoundError,
    VioPaymentRequiredError,
    VioUnauthorizedError,
)

Payload = Dict[str, Any]
ImageInput = Union[str, Path]


def _read_dotenv(path: Path) -> Dict[str, str]:
    """Lê pares KEY=VALUE de um .env simples, ignorando comentários."""
    values: Dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        quote = ""
        for index, character in enumerate(value):
            if character in "\"'":
                if not quote:
                    quote = character
                elif quote == character:
                    quote = ""
            elif character == "#" and not quote and (index == 0 or value[index - 1].isspace()):
                value = value[:index].rstrip()
                break
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


class VioClient:
    """Cliente síncrono da API VIO para ambientes de produção e homologação.

    Parâmetros explícitos têm precedência sobre ``os.environ`` e o arquivo
    ``.env`` do diretório atual. As variáveis de ambiente têm precedência
    sobre o arquivo ``.env``.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        environment: Optional[str] = None,
        *,
        poll_interval: float = 1.0,
        timeout: float = 15.0,
    ) -> None:
        dotenv = _read_dotenv(Path.cwd() / ".env")
        self.api_key = api_key or os.environ.get("VIO_API_KEY") or dotenv.get("VIO_API_KEY")
        self.base_url = (base_url or os.environ.get("VIO_BASE_URL") or dotenv.get("VIO_BASE_URL") or "https://vio.api.br").rstrip("/")
        mode = environment or os.environ.get("VIO_ENV") or dotenv.get("VIO_ENV") or "production"
        mode = mode.strip().lower()
        if mode not in ("production", "homologation"):
            raise ValueError("VIO_ENV deve ser 'production' ou 'homologation'.")
        if poll_interval < 0 or timeout < 0:
            raise ValueError("poll_interval e timeout devem ser maiores ou iguais a zero.")
        self.environment = mode
        self.poll_interval = poll_interval
        self.timeout = timeout

    def _require_environment(self, *allowed: str) -> None:
        if self.environment not in allowed:
            names = " ou ".join(allowed)
            raise VioEnvironmentError(
                f"Este método está disponível em {names}; ambiente atual: {self.environment}."
            )

    def _request(self, method: str, path: str, *, payload: Optional[Any] = None,
                 params: Optional[Dict[str, Any]] = None) -> Any:
        if not self.api_key:
            raise VioApiError("Configure VIO_API_KEY ou informe api_key no construtor.")
        url = self.base_url + path
        if params:
            query = urlencode(params, doseq=True)
            url += ("&" if "?" in url else "?") + query
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"X-API-Key": self.api_key, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request) as response:
                body = response.read()
                content_type = response.headers.get("Content-Type", "")
        except HTTPError as exc:
            body = exc.read()
            try:
                detail = body.decode("utf-8")
            except UnicodeDecodeError:
                detail = str(exc.reason)
            message = f"API VIO respondeu HTTP {exc.code}: {detail or exc.reason}"
            error_types = {
                400: VioBadRequestError,
                401: VioUnauthorizedError,
                402: VioPaymentRequiredError,
                404: VioNotFoundError,
            }
            raise error_types.get(exc.code, VioApiError)(message) from exc
        except URLError as exc:
            raise VioApiError(f"Falha de comunicação com a API VIO: {exc.reason}") from exc
        if "image/" in content_type.lower() or "application/octet-stream" in content_type.lower():
            return body
        if not body:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return body

    @staticmethod
    def _encode_image(image: ImageInput) -> str:
        """Converte um caminho de arquivo para base64; preserva strings base64/data URI."""
        if isinstance(image, Path):
            return base64.b64encode(image.read_bytes()).decode("ascii")
        candidate = Path(image)
        if not image.startswith("data:") and candidate.is_file():
            return base64.b64encode(candidate.read_bytes()).decode("ascii")
        return image

    def read_qrcode(self, image: ImageInput, *, wait: bool = True,
                    poll_interval: Optional[float] = None,
                    timeout: Optional[float] = None) -> Payload:
        """Envia documento para leitura e, opcionalmente, aguarda o processamento.

        Em produção, consulta automaticamente o resultado enquanto estiver
        processando. No timeout, devolve o último payload para consulta posterior.
        """
        self._require_environment("production", "homologation")
        result = self._request("POST", "/api/qrcode/read", payload={"image": self._encode_image(image)})
        if not wait or not isinstance(result, dict) or result.get("status") != "processing":
            return result
        extract_id = result.get("id")
        if extract_id is None:
            return result
        interval = self.poll_interval if poll_interval is None else poll_interval
        limit = self.timeout if timeout is None else timeout
        if interval < 0 or limit < 0:
            raise ValueError("poll_interval e timeout devem ser maiores ou iguais a zero.")
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            if interval:
                time.sleep(min(interval, max(0.0, deadline - time.monotonic())))
            result = self.get_result(str(extract_id))
            if not isinstance(result, dict) or result.get("status") != "processing":
                return result
        return result

    def get_result(self, extract_id: str) -> Any:
        """Consulta o resultado de uma leitura pelo identificador."""
        self._require_environment("production", "homologation")
        return self._request("GET", f"/api/qrcode/result/{extract_id}")

    def get_history(self, **params: Any) -> Any:
        """Consulta o histórico de leituras em produção, com filtros opcionais."""
        self._require_environment("production")
        return self._request("GET", "/api/qrcode/history", params=params)

    def get_stats(self, **params: Any) -> Any:
        """Consulta estatísticas em produção, com filtros opcionais."""
        self._require_environment("production")
        return self._request("GET", "/api/qrcode/stats", params=params)

    def get_results(self, ids: list[str]) -> Any:
        """Consulta vários resultados em uma única chamada de homologação."""
        self._require_environment("homologation")
        return self._request("POST", "/api/qrcode/results", payload=ids)

    def get_photo(self, extract_id: str) -> Any:
        """Obtém a foto associada a uma extração em homologação."""
        self._require_environment("homologation")
        return self._request("GET", f"/api/qrcode/photo/{extract_id}")

    def get_face(self, extract_id: str) -> Any:
        """Obtém a imagem facial/biométrica em homologação."""
        self._require_environment("homologation")
        return self._request("GET", f"/api/qrcode/face/{extract_id}")

    def get_balance(self) -> Any:
        """Consulta o saldo da conta em homologação."""
        self._require_environment("homologation")
        return self._request("GET", "/api/balance/")
