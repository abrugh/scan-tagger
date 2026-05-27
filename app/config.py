import os
from dataclasses import dataclass, field

import yaml


@dataclass
class Config:
    watch_path: str = "/scans"

    # LLM provider: "openai" or "azure"
    llm_provider: str = "openai"

    # OpenAI settings
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str = ""  # optional, for compatible APIs

    # Azure OpenAI settings
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = "gpt-4o"
    azure_openai_api_version: str = "2025-04-01-preview"

    stabilization_delay: float = 3.0
    stabilization_checks: int = 3
    max_summary_words: int = 4
    supported_extensions: list = field(
        default_factory=lambda: [".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"]
    )
    process_existing: bool = False
    log_level: str = "INFO"

    # Notifications
    discord_webhook_url: str = ""
    signal_recipient: str = ""
    signal_port: int = 7583
    notify_on_success: bool = True
    notify_on_startup: bool = True
    daily_summary_hour: int = 20  # 8 PM local

    @classmethod
    def load(cls, config_path: str = "/app/config.yaml") -> "Config":
        config = cls()

        if os.path.exists(config_path):
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            for key, value in data.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        env_map = {
            "WATCH_PATH": "watch_path",
            "LLM_PROVIDER": "llm_provider",
            "OPENAI_API_KEY": "openai_api_key",
            "OPENAI_MODEL": "openai_model",
            "OPENAI_BASE_URL": "openai_base_url",
            "AZURE_OPENAI_ENDPOINT": "azure_openai_endpoint",
            "AZURE_OPENAI_API_KEY": "azure_openai_api_key",
            "AZURE_OPENAI_DEPLOYMENT": "azure_openai_deployment",
            "AZURE_OPENAI_API_VERSION": "azure_openai_api_version",
            "STABILIZATION_DELAY": "stabilization_delay",
            "STABILIZATION_CHECKS": "stabilization_checks",
            "MAX_SUMMARY_WORDS": "max_summary_words",
            "PROCESS_EXISTING": "process_existing",
            "LOG_LEVEL": "log_level",
            "DISCORD_WEBHOOK_URL": "discord_webhook_url",
            "SIGNAL_RECIPIENT": "signal_recipient",
            "SIGNAL_PORT": "signal_port",
            "NOTIFY_ON_SUCCESS": "notify_on_success",
            "NOTIFY_ON_STARTUP": "notify_on_startup",
            "DAILY_SUMMARY_HOUR": "daily_summary_hour",
        }

        for env_key, attr in env_map.items():
            val = os.environ.get(env_key)
            if val is not None:
                current = getattr(config, attr)
                if isinstance(current, bool):
                    setattr(config, attr, val.lower() in ("true", "1", "yes"))
                elif isinstance(current, float):
                    setattr(config, attr, float(val))
                elif isinstance(current, int):
                    setattr(config, attr, int(val))
                else:
                    setattr(config, attr, val)

        return config
