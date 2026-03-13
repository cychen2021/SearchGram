#!/usr/local/bin/python3
# coding: utf-8

# SearchGram - config.py
# 4/5/22 09:10
#

__author__ = "Benny <benny.think@gmail.com>"

import os
import sys
from pathlib import Path

# Import appropriate TOML library based on Python version
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

# Try to load config from TOML file
_config = {}
_config_path = Path.home() / ".config" / "searchgram" / "config.toml"

if tomllib and _config_path.exists():
    try:
        with open(_config_path, "rb") as f:
            _config = tomllib.load(f)
    except Exception as e:
        print(f"Warning: Failed to load config from {_config_path}: {e}")
        _config = {}

# Helper function to get config value with fallback to environment variable
def _get_config(toml_key, env_key, default):
    """Get config value from TOML file, then environment variable, then default."""
    return _config.get(toml_key, os.getenv(env_key, default))

APP_ID = int(_get_config("APP_ID", "APP_ID", 321232123))
APP_HASH = _get_config("APP_HASH", "APP_HASH", "23231321")
TOKEN = _get_config("TOKEN", "TOKEN", "1234")  # id:hash

######### search engine settings #########
# MeiliSearch, by default it's meili in docker-compose
MEILI_HOST = _get_config("MEILI_HOST", "MEILI_HOST", "http://meili:7700")
# Using bot token for simplicity
MEILI_PASS = os.getenv("MEILI_MASTER_KEY", TOKEN)
# Read MEILI_MAX_INDEXING_MEMORY from config or environment
MEILI_MAX_INDEXING_MEMORY = _get_config("MEILI_MAX_INDEXING_MEMORY", "MEILI_MAX_INDEXING_MEMORY", None)

# If you want to use MongoDB as search engine, you need to set this
MONGO_HOST = os.getenv("MONGO_HOST", "mongo")

# available values: meili, mongo, zinc, default: meili
ENGINE = os.getenv("ENGINE", "meili").lower()

# If you want to use Zinc as search engine, you need to set username and password
ZINC_HOST = os.getenv("ZINC_HOST", "http://zinc:4080")
ZINC_USER = os.getenv("ZINC_FIRST_ADMIN_USER", "root")
ZINC_PASS = os.getenv("ZINC_FIRST_ADMIN_PASSWORD", "root")

####################################
# Your own user id, for example: 260260121
# Can be a single ID (string) or a list of IDs
_owner_id_config = _get_config("OWNER_ID", "OWNER_ID", "260260121")
if isinstance(_owner_id_config, list):
    OWNER_IDS = [int(uid) for uid in _owner_id_config]
elif isinstance(_owner_id_config, str):
    OWNER_IDS = [int(_owner_id_config)]
else:
    OWNER_IDS = [int(_owner_id_config)]

# Keep OWNER_ID for backward compatibility
OWNER_ID = str(OWNER_IDS[0])
BOT_ID = int(TOKEN.split(":")[0])

# Handle PROXY configuration - can be a dict from TOML or string from env
_proxy_from_config = _config.get("PROXY")
_proxy_from_env = os.getenv("PROXY")
if _proxy_from_config:
    PROXY = _proxy_from_config
elif _proxy_from_env:
    PROXY = _proxy_from_env
else:
    PROXY = None
# example proxy configuration
# PROXY = {"scheme": "socks5", "hostname": "localhost", "port": 1080}

IPv6 = bool(os.getenv("IPv6", False))

# Sync configuration - get lists from TOML sections
def get_sync_list():
    """Get list of chat IDs/usernames to sync from config."""
    sync_section = _config.get("sync", {})
    return list(sync_section.keys())

def get_whitelist():
    """Get whitelist of chat IDs/usernames from config."""
    whitelist_section = _config.get("whitelist", {})
    return list(whitelist_section.keys())

def get_blacklist():
    """Get blacklist of chat IDs/usernames from config."""
    blacklist_section = _config.get("blacklist", {})
    return list(blacklist_section.keys())
