from .load_config import load_config
from .calc_implied import compute_implied_curve_from_rows
from datetime import date


def main():
    fed = load_config("FED")

    print("✅ FED loaded")
    print("Bank:", fed["bank"]["name"])
    print("Current rate:", fed["current_rate"]["value"])

    # --- Futures fictives (test moteur) ---
    futures_rows = [
        {
            "month": "2026-03",
            "price": 95.25,
            "open_interest": 120000,
            "volume": 45000,
            "bid_ask_spread_bp": 1.5,
        },
        {
            "contract_month": date(2026, 4, 1),
            "price": 95.38,
            "open_interest": 90000,
            "volume": 28000,
            "bid_ask_spread_bp": 2.0,
        },
    ]

    # ✅ calc_implied.py attend d'abord "config" (dict), puis "rows" (list)
    implied_curve = compute_implied_curve_from_rows(
        fed,
        futures_rows,
    )

    print("\n📈 Implied rate curve:")
    for point in implied_curve:
        print(point)


if __name__ == "__main__":
    main()
