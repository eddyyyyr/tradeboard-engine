from load_config import load_config
from pprint import pprint

def main():
    fed_config = load_config("FED")
    print("✅ FED loaded")
    print("Bank name:", fed_config["bank"]["name"])
    print("Current rate:", fed_config["current_rate"]["value"])
    print("\nFull config:")
    pprint(fed_config)

if __name__ == "__main__":
    main()
