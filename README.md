# vio-api

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen)](pyproject.toml)
[![uv](https://img.shields.io/badge/package%20manager-uv-6b4fbb)](https://docs.astral.sh/uv/)

Cliente Python síncrono e sem dependências de terceiros para integrar aplicações à [API VIO](https://vio.api.br/), que realiza leitura e validação de documentos oficiais, como CNH, CRLV e ATPV-e.

## Requisitos

- Python 3.10 ou superior
- Uma chave de API VIO
- `uv` ou `pip`

## Instalação

No projeto que utilizará a biblioteca, instale pelo índice Python:

```bash
uv add vio-api
# ou
pip install vio-api
```

Para desenvolver a biblioteca a partir deste repositório:

```bash
uv sync
```

## Configuração

Defina as opções no ambiente ou copie `.env.example` para `.env` e preencha sua chave:

```dotenv
VIO_API_KEY=sua-chave-aqui
#VIO_BASE_URL=https://vio.api.br #Caso a base_url mude
VIO_ENV=homologation #homologation/production 
```

O cliente lê primeiro os parâmetros informados no construtor, depois `os.environ` e por último o arquivo `.env` do diretório atual. `VIO_BASE_URL` assume `https://vio.api.br` quando não informado. `VIO_ENV` aceita `production` ou `homologation` e assume `production`.

```python
from vio_api import VioClient

client = VioClient()
# Também é possível sobrescrever as configurações:
client = VioClient(api_key="minha-chave", environment="production")
```

Todas as requisições enviam a chave no header `X-API-Key`.

## Leitura em produção

`read_qrcode` aceita base64, uma data URI ou o caminho (`str` ou `pathlib.Path`) de um arquivo de imagem ou PDF. O arquivo é lido e convertido para base64 antes do envio. Em produção, o método aguarda o processamento automaticamente: consulta o resultado a cada segundo, por até 15 segundos por padrão. Esses valores podem ser ajustados no cliente ou na chamada.

```python
from pathlib import Path
from vio_api import VioClient

client = VioClient()  # poll_interval=1.0 e timeout=15.0 por padrão
resultado = client.read_qrcode(Path("documento.pdf"))

if resultado.get("status") == "processing":
    # O prazo terminou; o ID e o último status permitem consultar depois.
    resultado = client.get_result(resultado["id"])
else:
    print(resultado)
```

Para fornecer uma imagem já codificada, passe a string base64. Para receber o ID imediatamente sem polling, use `wait=False`:

```python
resultado = client.read_qrcode("iVBORw0KGgo...", wait=False)
print(resultado["id"])
```

O timeout não lança exceção: se a API ainda indicar `processing`, o método devolve o último payload, incluindo o `id`, para consulta posterior.

## Consultas de produção

```python
resultado = client.get_result("id-da-leitura")
historico = client.get_history(page=1, per_page=20, status="completed")
estatisticas = client.get_stats(period="month")
```

Os argumentos de `get_history` e `get_stats` são enviados como query parameters; filtros disponíveis dependem da API.

## Homologação

Configure `VIO_ENV=homologation` ou passe `environment="homologation"`. Os métodos específicos abaixo são bloqueados em produção e lançam `VioEnvironmentError`.

```python
from vio_api import VioClient

client = VioClient(environment="homologation")

# Leitura e consulta individual também estão disponíveis em homologação.
leitura = client.read_qrcode("base64-da-imagem", wait=False)
resultado = client.get_result(leitura["id"])

# Endpoints adicionais de homologação
resultados = client.get_results(["id-1", "id-2"])
foto = client.get_photo("id-da-extracao")  # bytes de imagem ou JSON
face = client.get_face("id-da-extracao")   # bytes de imagem ou JSON
saldo = client.get_balance()
```

### Executar os cenários de homologação

O repositório inclui imagens de teste em `tests/tests-files/` e seus resultados esperados em `cenarios.json`. Para executar o runner, use o ambiente de homologação e uma chave de teste VIO com prefixo `vio_test_`. O script recusa outras chaves para evitar enviar as imagens de cenário por engano com uma chave de produção.

Configure o `.env` na raiz do projeto:

```dotenv
VIO_API_KEY=vio_test_sua-chave-de-homologacao
VIO_ENV=homologation
VIO_BASE_URL=https://vio.api.br
```

Execute a partir da raiz do repositório. Primeiro, rode alguns cenários para confirmar a configuração; depois, rode o conjunto completo:

```bash
uv run python tests/run_homologation_scenarios.py --limit 5
uv run python tests/run_homologation_scenarios.py
```

O runner envia as imagens em sequência, aguarda o resultado de cada leitura e compara o status com o esperado em `cenarios.json`. O polling usa intervalo de 1 segundo e timeout de 60 segundos por cenário por padrão. É possível filtrar o conjunto ou ajustar esses valores:

```bash
uv run python tests/run_homologation_scenarios.py --group geral
uv run python tests/run_homologation_scenarios.py --group documento --timeout 120 --poll-interval 2
```

O conjunto atual contém 358 cenários. Os resultados esperados são 179 leituras `completed`, 177 `failed`, uma resposta HTTP 402 no cenário de saldo insuficiente e uma leitura que passa de `processing` para `completed`. A resposta HTTP 402 desse cenário conta como aprovação. O runner mostra o progresso e, ao final, lista apenas os códigos e status divergentes; não imprime a chave nem os dados extraídos dos documentos.

Uma execução completa bem-sucedida termina com:

```text
Resultado: 358/358 aprovados; 0 divergência(s).
```

O processo termina com código `0` quando todos os cenários passam, `1` quando há divergências e `2` quando há erro de configuração, autenticação ou conexão. A documentação em `tests/tests-files/LEIA-ME.txt` descreve a finalidade das imagens de homologação.

### Exemplo de projeto consumidor

O diretório [`examples/consumer-smoke`](examples/consumer-smoke/) contém um projeto `uv` separado que instala esta biblioteca pelo caminho local e executa uma leitura de homologação. O `.env` deve ser criado nesse diretório, pois a biblioteca lê a configuração do diretório de trabalho atual do processo. Consulte o [README do exemplo](examples/consumer-smoke/README.md) para executar.

## Métodos e exceções

| Método | Endpoint | Ambiente | Retorno |
|---|---|---|---|
| `read_qrcode(image, wait=True, poll_interval=None, timeout=None)` | `POST /api/qrcode/read`; polling em `GET /api/qrcode/result/{id}` | Produção e homologação | JSON do resultado ou payload ainda em processamento |
| `get_result(id)` | `GET /api/qrcode/result/{id}` | Produção e homologação | JSON |
| `get_history(**params)` | `GET /api/qrcode/history` | Produção | JSON |
| `get_stats(**params)` | `GET /api/qrcode/stats` | Produção | JSON |
| `get_results(ids)` | `POST /api/qrcode/results` | Homologação | JSON |
| `get_photo(extract_id)` | `GET /api/qrcode/photo/{extract_id}` | Homologação | Bytes de imagem ou JSON |
| `get_face(id)` | `GET /api/qrcode/face/{id}` | Homologação | Bytes de imagem ou JSON |
| `get_balance()` | `GET /api/balance/` | Homologação | JSON |

| Exceção | Significado |
|---|---|
| `VioApiError` | Classe base para falhas de API ou comunicação |
| `VioBadRequestError` | HTTP 400 — requisição inválida |
| `VioUnauthorizedError` | HTTP 401 — chave ausente ou inválida |
| `VioPaymentRequiredError` | HTTP 402 — pagamento/créditos necessários |
| `VioNotFoundError` | HTTP 404 — recurso não encontrado |
| `VioEnvironmentError` | Método exclusivo chamado em ambiente incompatível |

Outros erros HTTP e falhas de rede também são reportados como `VioApiError`.

## Desenvolvimento

Os testes usam apenas `unittest` e `unittest.mock`:

```bash
uv run python -m unittest discover -s tests -v
```

## Licença

MIT.
