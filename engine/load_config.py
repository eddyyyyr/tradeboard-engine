import yaml
from pathlib import Path

def load_config(bank_code: str):
    """
    Load a central bank YAML config from /configs
    Example: bank_code="FED" -> configs/fed.yaml
    """
    config_path = Path("configs") / f"{bank_code.lower()}.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
