from load_config import load_config


def main():
    fed_config = load_config("FED")
    print("FED loaded:")
    print(fed_config["bank"]["name"])
    print("Current rate:", fed_config["current_rate"]["value"])


if __name__ == "__main__":
    main()
