"""
Broker cost calculator — exact formulas, no approximations.
Every P&L figure in KAIROS is NET of these costs.
"""


def calculate_india_costs(
    buy_price: float,
    sell_price: float,
    quantity: float,
    segment: str = "equity_intraday",
) -> dict:
    """
    Complete cost breakdown for NSE trades.
    segment: equity_delivery | equity_intraday | fno_futures | fno_options
    """
    buy_value = buy_price * quantity
    sell_value = sell_price * quantity
    turnover = buy_value + sell_value

    if segment == "equity_delivery":
        brokerage = 0.0
        stt = 0.001 * sell_value            # 0.1% on sell only
        stamp_duty = 0.00015 * buy_value    # 0.015% on buy only

    elif segment == "equity_intraday":
        brokerage = min(20.0, 0.0003 * turnover)   # ₹20 or 0.03%, lower
        stt = 0.00025 * sell_value          # 0.025% on sell only
        stamp_duty = 0.00003 * buy_value    # 0.003% on buy only

    elif segment == "fno_futures":
        brokerage = min(20.0, 0.0003 * turnover)
        stt = 0.0001 * sell_value           # 0.01% on sell
        stamp_duty = 0.00002 * buy_value    # 0.002% on buy

    elif segment == "fno_options":
        brokerage = 20.0                    # ₹20 flat per executed order
        stt = 0.0005 * sell_value           # 0.05% on sell (on premium)
        stamp_duty = 0.00003 * buy_value

    else:
        raise ValueError(f"Unknown segment: {segment}")

    exchange_charges = 0.0000335 * turnover     # NSE: 0.00335% of turnover
    sebi_charges = 0.000001 * turnover          # SEBI: 0.0001% of turnover
    gst = 0.18 * (brokerage + exchange_charges + sebi_charges)

    total_cost = brokerage + stt + stamp_duty + exchange_charges + sebi_charges + gst

    return {
        "brokerage": round(brokerage, 4),
        "stt": round(stt, 4),
        "stamp_duty": round(stamp_duty, 4),
        "exchange_charges": round(exchange_charges, 4),
        "sebi_charges": round(sebi_charges, 4),
        "gst": round(gst, 4),
        "total_cost": round(total_cost, 4),
        # US fields zeroed for cross-format consistency
        "sec_fee": 0.0,
        "finra_taf": 0.0,
    }


def calculate_us_costs(shares: float, sell_price: float) -> dict:
    """SEC and FINRA regulatory fees on sell side only."""
    notional_sell = shares * sell_price
    sec_fee = round(0.0000278 * notional_sell, 6)           # $27.80 per $1M sold
    finra_taf = round(min(5.95, 0.000119 * shares), 6)      # $0.000119/share, max $5.95
    total = round(sec_fee + finra_taf, 6)

    return {
        "sec_fee": sec_fee,
        "finra_taf": finra_taf,
        "total_cost": total,
        # India fields zeroed for cross-format consistency
        "brokerage": 0.0,
        "stt": 0.0,
        "stamp_duty": 0.0,
        "exchange_charges": 0.0,
        "sebi_charges": 0.0,
        "gst": 0.0,
    }


def calculate_costs(
    market: str,
    buy_price: float,
    sell_price: float,
    quantity: float,
    segment: str = "equity_intraday",
) -> dict:
    """Unified entry point used by executor.py."""
    if market == "INDIA":
        return calculate_india_costs(buy_price, sell_price, quantity, segment)
    if market == "US":
        return calculate_us_costs(quantity, sell_price)
    raise ValueError(f"Unknown market: {market}")
