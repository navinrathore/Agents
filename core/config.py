import os
import yaml

def load_config(config_path: str) -> dict:
    """
    Loads and parses the agent configuration from a YAML file.
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at {config_path}")
        
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
        
    # Basic validation
    required_keys = ['name', 'model', 'system']
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Missing required key in config: {key}")
            
    return config
