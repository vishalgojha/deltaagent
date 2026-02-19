from datetime import datetime, timezone


def default_instruments() -> list[dict]:
    now = datetime.now(timezone.utc)
    return [
        {"symbol": "AAPL", "asset_class": "stock", "exchange": "NASDAQ", "currency": "USD", "multiplier": 1, "tick_size": 0.01, "aliases": ["apple"], "contract_rules": {}, "is_active": True, "created_at": now, "updated_at": now},
        {"symbol": "MSFT", "asset_class": "stock", "exchange": "NASDAQ", "currency": "USD", "multiplier": 1, "tick_size": 0.01, "aliases": ["microsoft"], "contract_rules": {}, "is_active": True, "created_at": now, "updated_at": now},
        {"symbol": "NVDA", "asset_class": "stock", "exchange": "NASDAQ", "currency": "USD", "multiplier": 1, "tick_size": 0.01, "aliases": ["nvidia"], "contract_rules": {}, "is_active": True, "created_at": now, "updated_at": now},
        {"symbol": "TSLA", "asset_class": "stock", "exchange": "NASDAQ", "currency": "USD", "multiplier": 1, "tick_size": 0.01, "aliases": ["tesla"], "contract_rules": {}, "is_active": True, "created_at": now, "updated_at": now},
        {"symbol": "SPX", "asset_class": "index", "exchange": "CBOE", "currency": "USD", "multiplier": 1, "tick_size": 0.01, "aliases": ["sp500", "s&p500"], "contract_rules": {}, "is_active": True, "created_at": now, "updated_at": now},
        {"symbol": "NDX", "asset_class": "index", "exchange": "NASDAQ", "currency": "USD", "multiplier": 1, "tick_size": 0.01, "aliases": ["nasdaq100"], "contract_rules": {}, "is_active": True, "created_at": now, "updated_at": now},
        {"symbol": "RUT", "asset_class": "index", "exchange": "CBOE", "currency": "USD", "multiplier": 1, "tick_size": 0.01, "aliases": ["russell2000"], "contract_rules": {}, "is_active": True, "created_at": now, "updated_at": now},
        {"symbol": "VIX", "asset_class": "index", "exchange": "CBOE", "currency": "USD", "multiplier": 1, "tick_size": 0.01, "aliases": ["volatility"], "contract_rules": {}, "is_active": True, "created_at": now, "updated_at": now},
        {"symbol": "ES", "asset_class": "future", "exchange": "CME", "currency": "USD", "multiplier": 50, "tick_size": 0.25, "aliases": ["spx-future", "e-mini", "silver"], "contract_rules": {"session": "RTH+ETH"}, "is_active": True, "created_at": now, "updated_at": now},
        {"symbol": "NQ", "asset_class": "future", "exchange": "CME", "currency": "USD", "multiplier": 20, "tick_size": 0.25, "aliases": ["nasdaq-future"], "contract_rules": {"session": "RTH+ETH"}, "is_active": True, "created_at": now, "updated_at": now},
        {"symbol": "RTY", "asset_class": "future", "exchange": "CME", "currency": "USD", "multiplier": 50, "tick_size": 0.1, "aliases": ["russell-future"], "contract_rules": {"session": "RTH+ETH"}, "is_active": True, "created_at": now, "updated_at": now},
        {"symbol": "YM", "asset_class": "future", "exchange": "CBOT", "currency": "USD", "multiplier": 5, "tick_size": 1.0, "aliases": ["dow-future"], "contract_rules": {"session": "RTH+ETH"}, "is_active": True, "created_at": now, "updated_at": now},
        {"symbol": "CL", "asset_class": "future", "exchange": "NYMEX", "currency": "USD", "multiplier": 1000, "tick_size": 0.01, "aliases": ["crude", "oil"], "contract_rules": {"session": "RTH+ETH"}, "is_active": True, "created_at": now, "updated_at": now},
        {"symbol": "GC", "asset_class": "future", "exchange": "COMEX", "currency": "USD", "multiplier": 100, "tick_size": 0.1, "aliases": ["gold"], "contract_rules": {"session": "RTH+ETH"}, "is_active": True, "created_at": now, "updated_at": now},
        {"symbol": "SI", "asset_class": "future", "exchange": "COMEX", "currency": "USD", "multiplier": 5000, "tick_size": 0.005, "aliases": ["silver-future"], "contract_rules": {"session": "RTH+ETH"}, "is_active": True, "created_at": now, "updated_at": now},
        {"symbol": "HG", "asset_class": "future", "exchange": "COMEX", "currency": "USD", "multiplier": 25000, "tick_size": 0.0005, "aliases": ["copper"], "contract_rules": {"session": "RTH+ETH"}, "is_active": True, "created_at": now, "updated_at": now},
        {"symbol": "ZB", "asset_class": "future", "exchange": "CBOT", "currency": "USD", "multiplier": 1000, "tick_size": 0.03125, "aliases": ["30y-bond"], "contract_rules": {"session": "RTH+ETH"}, "is_active": True, "created_at": now, "updated_at": now},
        {"symbol": "ZN", "asset_class": "future", "exchange": "CBOT", "currency": "USD", "multiplier": 1000, "tick_size": 0.015625, "aliases": ["10y-note"], "contract_rules": {"session": "RTH+ETH"}, "is_active": True, "created_at": now, "updated_at": now},
    ]


def default_strategy_profiles() -> list[dict]:
    now = datetime.now(timezone.utc)
    return [
        {
            "strategy_id": "delta_rebalance_single",
            "name": "Single-leg delta rebalance",
            "description": "Uses one hedge leg to bring portfolio delta toward threshold.",
            "allowed_asset_classes": ["future", "fop"],
            "allowed_symbols": ["ES", "NQ", "SI", "GC", "CL"],
            "max_legs": 1,
            "require_defined_risk": False,
            "tier_allowlist": ["basic", "pro", "enterprise"],
            "entry_rules": {"trigger": "abs(net_delta) > delta_threshold"},
            "exit_rules": {"trigger": "abs(net_delta) <= delta_threshold"},
            "risk_template": {"max_size": 10},
            "execution_template": {"order_type": "MKT"},
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "strategy_id": "vertical_spread",
            "name": "Defined-risk vertical spread",
            "description": "Two-leg directional spread with capped risk.",
            "allowed_asset_classes": ["fop"],
            "allowed_symbols": ["ES", "NQ", "SI", "GC", "CL"],
            "max_legs": 2,
            "require_defined_risk": True,
            "tier_allowlist": ["pro", "enterprise"],
            "entry_rules": {"trigger": "directional view confirmed"},
            "exit_rules": {"trigger": "profit_target or stop_loss"},
            "risk_template": {"max_spread_width": 100},
            "execution_template": {"order_type": "LMT"},
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "strategy_id": "iron_condor",
            "name": "Defined-risk iron condor",
            "description": "Four-leg neutral premium strategy with wings.",
            "allowed_asset_classes": ["fop"],
            "allowed_symbols": ["ES", "NQ"],
            "max_legs": 4,
            "require_defined_risk": True,
            "tier_allowlist": ["enterprise"],
            "entry_rules": {"trigger": "range-bound IV rich environment"},
            "exit_rules": {"trigger": "50pct max profit or delta breach"},
            "risk_template": {"max_loss_pct": 1.0},
            "execution_template": {"order_type": "LMT"},
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
    ]
