"""Exceções públicas da biblioteca vio-api."""


class VioApiError(Exception):
    """Erro base para falhas de comunicação ou respostas da API VIO."""


class VioBadRequestError(VioApiError):
    """A API rejeitou a requisição (HTTP 400)."""


class VioUnauthorizedError(VioApiError):
    """A chave de API está ausente ou inválida (HTTP 401)."""


class VioPaymentRequiredError(VioApiError):
    """A conta precisa de créditos ou regularização (HTTP 402)."""


class VioNotFoundError(VioApiError):
    """O recurso solicitado não foi encontrado (HTTP 404)."""


class VioEnvironmentError(VioApiError):
    """O método não está disponível no ambiente configurado."""
