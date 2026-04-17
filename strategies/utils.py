"""
Shared strategy utilities: AMM math, pair normalization.
"""
from __future__ import annotations


def amm_price(reserve_in: float, reserve_out: float) -> float:
    """Calculate the spot price in a constant-product AMM: price = reserve_out / reserve_in."""
    if reserve_in == 0:
        return 0.0
    return reserve_out / reserve_in


def amm_output(amount_in: float, reserve_in: float, reserve_out: float, fee: float = 0.0025) -> float:
    """
    Calculate output amount for a swap in a constant-product AMM.
    Formula: amount_out = (amount_in * (1 - fee) * reserve_out) / (reserve_in + amount_in * (1 - fee))
    """
    if reserve_in == 0 or reserve_out == 0:
        return 0.0
    amount_in_after_fee = amount_in * (1 - fee)
    numerator = amount_in_after_fee * reserve_out
    denominator = reserve_in + amount_in_after_fee
    return numerator / denominator


def price_impact(amount_in: float, reserve_in: float) -> float:
    """Estimate price impact as a fraction of the reserve."""
    if reserve_in == 0:
        return 1.0
    return amount_in / (reserve_in + amount_in)


def normalize_pair(symbol_a: str, symbol_b: str) -> str:
    """Return a canonical pair key (alphabetically sorted)."""
    return "/".join(sorted([symbol_a, symbol_b]))
