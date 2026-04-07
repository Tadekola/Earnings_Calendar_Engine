from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


class EarningsEngineError(Exception):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class ProviderError(EarningsEngineError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class ProviderAuthError(ProviderError):
    pass


class StaleDataError(EarningsEngineError):
    pass


class DataUnavailableError(EarningsEngineError):
    pass


class ScanPipelineError(EarningsEngineError):
    pass


class TradeConstructionError(EarningsEngineError):
    pass


class ScoringError(EarningsEngineError):
    pass


class ConfigurationError(EarningsEngineError):
    pass


class LiquidityError(EarningsEngineError):
    pass


class UniverseError(EarningsEngineError):
    pass


def raise_not_found(resource: str, identifier: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} not found: {identifier}",
    )


def raise_bad_request(message: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=message,
    )


def raise_service_unavailable(message: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=message,
    )
