from load_config import load_config
import pprint

def main():
    fed_config = load_config("FED")
    pprint.pprint(fed_config)

if __name__ == "__main__":
    main()
