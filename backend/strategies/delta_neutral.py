from backend.strategies.greeks import aggregate_portfolio_greeks


def detect_rebalance_need(positions: list[dict], delta_threshold: float) -> dict:
    greeks = aggregate_portfolio_greeks(positions)
    net_delta = greeks["delta"]
    return {
        "needs_rebalance": abs(net_delta) > delta_threshold,
        "net_delta": net_delta,
        "greeks": greeks,
    }
