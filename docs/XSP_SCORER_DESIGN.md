# XSP Butterfly Scorer — Design Spec

**Status:** Draft — awaiting user approval
**Author:** Cascade
**Date:** 2026-04-16

---

## 1. Why a Separate Scorer

The existing `ButterflyStrategy` scorer is built for **pre-earnings equity IV crush**. Its factors (IV Percentile > 80, strong backwardation, proximity to earnings event) simply don't apply to XSP — an index product with no earnings.

Result: XSP consistently scores ~55 using the equity scorer, below the 65 WATCHLIST threshold, so it never surfaces as a recommendation.

This spec proposes `XSPButterflyStrategy` — a sibling class with index-appropriate scoring.

---

## 2. Trading Thesis (must agree on this first)

XSP iron butterflies profit from:
- **Theta decay** on the short ATM straddle (body)
- **Stock pinning** near the body strike at expiration
- **Stable or declining IV** over the holding period

They lose money when:
- Market makes a large move outside the wings (gap or trend)
- VIX expands rapidly (regime change)
- A macro event (FOMC, CPI, NFP) shocks volatility

**Ideal entry conditions:**
- VIX in a "healthy" range (not crisis, not sleepy)
- Recent realized volatility is low (market is range-bound)
- Normal contango term structure (opposite of equity butterfly)
- No major macro event between entry and expiry
- 7–14 days to expiration (enough theta, manageable gamma)

---

## 3. Factor Breakdown (proposed weights)

| # | Factor | Weight | Sweet Spot | Rationale |
|---|--------|--------|-----------|-----------|
| 1 | **IV Rank** | 20% | 30–60% | Elevated premium but no regime risk |
| 2 | **Realized Vol (20d)** | 20% | < 15% annualized | Quiet market = pinning likely |
| 3 | **Term Structure** | 15% | Mild contango (slope 0 to +0.10) | Normal vol curve = stable regime |
| 4 | **Gap Risk (ATR/Price)** | 15% | < 1.5% | Low daily range = low wing-breach risk |
| 5 | **Liquidity / Spreads** | 15% | < 35% spread-to-mid | Needs tight fills to collect credit |
| 6 | **DTE Fit** | 10% | 7–14 days | Balance theta vs gamma |
| 7 | **Risk/Reward** | 5% | Credit ≥ 25% of wing width | Structural quality |
|   | **Total** | **100%** | | |

### Scoring curves (0–100 per factor)

**IV Rank (20% weight)**
- IVR 30–60%: **100** (sweet spot)
- IVR 20–30% or 60–70%: **70**
- IVR 10–20% or 70–80%: **40**
- IVR < 10% or > 80%: **10** (too cheap or too hot)

**Realized Vol, 20-day annualized (20% weight)**
- RV < 12%: **100** (very quiet)
- RV 12–18%: **70**
- RV 18–25%: **40**
- RV > 25%: **10** (market is trending)

**Term Structure Slope (15% weight)**
- Slope 0 to +0.10 (mild contango): **100**
- Slope +0.10 to +0.20 (steep contango): **70**
- Slope -0.05 to 0 (flat): **60**
- Slope < -0.05 (backwardation): **20** (regime stress signal)
- Slope > +0.20 (very steep): **40** (complacency)

**Gap Risk, ATR/Price (15% weight)**
- ATR/P < 1.0%: **100**
- ATR/P 1.0–1.5%: **80**
- ATR/P 1.5–2.5%: **50**
- ATR/P > 2.5%: **15**

**Liquidity (15% weight)** — pass-through from `LiquidityEngine` with `is_index=True`

**DTE Fit (10% weight)**
- DTE 7–14: **100**
- DTE 5–7 or 14–21: **75**
- DTE 2–5 or 21–30: **50**
- DTE < 2 or > 30: **20**

**Risk/Reward (5% weight)**
- Credit ≥ 30% of wing width: **100**
- Credit 20–30%: **70**
- Credit 15–20%: **40**
- Credit < 15%: **10**

### Hard rejections (auto NO_TRADE, bypass scoring)

- Realized vol > 35% annualized (market in crisis)
- Term structure slope < -0.20 (severe backwardation)
- Bid-ask spread > 80% (market broken)
- No valid expiry in 3–30 DTE window

---

## 4. Data Requirements

### Already available (from existing providers)

- `price` — Tradier fallback already wired for XSP ✅
- `chain` — Tradier options chain ✅
- `vol.iv_rank` ✅
- `vol.realized_vol_20d` ✅
- `vol.term_structure_slope` ✅
- `vol.atr_14d` ✅
- `vol.front_expiry_iv` ✅

### Optional enhancement (future)

- **VIX level** — could add as a bonus factor (VIX 13–20 = ideal). Requires a VIX data provider (FMP has `^VIX`).
- **Macro event calendar** — FOMC, CPI, NFP dates. Would enable hard rejection if event falls between entry and expiry. Requires new data source.

**Phase 2 ships without these.** They're Phase 4 enhancements.

---

## 5. Classification Thresholds

Same as equity: **≥ 80 RECOMMEND**, **65–79 WATCHLIST**, **< 65 NO_TRADE**.

Rationale: Keep the discipline. A properly-scored XSP butterfly in a favorable regime should score 80+.

---

## 6. Integration Points

### Routing change

Current `scan_pipeline.py`:
```python
if ticker.upper() == "XSP":
    target_strategy_id = "IRON_BUTTERFLY_ATM"  # equity butterfly scorer
    layer_id = "L4"
```

Proposed:
```python
if ticker.upper() == "XSP":
    target_strategy_id = "XSP_IRON_BUTTERFLY"  # new scorer
    layer_id = "L4"
```

Same change in `trade_builder.py:_determine_phase`.

### StrategyFactory registration

Add `"XSP_IRON_BUTTERFLY"` to `base_strategy.py:StrategyFactory.get_strategy()`.

### No backward-compat break

- Equity butterflies (L2, L3) still use existing `ButterflyStrategy` — zero change
- Double calendars (L1) unchanged
- Only XSP routing changes

---

## 7. Equity Butterfly Cap (Phase 3)

Add config setting:
```python
class ScoringSettings:
    EQUITY_BUTTERFLY_MAX_CLASSIFICATION: str = "WATCHLIST"
```

In `scan_pipeline.py` after final classification:
```python
if (
    best_strategy in ("IRON_BUTTERFLY_ATM", "IRON_BUTTERFLY_BULLISH")
    and ticker.upper() not in settings.liquidity.INDEX_TICKERS
    and best_result.classification == RecommendationClass.RECOMMEND
):
    best_result.classification = RecommendationClass.WATCHLIST
    best_result.rationale_summary += (
        " [Capped to WATCHLIST: equity butterflies carry early-assignment "
        "risk on the short ATM body. Prefer XSP.]"
    )
```

**Effect:** Equity butterflies can still score high and appear in results, but they will never be a RECOMMEND. XSP butterflies can still be RECOMMEND when conditions are right.

---

## 8. Test Coverage

New tests in `test_strategies.py`:

1. `test_xsp_butterfly_factory_registered` — StrategyFactory returns `XSPButterflyStrategy`
2. `test_xsp_butterfly_scoring_ideal_regime` — IVR=45, RV=10%, contango → expect score ≥ 80
3. `test_xsp_butterfly_scoring_crisis_regime` — RV=40% → hard reject NO_TRADE
4. `test_xsp_butterfly_scoring_complacent` — IVR=8% → scores low (not enough premium)
5. `test_xsp_butterfly_scoring_backwardation` — slope=-0.30 → hard reject
6. `test_xsp_routing` — scan_pipeline routes XSP to `XSP_IRON_BUTTERFLY`
7. `test_equity_butterfly_capped_at_watchlist` — high-scoring equity butterfly → WATCHLIST not RECOMMEND
8. `test_xsp_butterfly_not_capped` — high-scoring XSP butterfly → stays RECOMMEND

Target: 8 new tests → **189 total**.

---

## 9. Open Questions for User

These are **your trading decisions** — please confirm or override:

1. **IV Rank sweet spot** — I proposed 30–60. Agree? Or do you prefer higher (50–70)?
2. **Realized vol threshold** — I proposed < 12% for max score. Too strict? (For context, SPY 20d RV is typically 10–20%)
3. **DTE sweet spot** — I proposed 7–14 days. Are you a 0DTE trader or do you want longer dated (21–30)?
4. **Contango preference** — I'm treating mild contango as ideal. Agree? (This is opposite of equity butterfly thesis)
5. **Equity butterfly cap** — Do you want them capped at WATCHLIST (Phase 3A) or fully disabled (Phase 3B)?

---

## 10. Out of Scope (explicitly deferred)

- VIX-based factor (needs new data source)
- Macro event calendar integration (FOMC, CPI, NFP)
- 0DTE-specific scoring variant
- Multiple XSP strategies (bullish/bearish offset variants)
- Backtest validation of the new scorer (separate effort)

---

## 11. Estimated Effort

- **Phase 1 (config):** 15 min
- **Phase 2 (new scorer + tests):** 90 min
- **Phase 3 (equity cap):** 20 min
- **Documentation + commit + push:** 15 min
- **Total:** ~2.5 hours

Ready to build on approval.
