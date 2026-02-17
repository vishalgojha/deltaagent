def aggregate_portfolio_greeks(positions: list[dict]) -> dict[str, float]:
    totals = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    for pos in positions:
        qty = float(pos.get("qty", 0))
        totals["delta"] += float(pos.get("delta", 0)) * qty
        totals["gamma"] += float(pos.get("gamma", 0)) * qty
        totals["theta"] += float(pos.get("theta", 0)) * qty
        totals["vega"] += float(pos.get("vega", 0)) * qty
    return totals
