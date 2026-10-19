"""Standalone SSH worker for the joined native Codex CLI model catalog.

Catalog, CatalogError and read_daemon_environment are supplied by the injected
source bundle. The response contains only public model metadata and digests.
"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path


REMOTE_MODEL_ERROR = '无法核验 SSH 原生 CLI 守护进程的启动环境，请重新连接后刷新模型'
REMOTE_MODEL_CHANGED = 'SSH 原生 CLI 守护进程已变化，请重新连接后刷新模型'


def _remote_executable(home):
    home = Path(home)
    state = home / 'app-server-daemon'
    dedicated = home / 'packages/app-server-daemon'
    if os.path.lexists(dedicated / 'current') or any(os.path.lexists(state / name) for name in
            ('daemon.pid', 'daemon.stderr.log', 'daemon-updater.pid', 'daemon-updater.stderr.log')):
        root = dedicated
    elif any(os.path.lexists(state / name) for name in
             ('app-server.pid', 'app-server.stderr.log', 'app-server-updater.pid', 'app-server-updater.stderr.log')):
        root = home / 'packages/standalone'
    else:
        root = dedicated
    for candidate in (root / 'current/bin/codex', root / 'current/codex'):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    fallback = shutil.which('codex') or str(Path.home() / '.local/bin/codex')
    if Path(fallback).is_file() and os.access(fallback, os.X_OK):
        return fallback
    raise ValueError(REMOTE_MODEL_ERROR)


def _environment_snapshot(home, cwd, provider, config, account):
    if sys.platform not in ('linux', 'darwin'):
        raise ValueError('SSH 原生 CLI 模型查询暂不支持此系统')
    if not isinstance(home, str) or not Path(home).is_absolute() or not isinstance(cwd, str) or not Path(cwd).is_absolute():
        raise ValueError(REMOTE_MODEL_ERROR)
    if not isinstance(config, dict) or not isinstance(account, dict) or not isinstance(provider, str) or not provider:
        raise ValueError(REMOTE_MODEL_ERROR)
    profile = (config.get('profiles') or {}).get(config.get('profile')) or {}
    effective = {**config, **profile}
    definition = (effective.get('model_providers') or {}).get(provider) or {}
    names = {name for name in (definition.get('env_key'), *(definition.get('env_http_headers') or {}).values())
             if isinstance(name, str) and name}
    if (provider == 'openai' and
            not effective.get('openai_base_url') and not definition.get('base_url')):
        names.add('OPENAI_BASE_URL')
    if (not definition.get('env_key') and not definition.get('experimental_bearer_token') and
            (definition.get('requires_openai_auth') or provider == 'openai' and
             not definition.get('http_headers') and not definition.get('env_http_headers'))):
        names.add('OPENAI_API_KEY')
    try:
        auth_bytes = (Path(home) / 'auth.json').read_bytes()
        auth_hash = hashlib.sha256(auth_bytes).hexdigest()
    except OSError:
        auth_bytes = b''
        auth_hash = None
    if 'OPENAI_API_KEY' in names:
        try:
            if json.loads(auth_bytes).get('OPENAI_API_KEY'):
                names.discard('OPENAI_API_KEY')
        except (ValueError, AttributeError, TypeError):
            pass
    environment, process = read_daemon_environment(home, _remote_executable(home), names) if names else ({}, None)
    parts = [str(Path(home).resolve()), str(Path(cwd).resolve()), provider, config, account, auth_hash,
             {name: hashlib.sha256(value.encode()).hexdigest() for name, value in sorted(environment.items())},
             process]
    identity = hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()
    return environment, identity


def remote_model_worker(value):
    """Read only the selected daemon environment; never return its values."""
    operation = value.get('operation')
    if operation not in ('identity', 'models'):
        return {'error': '未知模型目录操作'}
    if sys.platform not in ('linux', 'darwin'):
        return {'error': 'SSH 原生 CLI 模型查询暂不支持此系统'}
    home, cwd, provider = value.get('home'), value.get('cwd'), value.get('provider')
    config, account = value.get('config'), value.get('account') or {}
    try:
        environment, identity = _environment_snapshot(home, cwd, provider, config, account)
    except (OSError, ValueError):
        return {'error': REMOTE_MODEL_ERROR}
    if operation == 'identity':
        return {'identity': identity}
    native = value.get('nativeModels') or []
    if not isinstance(native, list):
        return {'error': 'CLI 模型元数据格式无效'}

    def request(method, params):
        if method == 'config/read':
            return {'config': config}
        if method == 'account/read':
            return {'account': account}
        if method == 'model/list':
            return {'data': native}
        raise CatalogError('CLI 模型目录只允许只读请求')

    try:
        reader = Catalog(home, _remote_executable(home), allow_background_refresh=False)
        result = reader.read_models(request, cwd, provider, metadata_request=request, environment=environment)
        if result.get('modelSource') != 'api':
            return {'error': '当前原生 CLI 接入不是 API 模型目录，请手动填写模型 ID'}
        _, after = _environment_snapshot(home, cwd, provider, config, account)
        if identity != after:
            return {'error': REMOTE_MODEL_CHANGED}
        models = [{'id': item['model'], 'name': item.get('displayName') or item['model'],
                   'description': item.get('description', ''),
                   'efforts': [level['reasoningEffort'] for level in item.get('supportedReasoningEfforts') or []],
                   'defaultEffort': item.get('defaultReasoningEffort'), 'isDefault': False,
                   'fastTier': None, 'defaultServiceTier': None}
                  for item in result.get('models') or [] if isinstance(item, dict) and item.get('model')]
        return {'identity': identity, 'models': models, 'modelSource': 'api',
                'modelError': result.get('modelError')}
    except (OSError, ValueError, CatalogError, KeyError, TypeError):
        return {'error': REMOTE_MODEL_ERROR}
