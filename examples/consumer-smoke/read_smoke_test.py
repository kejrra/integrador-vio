"""Leitura simples para validar vio-api a partir de um projeto consumidor."""

import sys
from pathlib import Path

from vio_api import VioApiError, VioClient


DEFAULT_IMAGE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "tests-files"
    / "geral"
    / "qr-comum-url.png"
)


def main() -> int:
    image_path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_IMAGE
    if not image_path.is_file():
        print(f"Arquivo de teste não encontrado: {image_path}")
        return 2

    try:
        client = VioClient(timeout=60.0)
        if client.environment != "homologation":
            print("Configure VIO_ENV=homologation no .env deste projeto.")
            return 2
        if not client.api_key or not client.api_key.startswith("vio_test_"):
            print("Configure uma chave de teste VIO com prefixo vio_test_; nenhuma chamada foi enviada.")
            return 2

        result = client.read_qrcode(image_path)
    except VioApiError as exc:
        print(f"Falha na leitura VIO: {type(exc).__name__}: {exc}")
        return 1

    if not isinstance(result, dict):
        print(f"Resposta inesperada: {type(result).__name__}")
        return 1

    status = result.get("status")
    print(f"status={status}; id_presente={bool(result.get('id'))}")
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
