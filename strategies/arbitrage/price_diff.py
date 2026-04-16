"""
Price Difference Calculator: precise price comparison between pools.
"""

from utils.models import PoolData


def calculate_price_diff(pool_a: PoolData, pool_b: PoolData) -> dict:
    """
    Calculate the precise price difference between two pools for the same token pair.
    
    Uses the AMM formula: price = reserve_out / reserve_in
    
    Returns:
        dict with price_a, price_b, diff_absolute, diff_pct, cheaper_pool
    """
    price_a = pool_a.price_token0_in_token1
    price_b = pool_b.price_token0_in_token1

    if price_a == 0 and price_b == 0:
        return {"price_a": 0, "price_b": 0, "diff_absolute": 0, "diff_pct": 0, "cheaper_pool": None}

    avg_price = (price_a + price_b) / 2 if (price_a + price_b) > 0 else 1
    diff_absolute = abs(price_a - price_b)
    diff_pct = diff_absolute / avg_price

    cheaper_pool = "A" if price_a < price_b else "B"

    return {
        "price_a": price_a,
        "price_b": price_b,
        "diff_absolute": round(diff_absolute, 8),
        "diff_pct": round(diff_pct, 6),
        "cheaper_pool": cheaper_pool,
    }
