import json
import os


class MissingAPIKey(Exception):
    pass


CONFIG_PATH = os.path.expanduser("~/ai-system/ClaudeProjects/user-insights/user_insights_config.json")
DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_PROVIDER = "anthropic"
DEFAULT_OUTPUT = "user-insights-output"

REDDIT_USER_AGENT = "user-insights/0.1 by kairosl"


def get_youtube_api_key() -> str:
    """YouTube Data API v3 key from env var only (never in config file)."""
    key = os.environ.get("YOUTUBE_API_KEY", "")
    if key:
        return key
    raise MissingAPIKey(
        "No YouTube API key found. Set YOUTUBE_API_KEY environment variable."
    )


def get_reddit_credentials() -> dict:
    client_id = os.environ.get("REDDIT_CLIENT_ID", "")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise MissingAPIKey(
            "Reddit credentials not found. Set REDDIT_CLIENT_ID and "
            "REDDIT_CLIENT_SECRET environment variables."
        )
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "user_agent": REDDIT_USER_AGENT,
    }


def get_api_key() -> str:
    cfg = load_config()
    provider = cfg.get("provider", DEFAULT_PROVIDER)
    env_var = _api_key_env_var(provider)
    key = os.environ.get(env_var, "")
    if key:
        return key
    key = cfg.get("api_key", "")
    if key:
        return key
    raise MissingAPIKey(
        f"No API key found. Set {env_var} environment variable "
        f"or run `user-insights config` to save one."
    )


def get_model() -> str:
    cfg = load_config()
    return cfg.get("model", DEFAULT_MODEL)


def get_provider() -> str:
    cfg = load_config()
    return cfg.get("provider", DEFAULT_PROVIDER)


def get_base_url() -> str:
    cfg = load_config()
    return cfg.get("base_url", "")


def get_output_base() -> str:
    cfg = load_config()
    return cfg.get("output_dir", DEFAULT_OUTPUT)


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_config(key: str, value: str) -> None:
    cfg = load_config()
    cfg[key] = value
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def _api_key_env_var(provider: str) -> str:
    if provider == "openai_compatible":
        return "DEEPSEEK_API_KEY"
    return "ANTHROPIC_API_KEY"
