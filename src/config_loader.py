"""Configuration loader with dual-environment fallback.

Priority chain: config/config.yaml → environment variables → Streamlit secrets.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.yaml"

_LLM_ENV_MAP: dict[str, tuple[str, str]] = {
    "LLM_API_KEY": ("llm", "api_key"),
    "LLM_BASE_URL": ("llm", "base_url"),
    "LLM_MODEL_NAME": ("llm", "model_name"),
}

_LLM_STREAMLIT_MAP: dict[str, tuple[str, str]] = {
    "llm_api_key": ("llm", "api_key"),
    "llm_base_url": ("llm", "base_url"),
    "llm_model_name": ("llm", "model_name"),
}


def load_config() -> dict[str, Any]:
    """Load configuration with fallback chain.

    Order: ``config/config.yaml`` → ``os.environ`` → ``streamlit.secrets``.
    Later sources override earlier ones (env wins over yaml, secrets win over env).
    """
    config: dict[str, Any] = _load_yaml_config()
    _apply_env_overrides(config)
    _apply_streamlit_overrides(config)
    return config


def _load_yaml_config() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        logger.debug("No local yaml at %s; skipping", _CONFIG_PATH)
        return {}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            logger.warning("config.yaml did not parse to a dict (got %s); ignoring", type(data).__name__)
            return {}
        logger.debug("Loaded config from %s", _CONFIG_PATH)
        return data
    except yaml.YAMLError as e:
        logger.warning("Failed to parse %s: %s", _CONFIG_PATH, e)
        return {}
    except OSError as e:
        logger.warning("Failed to read %s: %s", _CONFIG_PATH, e)
        return {}


def _apply_env_overrides(config: dict[str, Any]) -> None:
    for env_key, (section, field) in _LLM_ENV_MAP.items():
        value = os.getenv(env_key)
        if value:
            config.setdefault(section, {})[field] = value
            logger.debug("Override from env: %s.%s", section, field)


def _apply_streamlit_overrides(config: dict[str, Any]) -> None:
    try:
        import streamlit as st
        secrets = getattr(st, "secrets", None)
        if secrets is None:
            return
        has_secrets = False
        try:
            has_secrets = len(secrets) > 0
        except Exception:
            try:
                has_secrets = bool(secrets._parse())
            except Exception:
                return
        if not has_secrets:
            return
    except Exception:
        return

    try:
        for secret_key, (section, field) in _LLM_STREAMLIT_MAP.items():
            try:
                value = secrets.get(secret_key)
            except Exception:
                continue
            if value:
                config.setdefault(section, {})[field] = value
                logger.debug("Override from streamlit secrets: %s.%s", section, field)
    except Exception as e:
        logger.debug("Streamlit secrets read failed: %s", e)


def get_llm_config() -> dict[str, Any]:
    cfg = load_config().get("llm", {}) or {}
    return {
        "base_url": cfg.get("base_url", "https://api.minimaxi.com/v1"),
        "api_key": cfg.get("api_key", ""),
        "model_name": cfg.get("model_name", "MiniMax-M3"),
        "temperature": cfg.get("temperature", 0.3),
        "max_tokens": cfg.get("max_tokens", 8192),
        "max_retries": cfg.get("max_retries", 3),
        "retry_delay": cfg.get("retry_delay", 2),
    }


def get_app_config() -> dict[str, Any]:
    return load_config().get("app") or {
        "course_name": "人工智能基础",
        "university": "河北工业大学",
        "department": "人工智能学院",
        "max_questions": 10,
    }


def get_auth_config() -> dict[str, Any]:
    return load_config().get("auth", {}) or {}