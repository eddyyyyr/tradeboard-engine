from engine.load_config import load_config


def compute_implied_rates(current_rate, futures_prices):
    """
    Conversion simplifiée : implied rate = 100 - prix future
    """
    implied = {}
    for label, price in futures_prices.items():
        implied[label] = round(100 - price, 2)
    return implied


def main():
    config = load_config("FED")

    current_rate = config["current_rate"]["value"]

    # Futures PRIX (exemple simple pour test)
    futures_prices = {
        "2026-03": 95.50,
        "2026-06": 95.75,
        "2026-09": 96.00,
    }

    implied_rates = compute_implied_rates(current_rate, futures_prices)

    print("\n=== IMPLIED RATES (TEST) ===")
    print(f"Current rate: {current_rate}%\n")

    for month, rate in implied_rates.items():
        delta_bp = round((rate - current_rate) * 100)
        print(f"{month} → {rate}% ({delta_bp:+} bp)")


if __name__ == "__main__":
    main()
