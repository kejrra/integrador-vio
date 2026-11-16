"""Executa cenários de leitura VIO usando as imagens de homologação do repositório.

Uso a partir da raiz do projeto:
    uv run python tests/run_homologation_scenarios.py
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError

from vio_api import (
    VioApiError,
    VioBadRequestError,
    VioClient,
    VioNotFoundError,
    VioPaymentRequiredError,
    VioUnauthorizedError,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_ROOT = PROJECT_ROOT / "tests" / "tests-files"
SCENARIOS_FILE = FIXTURES_ROOT / "cenarios.json"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Roda os cenários de leitura usando a API VIO em homologação."
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Executa somente os primeiros N cenários (útil para uma chamada inicial).",
    )
    parser.add_argument(
        "--group", choices=("geral", "documento"), default=None,
        help="Filtra pelo grupo indicado no cenarios.json.",
    )
    parser.add_argument(
        "--timeout", type=float, default=60.0,
        help="Tempo máximo de polling por cenário, em segundos (padrão: 60).",
    )
    parser.add_argument(
        "--poll-interval", type=float, default=1.0,
        help="Intervalo entre consultas de resultado (padrão: 1 segundo).",
    )
    return parser.parse_args()


def _load_scenarios(group: Optional[str], limit: Optional[int]) -> List[Dict[str, Any]]:
    with SCENARIOS_FILE.open("r", encoding="utf-8") as scenario_file:
        scenarios = json.load(scenario_file)
    if not isinstance(scenarios, list):
        raise ValueError("cenarios.json deve conter uma lista de cenários.")
    if group is not None:
        scenarios = [scenario for scenario in scenarios if scenario.get("group") == group]
    if limit is not None:
        if limit < 0:
            raise ValueError("--limit deve ser maior ou igual a zero.")
        scenarios = scenarios[:limit]
    return scenarios


def _scenario_image(scenario: Dict[str, Any]) -> Path:
    relative_path = Path(str(scenario["file"]))
    root = FIXTURES_ROOT.resolve()
    image_path = (root / relative_path).resolve()
    try:
        image_path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Caminho fora da pasta de fixtures: {scenario.get('code', '?')}") from exc
    if not image_path.is_file():
        raise FileNotFoundError(f"Imagem ausente para o cenário {scenario.get('code', '?')}.")
    return image_path


def _actual_result(client: VioClient, image_path: Path, timeout: float) -> Tuple[str, bool]:
    try:
        result = client.read_qrcode(image_path, wait=True, timeout=timeout)
    except VioUnauthorizedError:
        raise RuntimeError("Autenticação recusada (HTTP 401); execução interrompida.")
    except VioPaymentRequiredError:
        return "HTTP 402", False
    except VioBadRequestError:
        return "HTTP 400", False
    except VioNotFoundError:
        return "HTTP 404", False
    except VioApiError as exc:
        if isinstance(exc.__cause__, URLError):
            raise RuntimeError(
                "Falha de conexão com a API; execução interrompida para evitar repetir chamadas."
            ) from exc
        raise RuntimeError(
            f"Erro da API ({type(exc).__name__}); execução interrompida."
        ) from exc

    if not isinstance(result, dict):
        return type(result).__name__, False
    status = str(result.get("status", "sem status"))
    return status, status == "processing"


def main() -> int:
    args = _arguments()
    if args.timeout < 0 or args.poll_interval < 0:
        print("ERRO: timeout e poll-interval precisam ser maiores ou iguais a zero.")
        return 2

    try:
        client = VioClient(poll_interval=args.poll_interval, timeout=args.timeout)
        if client.environment != "homologation":
            print("ERRO: configure VIO_ENV=homologation no .env ou no ambiente.")
            return 2
        if not client.api_key or not client.api_key.startswith("vio_test_"):
            print("ERRO: a chave não parece ser de teste (prefixo vio_test_); nenhuma chamada foi enviada.")
            return 2
        scenarios = _load_scenarios(args.group, args.limit)
        for scenario in scenarios:
            _scenario_image(scenario)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERRO de configuração/fixtures: {exc}")
        return 2

    print(f"Homologação VIO: {len(scenarios)} cenário(s); chave não exibida.", flush=True)
    passed = 0
    failed: List[Tuple[str, str, str]] = []
    pending: List[str] = []

    for index, scenario in enumerate(scenarios, start=1):
        code = str(scenario.get("code", f"cenario-{index}"))
        expected = str(scenario.get("expected", ""))
        try:
            observed, still_processing = _actual_result(
                client, _scenario_image(scenario), args.timeout
            )
        except (RuntimeError, OSError, ValueError) as exc:
            print(f"INTERROMPIDO em {code}: {exc}")
            print(f"Resumo parcial: {passed} aprovado(s), {len(failed)} divergência(s).")
            return 2

        expected_final = "completed" if expected == "processing → completed" else expected
        if still_processing:
            pending.append(code)
            failed.append((code, expected, "processing (timeout)"))
        elif observed == expected_final:
            passed += 1
        else:
            failed.append((code, expected, observed))

        if index % 10 == 0 or index == len(scenarios):
            print(f"Progresso: {index}/{len(scenarios)}; {passed} aprovado(s).", flush=True)

    print(f"Resultado: {passed}/{len(scenarios)} aprovados; {len(failed)} divergência(s).")
    if pending:
        print("Ainda processando após timeout: " + ", ".join(pending))
    if failed:
        print("Divergências (código | esperado | recebido):")
        for code, expected, observed in failed:
            print(f"- {code} | {expected} | {observed}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
