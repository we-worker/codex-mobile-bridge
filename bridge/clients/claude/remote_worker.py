"""Standalone Claude CLI SSH source. Sent to the selected host; bridge is not installed there."""

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

MODES = {'default', 'acceptEdits', 'plan', 'dontAsk', 'auto', 'bypassPermissions'}


def draft_account_identity(directory, cwd=None, environment=None):
    """Use stable local account metadata without starting or querying Claude."""
    directory = Path(directory)
    selected = {name: value for name, value in (environment or {}).items()
                if name in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN',
                            'ANTHROPIC_BASE_URL') and isinstance(value, str) and value}
    files = [directory/'settings.json', directory/'settings.local.json']
    if cwd:
        files.extend((Path(cwd)/'.claude/settings.json', Path(cwd)/'.claude/settings.local.json'))
    for path in files:
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            continue
        settings = value.get('env') if isinstance(value, dict) else None
        if isinstance(settings, dict):
            selected.update({name: item for name, item in settings.items()
                             if name in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN',
                                         'CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_BASE_URL')
                             and isinstance(item, str) and item})
    key = selected.get('ANTHROPIC_API_KEY') or selected.get('ANTHROPIC_AUTH_TOKEN') or selected.get('CLAUDE_CODE_OAUTH_TOKEN')
    if key:
        value = ['claude-code-api', str(directory.resolve()), selected.get('ANTHROPIC_BASE_URL') or '', key]
        return hashlib.sha256(json.dumps(value, separators=(',', ':')).encode()).hexdigest()
    metadata_paths = [directory/'.claude.json']
    if directory.resolve() == Path.home()/'.claude':
        metadata_paths.insert(0, directory.parent/'.claude.json')
    for path in metadata_paths:
        try:
            metadata = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            continue
        account = metadata.get('oauthAccount') if isinstance(metadata, dict) else None
        if not isinstance(account, dict):
            continue
        user = account.get('accountUuid') or account.get('emailAddress')
        organization = account.get('organizationUuid') or account.get('organizationId') or ''
        if isinstance(user, str) and user:
            value = ['claude-code', str(directory.resolve()), user, organization]
            return hashlib.sha256(json.dumps(value, separators=(',', ':')).encode()).hexdigest()
    try:
        credential = (directory/'.credentials.json').read_bytes()
        if credential:
            return hashlib.sha256(b'claude-code-credential\0' + credential).hexdigest()
    except OSError:
        pass
    return ''


def auth_status(binary, directory):
    env = os.environ.copy()
    env['CLAUDE_CONFIG_DIR'] = str(directory)
    try:
        result = subprocess.run([binary, 'auth', 'status', '--json'], env=env,
                                capture_output=True, text=True, timeout=5)
        value = json.loads(result.stdout)
        return value if result.returncode == 0 and isinstance(value, dict) else {}
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}


def auth_fingerprint(binary, directory):
    status = auth_status(binary, directory)
    stable = {key: status[key] for key in ('authMethod', 'apiProvider', 'email', 'accountId',
              'accountUuid', 'organizationId', 'organizationUuid', 'orgId', 'workspaceId')
              if isinstance(status.get(key), str) and status[key]}
    credentials = Path(directory)/'.credentials.json'
    ambient = {key: os.environ[key] for key in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN',
               'CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_BASE_URL', 'ANTHROPIC_CUSTOM_HEADERS')
               if os.environ.get(key)}
    identity = {'loggedIn': status.get('loggedIn') is True, 'stable': stable,
                'ambient': ambient}
    if not any(key in stable for key in ('email', 'accountId', 'accountUuid',
                                        'organizationId', 'organizationUuid', 'orgId', 'workspaceId')):
        try:
            identity['credentials'] = hashlib.sha256(credentials.read_bytes()).hexdigest()
        except OSError:
            identity['credentials'] = 'none'
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def profile():
    binary = shutil.which('claude') or next((str(p) for p in
        (Path.home()/'.local/bin/claude', Path('/usr/local/bin/claude'))
        if p.is_file() and os.access(p, os.X_OK)), None)
    if not binary:
        return None
    explicit = os.environ.get('CLAUDE_CONFIG_DIR')
    directory = Path(explicit).expanduser().resolve() if explicit else Path.home()/'.claude'
    try:
        digest = hashlib.sha256((directory/'settings.json').read_bytes()).hexdigest()
    except OSError:
        digest = 'none'
    binary = str(Path(binary).resolve())
    auth = auth_fingerprint(binary, directory)
    return {'binary': binary, 'directory': str(directory),
            'origin': ('environment:' if explicit else 'default:') + str(directory) + ':' + digest + ':' + auth}


def auth_ready(found):
    return auth_status(found['binary'], found['directory']).get('loggedIn') is True


def events(path):
    if path.stat().st_size > 20_000_000:
        raise ValueError('Claude 会话记录过大')
    result = []
    with path.open(encoding='utf-8', errors='replace') as source:
        for line in source:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                result.append(event)
    return result


def saved(path, found, *, include_events=False):
    try:
        native = str(uuid.UUID(path.stem))
        if path.is_symlink() or not path.is_file():
            return None
        history = events(path)
    except (OSError, ValueError):
        return None
    users = [e for e in history if e.get('type') == 'user' and not e.get('isSidechain')]
    if not users:
        return None
    cwd = next((e.get('cwd') for e in reversed(history) if e.get('type') in ('user', 'assistant')
                and isinstance(e.get('cwd'), str) and e['cwd']), '')
    if not cwd:
        return None
    project_settings = []
    for name in ('settings.json', 'settings.local.json'):
        try:
            project_settings.append(hashlib.sha256((Path(cwd)/'.claude'/name).read_bytes()).hexdigest())
        except OSError:
            project_settings.append(None)
    assistants = [e for e in history if e.get('type') == 'assistant' and isinstance(e.get('message'), dict)]
    model = next((e['message'].get('model') for e in reversed(assistants)
                  if isinstance(e['message'].get('model'), str)), '')
    permission = next((e.get('mode') for e in reversed(history)
                       if e.get('type') == 'mode' and e.get('mode') in MODES), None)
    if permission is None:
        permission = next((e.get('permissionMode') for e in reversed(users)
                           if e.get('permissionMode') in MODES), None)
    first = users[0].get('message') or {}
    content = first.get('content', '') if isinstance(first, dict) else ''
    if isinstance(content, list):
        content = '\n'.join(e.get('text', '') for e in content if isinstance(e, dict) and e.get('type') == 'text')
    title = str(content).strip().splitlines()[0][:120] if str(content).strip() else 'Claude Code 会话'
    row = {'nativeId': native, 'origin': found['origin'], 'cwd': cwd, 'model': model,
           'projectConfig': hashlib.sha256(json.dumps(project_settings).encode()).hexdigest(),
           'permissionMode': permission or 'default', 'permissionKnown': permission is not None,
           'updatedAt': path.stat().st_mtime, 'title': title}
    if include_events:
        row['events'] = history
    return row


def sessions(found):
    root = Path(found['directory'])/'projects'
    if not root.is_dir() or root.is_symlink():
        return []
    result = []
    for directory in root.iterdir():
        if not directory.is_dir() or directory.is_symlink():
            continue
        for path in directory.glob('*.jsonl'):
            row = saved(path, found)
            if row:
                result.append(row)
    return result


def session(found, native):
    native = str(uuid.UUID(native))
    root = Path(found['directory'])/'projects'
    if not root.is_dir() or root.is_symlink():
        raise ValueError('原 Claude Code 会话不可用')
    for directory in root.iterdir():
        if directory.is_dir() and not directory.is_symlink():
            path = directory/(native+'.jsonl')
            if path.is_file() and not path.is_symlink():
                row = saved(path, found, include_events=True)
                if row:
                    return row
    raise ValueError('原 Claude Code 会话不可用')


def pid_domain():
    if sys.platform == 'linux':
        machine = Path('/etc/machine-id').read_text().strip()
        namespace = os.readlink('/proc/self/ns/pid')
        if not machine or not re.fullmatch(r'pid:\[\d+\]', namespace):
            raise ValueError('Linux 进程身份不可验证')
        return 'linux:' + machine + ':' + namespace
    if sys.platform == 'darwin':
        return 'darwin'
    raise ValueError('当前系统的 Claude 进程身份不可验证')


def linux_process_start(pid):
    # Kept standalone for SSH injection; matches platforms/linux/claude_process.py.
    try:
        stat = Path(f'/proc/{pid}/stat').read_text()
    except FileNotFoundError:
        return None
    fields = stat.rpartition(')')[2].split()
    if (not stat.startswith(f'{pid} (') or len(fields) < 20 or
            not re.fullmatch(r'[0-9]+', fields[19])):
        raise ValueError('无法核验 Claude Code 原会话是否仍在运行')
    return fields[19]


def assert_session_closed(found, native):
    directory = Path(found['directory'])/'sessions'
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError('无法核验 Claude Code 原会话是否仍在运行')
    domain = pid_domain()
    for path in directory.iterdir():
        if path.suffix != '.json':
            continue
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
            raise ValueError('无法核验 Claude Code 原会话是否仍在运行')
        entry = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(entry, dict):
            raise ValueError('无法核验 Claude Code 原会话是否仍在运行')
        if entry.get('sessionId') != native:
            continue
        pid = entry.get('pid')
        start = entry.get('procStart')
        if (type(pid) is not int or pid <= 0 or path.stem != str(pid) or
                not isinstance(start, str) or not start or entry.get('pidDomain') != domain):
            raise ValueError('无法核验 Claude Code 原会话是否仍在运行')
        if sys.platform == 'linux':
            if not re.fullmatch(r'[0-9]+', start):
                raise ValueError('无法核验 Claude Code 原会话是否仍在运行')
            if linux_process_start(pid) == start:
                raise ValueError('原 Claude Code 会话仍在其他终端运行')
            continue
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        except (PermissionError, OSError):
            raise ValueError('无法核验 Claude Code 原会话是否仍在运行') from None
        result = subprocess.run(['ps', '-p', str(pid), '-o', 'lstart='],
                                env={**os.environ, 'LC_ALL': 'C', 'TZ': 'UTC'},
                                capture_output=True, text=True, timeout=3)
        if result.returncode != 0 or not result.stdout.strip():
            raise ValueError('无法核验 Claude Code 原会话是否仍在运行')
        if result.stdout.split() == start.split():
            raise ValueError('原 Claude Code 会话仍在其他终端运行')


def upload_root(found, scope):
    uuid.UUID(scope)
    root = Path(found['directory'])/'mobile-bridge'/'uploads'
    path = root/scope
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any(part.is_symlink() for part in (root.parent, root, path)):
        raise ValueError('附件目录无效')
    return path.resolve()


def upload(found, request):
    identifier = str(uuid.UUID(request['id']))
    name = request['name']
    if not isinstance(name, str) or not name or len(name.encode()) > 200 or re.search(r'[\\/\x00-\x1f\x7f]', name):
        raise ValueError('附件文件名无效')
    data = base64.b64decode(request['data'], validate=True)
    if not 0 < len(data) <= 20*1024*1024 or hashlib.sha256(data).hexdigest() != request['sha256']:
        raise ValueError('附件内容不匹配')
    folder = upload_root(found, request['scope'])/identifier
    folder.mkdir(mode=0o700, exist_ok=True)
    if folder.is_symlink():
        raise ValueError('附件路径无效')
    suffix = Path(name).suffix.lower()
    if not re.fullmatch(r'\.[a-z0-9]{1,16}', suffix):
        suffix = '.bin'
    path = folder/('original'+suffix)
    if path.is_symlink():
        raise ValueError('附件路径无效')
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != request['sha256']:
            raise ValueError('附件标识已被其他文件使用')
    else:
        part = folder/'original.part'
        with part.open('xb') as stream:
            stream.write(data)
        part.chmod(0o600)
        part.replace(path)
    return {'path': str(path.resolve())}


def command(request):
    found = profile()
    operation = request.get('operation')
    if operation == 'list':
        return {'profile': found, 'sessions': sessions(found) if found else []}
    if operation == 'projects':
        return {'profile': found, 'sessions': sessions(found) if found else [],
                'authReady': auth_ready(found) if found else False}
    if not found or found['origin'] != request.get('origin'):
        raise ValueError('原 Claude Code 配置已变化或不可用')
    if operation == 'detail':
        row = session(found, request['native'])
        row['draftAccountIdentity'] = draft_account_identity(found['directory'], row['cwd'], os.environ)
        if request.get('events') is not True:
            row.pop('events', None)
        return row
    if operation == 'auth':
        return {'ready': auth_ready(found)}
    if operation == 'upload':
        return upload(found, request)
    raise ValueError('不支持的 Claude Code 远端操作')


def resume(request):
    found = profile()
    if not found or found['origin'] != request.get('origin'):
        raise ValueError('原 Claude Code 配置已变化或不可用')
    row = session(found, request['native'])
    if row['cwd'] != request.get('cwd') or row['model'] != request.get('model') or row['permissionMode'] != request.get('permissionMode'):
        raise ValueError('原 Claude Code 会话设置已变化')
    if not row['permissionKnown'] or not auth_ready(found):
        raise ValueError('原 Claude Code 账号或权限模式不可用')
    cwd = Path(row['cwd']).resolve(strict=True)
    if not cwd.is_dir():
        raise ValueError('原项目目录不可用')
    assert_session_closed(found, row['nativeId'])
    directory = upload_root(found, request['scope'])
    if profile() != found:
        raise ValueError('原 Claude Code 配置已变化或不可用')
    arguments = [found['binary'], '-p', '--resume', row['nativeId'], '--input-format', 'stream-json',
                 '--output-format', 'stream-json', '--verbose', '--replay-user-messages',
                 '--setting-sources', 'user,project,local', '--permission-mode', row['permissionMode'],
                 '--permission-prompt-tool', 'stdio', '--permission-prompts', 'host',
                 '--allow-dangerously-skip-permissions', '--add-dir', str(directory)]
    if row['model']:
        arguments.extend(('--model', row['model']))
    env = os.environ.copy()
    env['CLAUDE_CONFIG_DIR'] = found['directory']
    os.chdir(cwd)
    print(json.dumps({'type': 'bridge_preflight', 'status': 'ready', 'cwd': str(cwd)}), flush=True)
    os.execvpe(found['binary'], arguments, env)


def create(request):
    found = profile()
    if not found or found['origin'] != request.get('origin') or not auth_ready(found):
        raise ValueError('原 Claude Code 账号配置已变化或不可用')
    native = str(uuid.UUID(request['native']))
    cwd = Path(request['cwd']).resolve(strict=True)
    if not cwd.is_dir():
        raise ValueError('原项目目录不可用')
    directory = upload_root(found, request['scope'])
    if profile() != found:
        raise ValueError('原 Claude Code 配置已变化或不可用')
    arguments = [found['binary'], '-p', '--session-id', native, '--input-format', 'stream-json',
                 '--output-format', 'stream-json', '--verbose', '--replay-user-messages',
                 '--setting-sources', 'user,project,local', '--permission-prompt-tool', 'stdio',
                 '--permission-prompts', 'host', '--allow-dangerously-skip-permissions',
                 '--add-dir', str(directory)]
    env = os.environ.copy()
    env['CLAUDE_CONFIG_DIR'] = found['directory']
    os.chdir(cwd)
    print(json.dumps({'type': 'bridge_preflight', 'status': 'ready', 'cwd': str(cwd)}), flush=True)
    os.execvpe(found['binary'], arguments, env)


if __name__ == '__main__':
    try:
        request = json.loads(sys.stdin.readline())
        if request.get('operation') in ('resume', 'create'):
            (resume if request['operation'] == 'resume' else create)(request)
        else:
            print(json.dumps({'ok': True, 'value': command(request)}, ensure_ascii=False), flush=True)
    except Exception as exc:
        if 'request' in locals() and request.get('operation') in ('resume', 'create'):
            value = {'type': 'bridge_preflight', 'status': 'blocked', 'message': str(exc)[:300]}
        else:
            value = {'ok': False, 'message': str(exc)[:300]}
        print(json.dumps(value, ensure_ascii=False), flush=True)
