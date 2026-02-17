def calculate_delta_hedge(target_delta: float, current_delta: float, contract_delta: float = 0.5) -> dict:
    delta_gap = target_delta - current_delta
    if contract_delta == 0:
        return {"action": "NONE", "qty": 0}
    qty = int(abs(delta_gap / contract_delta))
    action = "BUY" if delta_gap > 0 else "SELL"
    return {"action": action, "qty": max(qty, 1), "delta_gap": delta_gap}
