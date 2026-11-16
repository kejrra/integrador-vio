# Projeto consumidor de exemplo

Projeto mínimo que instala a biblioteca `vio-api` a partir da raiz deste repositório e a usa como uma aplicação independente. O arquivo `.env` fica neste diretório consumidor; o cliente lê as variáveis do diretório de trabalho atual.

## Preparar ambiente

No PowerShell, a partir da raiz do repositório:

```powershell
Set-Location examples/consumer-smoke
Copy-Item .env.example .env
```

Edite `.env` e informe a chave de teste de homologação da VIO. O `.env` é ignorado pelo Git.

## Executar

Use uma das imagens locais de homologação como padrão:

```powershell
uv run python read_smoke_test.py
```

Ou indique outro caminho de imagem/PDF:

```powershell
uv run python read_smoke_test.py ../../tests/tests-files/documentos/cnh-valido.png
```

O programa faz uma leitura em homologação, espera o resultado por até 60 segundos e imprime somente o status e a presença do ID, sem exibir a chave ou os dados extraídos do documento. O cenário padrão espera `completed`.
