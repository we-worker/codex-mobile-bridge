"""Opaque, stable namespaces for drafts whose account owner is known."""

import hashlib
import json
from pathlib import Path


def draft_identity(*parts):
    return hashlib.sha256(json.dumps(['draft-v1', *parts], ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def codex_account_identity(home, provider, environment=None):
    """Read the selected home without contacting or activating a Codex runtime."""
    home = Path(home)
    environment = environment or {}
    try:
        auth = json.loads((home/'auth.json').read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        auth = {}
    if provider == 'openai':
        account_id = (auth.get('tokens') or {}).get('account_id')
        if auth.get('auth_mode') != 'apikey' and isinstance(account_id, str) and account_id:
            return draft_identity('chatgpt', account_id)
        if auth.get('auth_mode') == 'chatgpt':
            return ''
        key = auth.get('OPENAI_API_KEY') or environment.get('OPENAI_API_KEY')
        endpoint = environment.get('OPENAI_BASE_URL') or 'https://api.openai.com/v1'
        return draft_identity('api', provider, endpoint, key) if isinstance(key, str) and key else ''
    try:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        config = tomllib.loads((home/'config.toml').read_text(encoding='utf-8'))
        profile = (config.get('profiles') or {}).get(config.get('profile')) or {}
        effective = {**config, **profile}
        definition = (effective.get('model_providers') or {}).get(provider) or {}
        key = (environment.get(definition['env_key']) if definition.get('env_key')
               else definition.get('experimental_bearer_token'))
        endpoint = definition.get('base_url')
        if isinstance(key, str) and key and isinstance(endpoint, str) and endpoint:
            return draft_identity('api', provider, endpoint, key)
    except (OSError, ValueError, TypeError, KeyError, ImportError, AttributeError):
        pass
    return ''
