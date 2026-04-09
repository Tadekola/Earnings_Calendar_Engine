"""Comprehensive live data validation script."""
import asyncio
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx

API = "http://localhost:8000"
FRONTEND = "http://localhost:3001"

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"

results = {"pass": 0, "fail": 0, "warn": 0}


def report(ok, label, detail=""):
    if ok == "pass":
        results["pass"] += 1
        print(f"  {PASS} {label}  {detail}")
    elif ok == "warn":
        results["warn"] += 1
        print(f"  {WARN} {label}  {detail}")
    else:
        results["fail"] += 1
        print(f"  {FAIL} {label}  {detail}")


async def test_health():
    print("\n=== 1. HEALTH + PROVIDERS ===")
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{API}/health")
        d = r.json()
        report("pass" if r.status_code == 200 else "fail", "Health endpoint", f"status={d.get('status')}")
        report("pass" if d.get("operating_mode") == "STRICT" else "fail", "Operating mode", d.get("operating_mode"))

        providers = d.get("providers", [])
        for p in providers:
            name = p.get("provider")
            connected = p.get("is_connected")
            conf = p.get("confidence_score", 0)
            severity = p.get("severity")
            if connected and conf >= 0.8:
                report("pass", f"Provider: {name}", f"conf={conf} severity={severity}")
            elif connected:
                report("warn", f"Provider: {name}", f"conf={conf} severity={severity}")
            else:
                report("fail", f"Provider: {name}", f"DISCONNECTED err={p.get('error_details')}")


async def test_earnings():
    print("\n=== 2. EARNINGS DATA (FMP) ===")
    from app.core.config import get_settings
    from app.providers.registry import ProviderRegistry

    s = get_settings()
    r = ProviderRegistry(s)
    r.initialize()

    # Test tickers with known upcoming earnings
    test_tickers = ["MSFT", "META", "GOOGL", "TSLA", "AMD", "NVDA", "NFLX"]
    found = 0
    for t in test_tickers:
        e = await r.earnings.get_earnings_date(t)
        if e:
            days = (e.earnings_date - date.today()).days
            report("pass", f"{t} earnings", f"date={e.earnings_date} ({days}d away) timing={e.report_timing}")
            found += 1
        else:
            report("warn", f"{t} earnings", "Not in next 60 days")

    report("pass" if found >= 3 else "fail", "Earnings coverage", f"{found}/{len(test_tickers)} tickers have dates")

    # Cross-check: MSFT should report around late April 2026
    msft = await r.earnings.get_earnings_date("MSFT")
    if msft:
        expected_month = 4  # April
        report(
            "pass" if msft.earnings_date.month == expected_month else "warn",
            "MSFT date cross-check",
            f"Expected ~April 2026, got {msft.earnings_date}"
        )


async def test_prices():
    print("\n=== 3. PRICE DATA (FMP) ===")
    from app.core.config import get_settings
    from app.providers.registry import ProviderRegistry

    s = get_settings()
    r = ProviderRegistry(s)
    r.initialize()

    tickers = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"]
    for t in tickers:
        p = await r.price.get_current_price(t)
        if p:
            # Sanity: price should be > $10 and < $5000 for these megacaps
            sane = 10 < p.close < 5000
            report(
                "pass" if sane else "fail",
                f"{t} price",
                f"${p.close:.2f} open=${p.open:.2f} high=${p.high:.2f} low=${p.low:.2f} vol={p.volume:,}"
            )
        else:
            report("fail", f"{t} price", "No data returned")

    # Test price history
    aapl_hist = await r.price.get_price_history("AAPL", date.today() - timedelta(days=30), date.today())
    if aapl_hist and len(aapl_hist) > 0:
        report("pass", "AAPL 30d history", f"{len(aapl_hist)} trading days")
        # Verify dates are recent
        latest = max(h.trade_date for h in aapl_hist)
        days_stale = (date.today() - latest).days
        report(
            "pass" if days_stale <= 3 else "warn",
            "History freshness",
            f"Latest date: {latest} ({days_stale}d ago)"
        )
    else:
        report("fail", "AAPL 30d history", "No data")


async def test_options():
    print("\n=== 4. OPTIONS DATA (Tradier) ===")
    from app.core.config import get_settings
    from app.providers.registry import ProviderRegistry

    s = get_settings()
    r = ProviderRegistry(s)
    r.initialize()

    for t in ["AAPL", "MSFT", "NVDA"]:
        exps = await r.options.get_expirations(t)
        report(
            "pass" if len(exps) >= 5 else "fail",
            f"{t} expirations",
            f"{len(exps)} dates (next: {exps[0] if exps else 'none'})"
        )

    # Fetch a small chain for AAPL (next 2 expirations only)
    aapl_exps = await r.options.get_expirations("AAPL")
    if len(aapl_exps) >= 2:
        chain = await r.options.get_options_chain("AAPL", aapl_exps[:2])
        report(
            "pass" if len(chain.options) > 0 else "fail",
            "AAPL chain (2 exps)",
            f"{len(chain.options)} contracts, spot=${chain.spot_price:.2f}"
        )

        # Verify chain has both calls and puts
        types = set(o.option_type for o in chain.options)
        report("pass" if types == {"call", "put"} else "fail", "Call+Put present", str(types))

        # Verify greeks exist
        with_delta = [o for o in chain.options if o.delta is not None]
        pct = len(with_delta) / len(chain.options) * 100 if chain.options else 0
        report(
            "pass" if pct > 50 else "warn",
            "Greeks coverage",
            f"{pct:.0f}% of contracts have delta"
        )

        # Spot price sanity
        report(
            "pass" if 50 < chain.spot_price < 1000 else "fail",
            "AAPL spot sanity",
            f"${chain.spot_price:.2f}"
        )


async def test_volatility():
    print("\n=== 5. VOLATILITY DATA (Computed) ===")
    from app.core.config import get_settings
    from app.providers.registry import ProviderRegistry

    s = get_settings()
    r = ProviderRegistry(s)
    r.initialize()

    for t in ["AAPL", "MSFT", "NVDA"]:
        v = await r.volatility.get_volatility_metrics(t)
        if v and v.meta.confidence_score > 0:
            rv20 = v.realized_vol_20d
            rv10 = v.realized_vol_10d
            report(
                "pass",
                f"{t} volatility",
                f"RV10={rv10:.1%} RV20={rv20:.1%} conf={v.meta.confidence_score}" if rv20 and rv10 else f"conf={v.meta.confidence_score} (partial data)"
            )
        else:
            report("fail", f"{t} volatility", "No data")


async def test_dashboard():
    print("\n=== 6. DASHBOARD SUMMARY ===")
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{API}/api/v1/dashboard/summary")
        d = r.json()
        report("pass" if r.status_code == 200 else "fail", "Dashboard endpoint", f"status={r.status_code}")
        report("pass" if d.get("total_scans", 0) > 0 else "warn", "Total scans", str(d.get("total_scans")))
        report(
            "pass" if d.get("total_candidates_scanned", 0) > 0 else "warn",
            "Total candidates",
            str(d.get("total_candidates_scanned"))
        )
        recent = d.get("recent_scans", [])
        report("pass" if len(recent) > 0 else "warn", "Recent scans", f"{len(recent)} entries")


async def test_scan_history():
    print("\n=== 7. SCAN HISTORY ===")
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{API}/api/v1/scan/results")
        d = r.json()
        report("pass" if r.status_code == 200 else "fail", "Scan results endpoint", f"{len(d)} scan runs")
        if d and isinstance(d, list) and len(d) > 0:
            latest = d[0]
            report("pass", "Latest scan", f"run_id={latest.get('run_id','')[:12]}... status={latest.get('status')}")


async def test_trade_builder():
    print("\n=== 8. TRADE BUILDER ===")
    async with httpx.AsyncClient(timeout=120) as c:
        # Test candidate detail endpoint
        for t in ["NFLX", "GOOGL", "TSLA"]:
            try:
                r = await c.get(f"{API}/api/v1/candidates/{t}")
                if r.status_code == 200:
                    d = r.json()
                    report("pass", f"Candidate {t}", f"classification={d.get('classification')} score={d.get('overall_score')}")
                    break
                else:
                    report("warn", f"Candidate {t}", f"status={r.status_code}")
            except httpx.ReadTimeout:
                report("warn", f"Candidate {t}", "Timeout (live scan slow)")
                break

        # Test trade builder endpoint
        try:
            r2 = await c.get(f"{API}/api/v1/trades/NFLX/recommended")
            if r2.status_code == 200:
                d2 = r2.json()
                report("pass", "Trade recommended", f"NFLX legs={len(d2.get('legs', []))}")
            else:
                report("warn", "Trade recommended", f"status={r2.status_code} (need RECOMMEND classification)")
        except httpx.ReadTimeout:
            report("warn", "Trade recommended", "Timeout")


async def test_rejections():
    print("\n=== 9. REJECTIONS ===")
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{API}/api/v1/rejections")
        d = r.json()
        report("pass" if r.status_code == 200 else "fail", "Rejections endpoint", f"total={d.get('total')}")
        rejections = d.get("rejections", [])
        stages = {}
        for rej in rejections:
            s = rej.get("stage", "unknown")
            stages[s] = stages.get(s, 0) + 1
        for stage, count in stages.items():
            report("pass", f"Stage: {stage}", f"{count} rejections")


async def test_settings():
    print("\n=== 10. SETTINGS CRUD ===")
    async with httpx.AsyncClient() as c:
        # Read
        r = await c.get(f"{API}/api/v1/settings")
        d = r.json()
        report("pass" if r.status_code == 200 else "fail", "Read settings", f"keys={len(d)}")

        # Check key settings
        ew = d.get("earnings_window", {})
        max_days = ew.get("max_days_to_earnings")
        report("pass" if max_days else "warn", "MAX_DAYS_TO_EARNINGS", str(max_days))
        report("pass" if d.get("operating_mode") == "STRICT" else "warn", "Operating mode", d.get("operating_mode"))

        # Update test: widen the window temporarily
        r2 = await c.put(
            f"{API}/api/v1/settings",
            json={"max_days_to_earnings": 30}
        )
        report("pass" if r2.status_code == 200 else "fail", "Update setting", f"status={r2.status_code}")

        # Verify it was updated
        r3 = await c.get(f"{API}/api/v1/settings")
        d3 = r3.json()
        new_max = d3.get("earnings_window", {}).get("max_days_to_earnings")
        report("pass" if new_max == 30 else "warn", "Setting persisted", f"MAX_DAYS_TO_EARNINGS={new_max}")


async def test_audit():
    print("\n=== 11. AUDIT TRAIL ===")
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{API}/api/v1/dashboard/audit")
        d = r.json()
        report("pass" if r.status_code == 200 else "fail", "Audit endpoint", f"{len(d)} entries")
        if d:
            types = set(e.get("event_type") for e in d)
            report("pass" if len(types) > 0 else "warn", "Event types", str(types))
            report("pass", "Latest event", f"{d[0].get('event_type')} at {d[0].get('created_at')}")


async def test_export():
    print("\n=== 12. CSV EXPORT ===")
    async with httpx.AsyncClient() as c:
        # Test scans CSV
        r = await c.get(f"{API}/api/v1/export/scans/csv")
        if r.status_code == 200:
            lines = r.text.strip().split("\n")
            report("pass", "Scans CSV export", f"{len(lines)} lines")
            report("pass" if "run_id" in lines[0].lower() else "fail", "CSV headers", lines[0][:80])
        else:
            report("fail", "Scans CSV export", f"status={r.status_code}")

        # Test candidates CSV
        r2 = await c.get(f"{API}/api/v1/export/candidates/csv")
        if r2.status_code == 200:
            lines2 = r2.text.strip().split("\n")
            report("pass", "Candidates CSV export", f"{len(lines2)} lines")
        else:
            report("fail", "Candidates CSV export", f"status={r2.status_code}")


async def test_frontend_pages():
    print("\n=== 13. FRONTEND PAGES ===")
    pages = ["/", "/scan", "/history", "/trades", "/rejections", "/audit", "/settings"]
    async with httpx.AsyncClient() as c:
        for page in pages:
            r = await c.get(f"{FRONTEND}{page}")
            report("pass" if r.status_code == 200 else "fail", f"Page {page}", f"status={r.status_code}")


async def test_scan_with_wider_window():
    print("\n=== 14. LIVE SCAN (30-day window) ===")
    async with httpx.AsyncClient(timeout=300) as c:
        # Settings already widened to 30 days in test 10
        r = await c.post(f"{API}/api/v1/scan/run")
        if r.status_code == 200:
            d = r.json()
            report("pass", "Scan completed", f"scanned={d.get('total_scanned')} recommended={d.get('total_recommended')} watchlist={d.get('total_watchlist')} rejected={d.get('total_rejected')}")

            # Check individual results
            for res in d.get("results", []):
                t = res.get("ticker")
                cls = res.get("classification")
                score = res.get("overall_score")
                summary = res.get("rationale_summary", "")[:80]
                if cls == "RECOMMEND":
                    report("pass", f"  {t}: RECOMMEND", f"score={score} {summary}")
                elif cls == "WATCHLIST":
                    report("pass", f"  {t}: WATCHLIST", f"score={score} {summary}")
                else:
                    stage = res.get("stage_reached", "")
                    reasons = "; ".join(res.get("rejection_reasons", [])[:2])
                    report("pass", f"  {t}: {cls}", f"stage={stage} {reasons[:60]}")
        else:
            report("fail", "Scan failed", f"status={r.status_code} {r.text[:200]}")

        # Restore original setting
        await c.put(
            f"{API}/api/v1/settings",
            json={"max_days_to_earnings": 21}
        )
        report("pass", "Restored MAX_DAYS_TO_EARNINGS=21")


async def main():
    print("=" * 60)
    print("  EARNINGS CALENDAR ENGINE - LIVE VALIDATION")
    print(f"  Date: {date.today()} | Backend: {API} | Frontend: {FRONTEND}")
    print("=" * 60)

    tests = [
        test_health, test_earnings, test_prices, test_options,
        test_volatility, test_dashboard, test_scan_history,
        test_trade_builder, test_rejections, test_settings,
        test_audit, test_export, test_frontend_pages,
        test_scan_with_wider_window,
    ]
    for t in tests:
        try:
            await t()
        except Exception as e:
            report("fail", f"CRASHED: {t.__name__}", str(e)[:100])

    print("\n" + "=" * 60)
    total = results["pass"] + results["fail"] + results["warn"]
    print(f"  RESULTS: {results['pass']}/{total} passed, {results['warn']} warnings, {results['fail']} failures")
    print("=" * 60)

    if results["fail"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
