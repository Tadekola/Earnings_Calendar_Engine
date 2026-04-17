"""
Phase A spot-check audit — cross-reference app outputs against TastyTrade.

Runs the full scan pipeline on a handful of tickers and prints every
observable metric in a table. You then manually cross-check each number
against TastyTrade (or your broker) to validate:

    * Spot price               -> quote matches
    * IV Rank                  -> VIX-derived for XSP, chain-skew for equities
    * Realized vol (10/20/30)  -> annualized log-return stdev
    * ATR (14d)                -> true ATR or H-L fallback
    * Term structure slope     -> contango (+) vs backwardation (-)
    * Front / back expiry IV   -> ATM IV for each
    * Expected move 1-sigma    -> spot * front_iv * sqrt(DTE/365)
    * Earnings date / DTE      -> earnings calendar accuracy
    * Classification + score   -> the scorer's verdict
    * Factor breakdown         -> each weighted contribution

Usage:
    docker exec earnings_calendar_engine-backend-1 python /app/scripts/audit_spot_check.py
    docker exec earnings_calendar_engine-backend-1 python /app/scripts/audit_spot_check.py XSP AAPL NVDA

The output is two tables per ticker:
    (a) Summary row with all scalar metrics
    (b) Factor breakdown with rationale

Cross-check against TastyTrade Dashboard / Watchlist for each ticker:
    - Does IV Rank on TT match ours? (expect small gap; same regime wins)
    - Does 1-sigma expected move match TT's expected-move column?
    - Does ATM strike appear correctly in our chain?
    - Does the earnings date on TT match ours?

Any mismatch > 15% is a flag worth investigating.
"""
from __future__ import annotations

import asyncio
import math
import sys
from datetime import date, timedelta

from app.core.config import Settings
from app.providers.registry import ProviderRegistry
from app.services.scan_pipeline import ScanPipeline


DEFAULT_TICKERS = ["XSP", "SPY", "AAPL", "NVDA", "MSFT"]


def fmt(v, spec: str = ".4f", na: str = "—") -> str:
    if v is None:
        return na
    try:
        return format(v, spec)
    except Exception:
        return str(v)


async def inspect_ticker(registry, settings, ticker: str) -> dict:
    """Gather every numeric we compute for this ticker."""
    ticker = ticker.upper()
    today = date.today()
    out: dict = {"ticker": ticker, "as_of": today}

    # 1. Price
    price = await registry.price.get_current_price(ticker)
    if price is None:
        # Index fallback
        from app.services.scan_pipeline import ScanPipeline as _SP

        pipe = _SP(settings, registry)
        price = await pipe._get_tradier_fallback_price(ticker)
    if price:
        out["spot"] = price.close
        out["price_source"] = price.meta.source_name if price.meta else "?"
    else:
        out["spot"] = None
        out["price_source"] = None

    # 2. Earnings
    try:
        earn = await registry.earnings.get_earnings_date(ticker)
        if earn:
            out["earnings_date"] = earn.earnings_date
            out["earnings_timing"] = earn.report_timing
            out["days_to_earnings"] = (earn.earnings_date - today).days
        else:
            out["earnings_date"] = None
    except Exception as e:
        out["earnings_date"] = f"error: {e}"

    # 3. Volatility metrics
    try:
        vol = await registry.volatility.get_volatility_metrics(ticker)
        out["iv_rank"] = vol.iv_rank
        out["iv_percentile"] = vol.iv_percentile
        out["rv_10"] = vol.realized_vol_10d
        out["rv_20"] = vol.realized_vol_20d
        out["rv_30"] = vol.realized_vol_30d
        out["atr_14"] = vol.atr_14d
        out["front_iv"] = vol.front_expiry_iv
        out["back_iv"] = vol.back_expiry_iv
        out["slope"] = vol.term_structure_slope
        out["vol_source"] = vol.meta.source_name if vol.meta else "?"
    except Exception as e:
        out["vol_error"] = str(e)

    # 4. Options chain — pick front expiry ≥ 7d and show ATM strikes
    try:
        chain = await registry.options.get_options_chain(ticker)
        exps = sorted(chain.expirations) if chain.expirations else []
        future = [e for e in exps if e > today]
        front = next((e for e in future if (e - today).days >= 7), future[0] if future else None)
        out["expirations_count"] = len(future)
        out["front_expiry"] = front
        if front:
            out["front_dte"] = (front - today).days
            spot = out.get("spot") or chain.spot_price
            # Find ATM call and put
            front_opts = [o for o in chain.options if o.expiration == front]
            if spot and front_opts:
                atm_call = min(
                    (o for o in front_opts if o.option_type == "call"),
                    key=lambda o: abs(o.strike - spot),
                    default=None,
                )
                atm_put = min(
                    (o for o in front_opts if o.option_type == "put"),
                    key=lambda o: abs(o.strike - spot),
                    default=None,
                )
                if atm_call:
                    out["atm_call_strike"] = atm_call.strike
                    out["atm_call_bid"] = atm_call.bid
                    out["atm_call_ask"] = atm_call.ask
                    out["atm_call_iv"] = atm_call.implied_volatility
                    out["atm_call_delta"] = atm_call.delta
                if atm_put:
                    out["atm_put_strike"] = atm_put.strike
                    out["atm_put_bid"] = atm_put.bid
                    out["atm_put_ask"] = atm_put.ask
                    out["atm_put_iv"] = atm_put.implied_volatility
                    out["atm_put_delta"] = atm_put.delta
        out["chain_source"] = chain.meta.source_name if chain.meta else "?"
    except Exception as e:
        out["chain_error"] = str(e)

    # 5. Expected move (1-sigma) using front IV and DTE
    spot = out.get("spot")
    dte = out.get("front_dte")
    fiv = out.get("front_iv")
    if spot and dte and fiv:
        em = spot * fiv * math.sqrt(dte / 365.0)
        out["expected_move_1sigma"] = round(em, 2)
        out["expected_move_pct"] = round(em / spot * 100, 2)

    return out


async def run_scan(settings, registry, tickers: list[str]) -> dict[str, any]:
    """Run the full pipeline on this ticker set and index results by ticker."""
    pipeline = ScanPipeline(settings, registry)
    result = await pipeline.run(tickers=tickers)
    return {r.ticker: r for r in result.results}


def print_metrics_table(m: dict) -> None:
    t = m["ticker"]
    print(f"\n{'='*78}")
    print(f" {t}  —  spot ${fmt(m.get('spot'), '.2f')}   "
          f"source: {m.get('price_source')}")
    print("=" * 78)

    # Core metrics — cross-check columns
    rows = [
        ("Spot price",              f"${fmt(m.get('spot'), '.2f')}",     "TT: Last/Size column"),
        ("Earnings date",           fmt(m.get('earnings_date'), ''),      f"TT: next earnings call ({fmt(m.get('days_to_earnings'), 'd')} days out)"),
        ("IV Rank",                 f"{fmt((m.get('iv_rank') or 0)*100, '.1f')}%", "TT: IV Rank header"),
        ("IV Percentile",           f"{fmt((m.get('iv_percentile') or 0)*100, '.1f')}%", "TT: IV Pctile (if shown)"),
        ("Realized Vol 10d (ann.)", f"{fmt((m.get('rv_10') or 0)*100, '.1f')}%", "TT/other: HV-10"),
        ("Realized Vol 20d (ann.)", f"{fmt((m.get('rv_20') or 0)*100, '.1f')}%", "HV-20"),
        ("Realized Vol 30d (ann.)", f"{fmt((m.get('rv_30') or 0)*100, '.1f')}%", "HV-30"),
        ("ATR 14d (absolute $)",    f"${fmt(m.get('atr_14'), '.2f')}",   "TT: not shown directly"),
        ("Front expiry",            fmt(m.get('front_expiry'), ''),       f"DTE = {fmt(m.get('front_dte'), 'd')}"),
        ("Front expiry IV (ATM)",   f"{fmt((m.get('front_iv') or 0)*100, '.1f')}%", "TT chain page: front IV"),
        ("Back expiry IV (ATM)",    f"{fmt((m.get('back_iv') or 0)*100, '.1f')}%",  "TT chain page: back IV"),
        ("Term structure slope",    f"{fmt(m.get('slope'), '+.4f')}",   ">0 contango, <0 backwardation"),
        ("Expected move 1-σ ($)",   f"±${fmt(m.get('expected_move_1sigma'), '.2f')}", "TT: Expected Move column"),
        ("Expected move 1-σ (%)",   f"±{fmt(m.get('expected_move_pct'), '.2f')}%",   ""),
        ("ATM call strike",         fmt(m.get('atm_call_strike'), '.2f'), ""),
        ("ATM call bid/ask",        f"{fmt(m.get('atm_call_bid'), '.2f')} / {fmt(m.get('atm_call_ask'), '.2f')}", ""),
        ("ATM call IV",             f"{fmt((m.get('atm_call_iv') or 0)*100, '.1f')}%", ""),
        ("ATM call delta",          fmt(m.get('atm_call_delta'), '.3f'), ""),
        ("ATM put strike",          fmt(m.get('atm_put_strike'), '.2f'), ""),
        ("ATM put bid/ask",         f"{fmt(m.get('atm_put_bid'), '.2f')} / {fmt(m.get('atm_put_ask'), '.2f')}", ""),
        ("ATM put IV",              f"{fmt((m.get('atm_put_iv') or 0)*100, '.1f')}%", ""),
        ("ATM put delta",           fmt(m.get('atm_put_delta'), '.3f'), ""),
        ("Expirations in chain",    fmt(m.get('expirations_count'), 'd'), ""),
    ]
    for label, val, hint in rows:
        print(f"  {label:28s}  {val:20s}  {hint}")


def print_scan_result(ticker: str, r) -> None:
    print(f"\n  ── Scan Pipeline Verdict ──────────────────────────")
    print(f"  classification:  {r.classification}")
    print(f"  score:           {fmt(r.overall_score, '.1f')}")
    print(f"  strategy:        {r.strategy_type}")
    print(f"  layer:           {r.layer_id}")
    print(f"  stage reached:   {r.stage_reached}")
    if r.rejection_reasons:
        print(f"  rejections:      {r.rejection_reasons}")
    if r.scoring_result and r.scoring_result.factors:
        print(f"  ── Factor Breakdown ─────────────────────────────")
        total = 0.0
        for f in r.scoring_result.factors:
            total += f.weighted_score
            print(f"    {f.name:30s} raw={f.raw_score:6.1f}  wt={f.weight:5.1f}  "
                  f"→ wtd={f.weighted_score:6.2f}")
            print(f"      {f.rationale}")
        print(f"    {'SUM of weighted':30s} {'':14s}                     {total:6.2f}")
        # Invariant check: sum of weighted should equal overall
        diff = abs(total - (r.overall_score or 0))
        if diff > 0.5:
            print(f"    ⚠️  INVARIANT VIOLATION: sum({total:.2f}) != overall({r.overall_score})")
    if r.scoring_result and r.scoring_result.risk_warnings:
        print(f"  ── Risk Warnings ────────────────────────────────")
        for w in r.scoring_result.risk_warnings:
            print(f"    • {w}")


def sanity_check_invariants(m: dict) -> list[str]:
    """Return a list of any obvious issues with the computed values."""
    warnings = []
    ivr = m.get("iv_rank")
    if ivr is not None and (ivr < 0 or ivr > 1):
        warnings.append(f"IV Rank out of [0,1]: {ivr}")
    for k in ["rv_10", "rv_20", "rv_30"]:
        v = m.get(k)
        if v is not None and (v < 0 or v > 3.0):  # 300% annualized sanity
            warnings.append(f"{k} out of sane range [0, 3.0]: {v}")
    slope = m.get("slope")
    if slope is not None and abs(slope) > 1.0:
        warnings.append(f"term slope magnitude > 1: {slope}")
    # ATR should be positive and < 20% of spot
    atr, spot = m.get("atr_14"), m.get("spot")
    if atr is not None and spot and atr / spot > 0.20:
        warnings.append(f"ATR/spot > 20% — implausibly volatile: {atr/spot:.2%}")
    # Expected move positive
    em = m.get("expected_move_1sigma")
    if em is not None and em <= 0:
        warnings.append(f"expected_move_1sigma non-positive: {em}")
    # IV rank and IV percentile should be somewhat consistent
    ivp = m.get("iv_percentile")
    if ivr is not None and ivp is not None and abs(ivr - ivp) > 0.5:
        warnings.append(
            f"IV Rank ({ivr:.2f}) and IV Pctile ({ivp:.2f}) diverge by >50pp — "
            "worth a closer look"
        )
    return warnings


async def main(tickers: list[str]) -> None:
    settings = Settings()
    registry = ProviderRegistry(settings)
    registry.initialize()

    print(f"\n╔{'═'*76}╗")
    print(f"║ PHASE A — Spot-Check Audit  ({len(tickers)} tickers)"
          f"{' ' * (76 - 36 - len(str(len(tickers))))}║")
    print(f"║ Compare each metric below against TastyTrade / your broker"
          f"{' ' * (76 - 60)}║")
    print(f"╚{'═'*76}╝")

    # 1. Gather observables per ticker
    metrics_by_ticker: dict = {}
    for t in tickers:
        print(f"\n  Gathering observables for {t}...")
        m = await inspect_ticker(registry, settings, t)
        metrics_by_ticker[t.upper()] = m

    # 2. Run scan pipeline once on full list
    print(f"\n  Running scan pipeline on {tickers}...")
    scan_results = await run_scan(settings, registry, tickers)

    # 3. Print per-ticker report
    all_warnings: dict[str, list[str]] = {}
    for t in tickers:
        T = t.upper()
        m = metrics_by_ticker.get(T, {"ticker": T})
        print_metrics_table(m)
        if T in scan_results:
            print_scan_result(T, scan_results[T])
        w = sanity_check_invariants(m)
        if w:
            all_warnings[T] = w

    # 4. Summary of invariant violations
    print(f"\n\n{'='*78}")
    print(" INVARIANT SUMMARY")
    print("=" * 78)
    if not all_warnings:
        print("  ✅ All tickers pass basic sanity checks.")
    else:
        print("  ⚠️  Items to investigate:")
        for t, ws in all_warnings.items():
            print(f"\n   {t}:")
            for w in ws:
                print(f"      • {w}")

    print(f"\n{'='*78}")
    print(" NEXT STEP — Manual Cross-Check")
    print("=" * 78)
    print("""
  For each ticker above:
    1. Open the ticker on TastyTrade
    2. Compare the 'Spot price' — should match to the cent (intraday)
    3. Compare 'IV Rank' — small differences OK, >15pp gap is a bug
    4. Compare 'Expected move' — should match TT's Expected Move column
    5. Compare 'Front expiry IV' — check against the chain's IV%
    6. Note the earnings date TT shows — compare to 'Earnings date' above

  ANY metric off by >15% from TastyTrade is a bug worth investigating.
  Report mismatches with the ticker name and both numbers.
""")


if __name__ == "__main__":
    tickers = sys.argv[1:] or DEFAULT_TICKERS
    asyncio.run(main(tickers))
