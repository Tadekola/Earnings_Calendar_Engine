"""Shared Tradier price-fallback helper.

Index products (XSP, RUT, SPX) are not covered by FMP's quote endpoint;
Tradier is. Both the scan pipeline and the trade builder need this
fallback, so we keep one implementation here.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

from app.core.logging import get_logger
from app.providers.base import PriceRecord, ProviderMeta
from app.providers.registry import ProviderRegistry

logger = get_logger(__name__)


def _f(v, default: float = 0.0) -> float:
    """Coerce None-or-missing Tradier numeric field to float safely."""
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


async def get_tradier_fallback_price(
    registry: ProviderRegistry, ticker: str
) -> PriceRecord | None:
    """Fallback price lookup via Tradier /markets/quotes.

    Returns None if:
      * Options provider isn't Tradier (mock / different backend)
      * Tradier responds but all price fields are null / ≤ 0
      * Any exception during the request
    """
    from app.providers.live.tradier import TradierOptionsProvider

    options_provider = registry.options
    if not isinstance(options_provider, TradierOptionsProvider):
        return None

    try:
        data = await options_provider._request(
            "/markets/quotes", {"symbols": ticker.upper()}
        )
        quotes = (data.get("quotes") or {}).get("quote", {})
        if isinstance(quotes, list):
            quotes = quotes[0] if quotes else {}

        last = (
            _f(quotes.get("last"))
            or _f(quotes.get("close"))
            or _f(quotes.get("prevclose"))
        )
        if last <= 0:
            return None

        return PriceRecord(
            ticker=ticker.upper(),
            trade_date=date.today(),
            open=_f(quotes.get("open"), last),
            high=_f(quotes.get("high"), last),
            low=_f(quotes.get("low"), last),
            close=last,
            volume=int(_f(quotes.get("volume"))),
            avg_dollar_volume=(
                _f(quotes.get("average_volume")) * last
                if quotes.get("average_volume")
                else None
            ),
            meta=ProviderMeta(
                source_name="tradier_quote_fallback",
                freshness_timestamp=datetime.now(UTC),
                confidence_score=0.85,
            ),
        )
    except Exception as e:
        logger.debug("tradier_fallback_price_failed", ticker=ticker, error=str(e))
        return None
