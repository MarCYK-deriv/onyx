import os
import yaml
from typing import Dict, Any, Optional

from src.utils.logger import logger


def load_prompts(yaml_file: str = "prompts.yaml") -> Dict[str, Any]:
    """
    Load prompts and configurations from a YAML file.

    Args:
        yaml_file: Path to the YAML file containing prompts and configurations

    Returns:
        Dict containing all prompts and configurations from the YAML file
    """
    try:
        # Get the absolute path to the YAML file in the config directory
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        yaml_path = os.path.join(base_dir, "config", yaml_file)

        # Log prompt loading attempt
        logger.info(f"Loading prompts from {yaml_path}", extra={
                    "event_type": "prompt_loading", "yaml_file": yaml_path})

        # Load the YAML file
        with open(yaml_path, "r") as file:
            prompts_data = yaml.safe_load(file)

        # Log successful loading
        logger.info(
            f"Successfully loaded prompts from {yaml_path}",
            extra={"event_type": "prompt_loading_success",
                   "yaml_file": yaml_path, "prompt_keys": list(prompts_data.keys())},
        )

        return prompts_data
    except Exception as e:
        # Log error and raise
        logger.error(
            f"Error loading prompts from {yaml_file}: {str(e)}",
            extra={
                "event_type": "prompt_loading_error",
                "yaml_file": yaml_file,
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
        )
        raise


def get_prompt_template(prompt_key: str, yaml_file: str = "prompts.yaml") -> Optional[Dict[str, str]]:
    """
    Get a specific prompt template from the YAML file.

    Args:
        prompt_key: Key of the prompt to retrieve
        yaml_file: Path to the YAML file containing prompts

    Returns:
        Dict containing the prompt template or None if not found
    """
    prompts_data = load_prompts(yaml_file)
    prompt = prompts_data.get(prompt_key)

    if not prompt:
        logger.warning(
            f"Prompt '{prompt_key}' not found in {yaml_file}",
            extra={"event_type": "prompt_not_found",
                   "prompt_key": prompt_key, "yaml_file": yaml_file},
        )
        return None

    return prompt


def get_config_value(config_key: str, default_value: Any = None, yaml_file: str = "prompts.yaml") -> Any:
    """
    Get a specific configuration value from the YAML file.

    Args:
        config_key: Key of the configuration value to retrieve
        default_value: Default value to return if the key is not found
        yaml_file: Path to the YAML file containing configuration

    Returns:
        Configuration value or default_value if not found
    """
    prompts_data = load_prompts(yaml_file)
    config = prompts_data.get("config", {})

    value = config.get(config_key, default_value)

    logger.info(
        f"Retrieved config value for '{config_key}'",
        extra={"event_type": "config_retrieval", "config_key": config_key,
               "value": value, "is_default": value == default_value},
    )

    return value
