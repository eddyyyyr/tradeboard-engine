import yaml
from pathlib import Path


def load_config(bank_code: str):
    """
    Charge la configuration YAML d'une banque centrale
    """
    config_path = Path("configs") / "engine" / "configs" / "configs" / f"{bank_code.lower()}.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path, "r") as f:
        return yaml.safe_load(f)
