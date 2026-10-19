"""Selected-host Claude Code CLI sessions over SSH stdio."""

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import shlex
import subprocess
import threading
import time
import uuid
from pathlib import Path

from bridge.clients.claude import model
from bridge.clients.claude.context import context_fields
from bridge.clients.claude.cli_session import (_Owned, _message_content, _skill_catalog, _cli_catalog,
                                                _set_cli_settings, MODES,
                                                PERMISSION_OPTIONS, ResumePreflightBlocked)
from bridge.clients.codex.remote import ssh_command
from bridge.clients.errors import BridgeUnavailable
from bridge.clients.uploads import DesktopUploads
from bridge.resources import source_text


def _command(alias):
    source = source_text('clients/claude/remote_worker.py')
    inner = 'exec python3 -u -c ' + shlex.quote(source)
    return ssh_command(alias)[:-1] + ['exec "$SHELL" -lc ' + shlex.quote(inner)]


def _remote(alias, request, timeout=30):
    try:
        result = subprocess.run(_command(alias), input=json.dumps(request, ensure_ascii=False)+'\n',
                                capture_output=True, text=True, encoding='utf-8', timeout=timeout)
        if result.returncode != 0:
            raise BridgeUnavailable('SSH Claude Code 主机不可用，请检查连接')
        value = json.loads(result.stdout.strip())
        if value.get('ok') is not True:
            raise BridgeUnavailable(value.get('message') or 'SSH Claude Code 读取失败')
        return value['value']
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        raise BridgeUnavailable('SSH Claude Code 主机不可用，请检查连接') from exc


class RemoteClaudeCli:
    def __init__(self, hosts=None):
        self.hosts = hosts
        self.lock = threading.RLock()
        self.index = {}
        self.history = {}
        self.listed = False
        self.refreshing = False
        self.last_refresh = 0
        self.host_snapshot = {}
        self.complete = False
        self.owned = {}
        self.closed = False

    def available(self):
        return not self.closed and self.hosts is not None and bool(self.hosts.hosts())

    def busy(self):
        with self.lock:
            for owned in self.owned.values():
                if owned.process.poll() is None:
                    with owned.condition:
                        if owned.active or owned.pending:
                            return True
        return False

    def _row(self, host_id, host, raw):
        native = raw['nativeId']
        origin = raw['origin']
        sid = model.gateway_id('cli:ssh:'+host_id+':'+origin, native)
        return {**raw, 'id': sid, 'backend': 'cli', 'mode': 'cli', 'host': host_id,
                'hostLabel': host.get('displayName') or host['alias'], 'alias': host['alias'],
                'archived': False}

    def _fetch(self, item):
        host_id, host = item
        try:
            result = _remote(host['alias'], {'operation': 'list'}, timeout=20)
            if not isinstance(result, dict):
                raise ValueError('SSH Claude Code 列表格式无效')
            return host_id, host, result
        except (BridgeUnavailable, ValueError):
            return host_id, host, None

    def _refresh(self, hosts):
        rows = {}
        complete = True
        with ThreadPoolExecutor(max_workers=min(4, max(1, len(hosts)))) as pool:
            futures = [pool.submit(self._fetch, item) for item in hosts.items()]
            for future in as_completed(futures):
                host_id, host, result = future.result()
                with self.lock:
                    previous = dict(self.index)
                if result is None:
                    complete = False
                    rows.update({sid: row for sid, row in previous.items()
                                 if row['host'] == host_id and row['alias'] == host['alias']})
                    continue
                for item in result.get('sessions') or []:
                    if isinstance(item, dict) and item.get('nativeId') and item.get('origin'):
                        row = self._row(host_id, host, item)
                        rows[row['id']] = row
                origin = (result.get('profile') or {}).get('origin')
                with self.lock:
                    rows.update({sid: row for sid, row in previous.items()
                                 if row['host'] == host_id and row['alias'] == host['alias']
                                 and row['origin'] == origin and sid in self.owned
                                 and self.owned[sid].process.poll() is None})
        with self.lock:
            trusted = self.hosts.hosts() if self.hosts else {}
            self.index = {sid: row for sid, row in rows.items()
                          if row['host'] in trusted and trusted[row['host']]['alias'] == row['alias']}
            self.history = {sid: events for sid, events in self.history.items() if sid in self.index}
            self.host_snapshot = hosts
            self.last_refresh = time.monotonic()
            self.complete = complete
            self.listed = True
            self.refreshing = False

    def listing(self):
        if self.closed or self.hosts is None:
            return {'connected': False, 'sessions': [], 'complete': True}
        hosts = self.hosts.hosts()
        with self.lock:
            if not self.refreshing and (hosts != self.host_snapshot or time.monotonic()-self.last_refresh >= 10):
                self.refreshing = True
                threading.Thread(target=self._refresh, args=(hosts,), daemon=True,
                                 name='claude-ssh-list').start()
            rows = {sid: row for sid, row in self.index.items()
                    if row['host'] in hosts and hosts[row['host']]['alias'] == row['alias']}
            return {'connected': bool(hosts), 'sessions': [self._public(row) for row in rows.values()],
                    'complete': self.complete and not self.refreshing and hosts == self.host_snapshot}

    def contains(self, sid):
        with self.lock:
            if sid in self.index:
                return True
            listed = self.listed
        if not listed:
            self.listing()
        with self.lock:
            return sid in self.index

    def projects(self):
        if self.closed or self.hosts is None:
            return []
        configured = self.hosts.hosts()
        known = self.hosts.projects()
        rows = []
        def discover(host_id, host):
            cwds = {item['cwd'] for item in known if item.get('host') == host_id}
            try:
                result = _remote(host['alias'], {'operation': 'projects'}, timeout=12)
                found = result.get('profile')
                if not found or not result.get('authReady'):
                    return []
            except BridgeUnavailable:
                return []
            cwds.update(item['cwd'] for item in result.get('sessions') or []
                    if isinstance(item, dict) and isinstance(item.get('cwd'), str))
            discovered = []
            for cwd in sorted(cwds):
                if not cwd.startswith('/'):
                    continue
                discovered.append({'key': model.gateway_id('cli:project:ssh:'+host_id+':'+found['origin'], cwd),
                                   'name': Path(cwd).name+' · '+(host.get('displayName') or host['alias']),
                                   'cwd': cwd, 'surface': 'cli', 'host': host_id,
                                   'alias': host['alias'], 'origin': found['origin'],
                                   'createRequiresMessage': True})
            return discovered
        with ThreadPoolExecutor(max_workers=min(4, max(1, len(configured)))) as pool:
            futures = [pool.submit(discover, host_id, host) for host_id, host in configured.items()]
            for future in as_completed(futures):
                rows.extend(future.result())
        return rows

    def _get(self, sid, *, events=False):
        with self.lock:
            row = self.index.get(sid)
        if row is None:
            self.listing()
            with self.lock:
                row = self.index.get(sid)
        if row is None or self.hosts is None:
            raise ValueError('找不到 SSH Claude Code 会话')
        host = self.hosts.hosts().get(row['host'])
        if not host or host['alias'] != row['alias']:
            raise ValueError('原 SSH 主机配置已变化')
        fresh = _remote(row['alias'], {'operation': 'detail', 'native': row['nativeId'],
                                       'origin': row['origin'], 'events': events})
        if model.gateway_id('cli:ssh:'+row['host']+':'+fresh['origin'], fresh['nativeId']) != sid:
            raise ValueError('原 SSH Claude Code 会话身份已变化')
        updated = self._row(row['host'], host, fresh)
        with self.lock:
            self.index[sid] = {key: value for key, value in updated.items() if key != 'events'}
        if not events:
            updated.pop('events', None)
        return updated

    def _public(self, row):
        value = {key: item for key, item in row.items() if key not in
                 ('events', 'origin', 'alias', 'permissionKnown', 'projectConfig')}
        value.update(context_fields(row.get('events') or []))
        owned = self.owned.get(row['id'])
        live = bool(owned and owned.origin == row['origin'] and owned.process.poll() is None and not owned.error)
        if live:
            with owned.condition:
                pending, active = dict(owned.pending), owned.active
        else:
            pending, active = {}, False
        value.update(status='active' if active else 'idle', runtimeKnown=True,
                     connectionState='awaiting' if pending else 'active' if active else 'ready' if live else 'closed',
                     requests=[{'id': rid, 'tool': event['request'].get('tool_name', '工具'),
                                'input': event['request'].get('input', {}),
                                'needsInput': event['request'].get('tool_name') == 'AskUserQuestion'}
                               for rid, event in pending.items()])
        if live:
            value['model'] = owned.model or value['model']
            value['permissionMode'] = owned.permission or value['permissionMode']
        return value

    def _upload_files(self, row, files):
        result = []
        scope = DesktopUploads.scope('claude', row['id'])
        for item in files:
            identifier = str(uuid.UUID(item['id']))
            path = Path(item['path'])
            data = path.read_bytes()
            if not 0 < len(data) <= 20*1024*1024:
                raise ValueError('文件附件大小无效')
            digest = hashlib.sha256(data).hexdigest()
            remote = _remote(row['alias'], {'operation': 'upload', 'origin': row['origin'],
                'scope': scope, 'id': identifier, 'name': item['name'], 'sha256': digest,
                'data': base64.b64encode(data).decode('ascii')}, timeout=90)
            result.append({'name': item['name'], 'path': remote['path']})
        return result

    def create(self, host_id, alias, origin, cwd, message):
        host = self.hosts.hosts().get(host_id) if self.hosts else None
        if not host or host['alias'] != alias:
            raise ValueError('原 SSH 主机配置已变化')
        preflight = _remote(alias, {'operation': 'projects'}, timeout=12)
        fresh = preflight.get('profile')
        if not fresh or fresh['origin'] != origin or not preflight.get('authReady'):
            raise BridgeUnavailable('原 SSH Claude Code 账号配置已变化或不可用')
        native = str(uuid.uuid4())
        sid = model.gateway_id('cli:ssh:'+host_id+':'+origin, native)
        process = subprocess.Popen(_command(alias), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True, encoding='utf-8', bufsize=1)
        try:
            process.stdin.write(json.dumps({'operation': 'create', 'origin': origin,
                'native': native, 'cwd': cwd, 'scope': DesktopUploads.scope('claude', sid)})+'\n')
            process.stdin.flush()
        except OSError:
            process.terminate()
            raise BridgeUnavailable('SSH Claude Code 新建结果不明，请检查会话列表') from None
        owned = _Owned(process, origin, native, cwd)
        with owned.condition:
            owned.condition.wait_for(lambda: owned.preflight is not None or owned.finished, timeout=20)
            blocked = owned.preflight and owned.preflight.get('status') == 'blocked'
        if blocked:
            error = owned.error
            owned.close()
            raise BridgeUnavailable(error)
        if owned.preflight is None:
            owned.close()
            raise BridgeUnavailable('SSH Claude Code 新建结果不明，请检查会话列表')
        try:
            owned.catalog = owned.control({'subtype': 'initialize', 'hooks': None}, timeout=30)
            if owned.error:
                raise BridgeUnavailable(owned.error)
            owned.permission = owned.catalog.get('current_permission_mode')
            with self.lock:
                self.owned[sid] = owned
            message_id = str(uuid.uuid4())
            with owned.condition:
                owned.active = True
                owned.write({'type': 'user', 'uuid': message_id,
                             'message': {'role': 'user', 'content': message}})
                acknowledged = owned.condition.wait_for(
                    lambda: message_id in owned.user_acks or owned.finished or owned.error,
                    timeout=20)
                if not acknowledged or message_id not in owned.user_acks:
                    raise BridgeUnavailable('SSH Claude Code 新建消息结果不明，请检查会话列表')
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    saved = _remote(alias, {'operation': 'detail', 'origin': origin,
                                            'native': native, 'events': False}, timeout=5)
                except BridgeUnavailable:
                    saved = None
                if saved and saved['cwd'] == owned.cwd and saved['origin'] == origin:
                    row = self._row(host_id, host, saved)
                    with self.lock:
                        self.index[sid] = row
                    return {'status': 'ready', 'result': {'id': sid}}
                time.sleep(.2)
            raise BridgeUnavailable('SSH Claude Code 新建记录尚未出现，请检查会话列表')
        except Exception:
            with self.lock:
                retained = sid in self.owned
            if not retained:
                owned.close()
            raise

    def call(self, action, sid, body):
        try:
            with self.lock:
                cached = self.index.get(sid)
                owned_cached = self.owned.get(sid)
            host = self.hosts.hosts().get(cached['host']) if cached and self.hosts else None
            live_cached = bool(cached and host and host['alias'] == cached['alias'] and
                               owned_cached and owned_cached.origin == cached['origin'] and
                               owned_cached.process.poll() is None and not owned_cached.error)
            if live_cached and action != 'resume':
                if action == 'detail':
                    try:
                        row = self._get(sid, events=True)
                        with self.lock:
                            self.history[sid] = row['events']
                    except BridgeUnavailable:
                        row = {**cached, 'events': self.history.get(sid, [])}
                else:
                    row = cached
            else:
                row = self._get(sid, events=action == 'detail')
                if action == 'detail':
                    with self.lock:
                        self.history[sid] = row['events']
        except (ValueError, BridgeUnavailable) as exc:
            if action == 'resume':
                raise ResumePreflightBlocked(str(exc)) from exc
            raise
        with self.lock:
            owned = self.owned.get(sid)
            if owned and (owned.origin != row['origin'] or owned.process.poll() is not None):
                owned = None
            public = self._public(row)
            live = owned is not None and not owned.error
            if action == 'detail':
                history = row['events']
                if live:
                    with owned.condition:
                        history = history + list(owned.events)
                public.update(context_fields(history))
                messages = model.transcript(history)
                ready = False
                if not live and row['permissionKnown']:
                    try:
                        ready = _remote(row['alias'], {'operation': 'auth', 'origin': row['origin']}, timeout=12)['ready']
                    except BridgeUnavailable:
                        pass
                return {'connected': True, 'session': public,
                        'messages': list({item['id']: item for item in messages}.values()),
                        'turns': model.turns(history),
                        'notice': '无法确认原会话权限模式，请在远端终端继续' if not live and not row['permissionKnown'] else '',
                        'capabilities': {'resume': not live and ready, 'send': live and public['connectionState'] == 'ready',
                                         'models': live, 'permissions': live, 'stop': live,
                                         'attachments': True, 'queue': False, 'steer': False, 'skills': live}}
            if action == 'catalog':
                if not live:
                    return {'models': [], 'capabilities': {'models': False}, 'notice': '请先继续这条 Claude Code 会话'}
                return _cli_catalog(owned, public, body.get('refresh') is True)
            if action == 'access' and 'mode' not in body:
                return {'status': 'accepted', 'mode': public['permissionMode'],
                        'options': [{'value': mode, 'label': label, 'description': description}
                                    for mode, label, description in PERMISSION_OPTIONS] if live else []}
            if action == 'resume':
                if live:
                    return {'status': 'ready'}
                if not row['permissionKnown'] or row['permissionMode'] not in MODES:
                    raise ResumePreflightBlocked('无法确认原会话权限模式')
                process = subprocess.Popen(_command(row['alias']), stdin=subprocess.PIPE,
                                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                           text=True, encoding='utf-8', bufsize=1)
                try:
                    process.stdin.write(json.dumps({'operation': 'resume', 'origin': row['origin'],
                        'native': row['nativeId'], 'cwd': row['cwd'], 'model': row['model'],
                        'permissionMode': row['permissionMode'],
                        'scope': DesktopUploads.scope('claude', sid)})+'\n')
                    process.stdin.flush()
                except OSError:
                    process.terminate()
                    raise BridgeUnavailable('SSH Claude Code 恢复结果不明，请检查原会话') from None
                owned = _Owned(process, row['origin'], row['nativeId'], row['cwd'])
                with owned.condition:
                    owned.condition.wait_for(lambda: owned.preflight is not None or owned.finished, timeout=20)
                    blocked = owned.preflight and owned.preflight.get('status') == 'blocked'
                if blocked:
                    message = owned.error
                    owned.close()
                    raise ResumePreflightBlocked(message)
                if owned.preflight is None:
                    owned.close()
                    raise BridgeUnavailable('SSH Claude Code 恢复结果不明，请检查原会话')
                try:
                    owned.catalog = owned.control({'subtype': 'initialize', 'hooks': None}, timeout=30)
                    if owned.error:
                        raise BridgeUnavailable(owned.error)
                    owned.permission = owned.catalog.get('current_permission_mode') or row['permissionMode']
                    if owned.permission != row['permissionMode']:
                        raise BridgeUnavailable('Claude Code 未保留原会话权限模式')
                except Exception:
                    owned.close()
                    raise
                self.owned[sid] = owned
                return {'status': 'ready'}
            if not live:
                raise BridgeUnavailable('请先继续这条 SSH Claude Code 会话')
            if action == 'send':
                if body.get('mode') in ('queue', 'steer'):
                    raise ValueError('Claude Code CLI 暂不支持此发送选项')
                selected = body.get('plugins') or []
                if not isinstance(selected, list) or len(selected) > 1:
                    raise ValueError('Claude Code CLI 每条消息只能调用一个 Skill')
                if selected and selected[0] not in {skill['id'] for skill in _skill_catalog(owned.catalog)
                                                    if skill['selectable']}:
                    raise ValueError('技能已不可用，请刷新后选择')
                with owned.condition:
                    if owned.active or owned.pending:
                        raise BridgeUnavailable('请等待当前 Claude Code 任务结束后再发送')
                files = self._upload_files(row, body.get('resolvedFiles') or [])
                message = ('/'+selected[0]+(' '+body['text'] if body['text'].strip() else '')
                           if selected else body['text'])
                content = _message_content({**body, 'text': message, 'resolvedFiles': files})
                with owned.condition:
                    if owned.active or owned.pending:
                        raise BridgeUnavailable('请等待当前 Claude Code 任务结束后再发送')
                    owned.active = True
                    message_id = str(uuid.uuid4())
                    owned.write({'type': 'user', 'uuid': message_id,
                                 'message': {'role': 'user', 'content': content}})
                    acknowledged = owned.condition.wait_for(
                        lambda: message_id in owned.user_acks or owned.finished or owned.error,
                        timeout=20)
                    if not acknowledged or message_id not in owned.user_acks:
                        raise BridgeUnavailable('SSH Claude Code 发送结果不明，请检查原会话')
            elif action == 'stop':
                owned.control({'subtype': 'interrupt'})
            elif action == 'settings':
                _set_cli_settings(owned, body)
            elif action == 'access':
                mode = body.get('mode')
                if mode not in MODES:
                    raise ValueError('请选择 Claude Code 提供的权限模式')
                if mode == 'bypassPermissions' and body.get('confirmed') is not True:
                    raise ValueError('完全访问需要明确确认')
                result = owned.control({'subtype': 'set_permission_mode', 'mode': mode})
                if result.get('mode') != mode:
                    raise BridgeUnavailable('Claude Code 未确认权限模式')
                with owned.condition:
                    deadline = time.monotonic() + 5
                    while owned.permission != mode and owned.process.poll() is None and time.monotonic() < deadline:
                        owned.condition.wait(max(0, deadline-time.monotonic()))
                    if owned.permission != mode:
                        raise BridgeUnavailable('Claude Code 尚未报告生效的权限模式，请刷新检查')
            elif action == 'respond':
                rid = body.get('requestId')
                with owned.condition:
                    pending = owned.pending.get(rid)
                if not pending:
                    raise ValueError('请求已处理或过期')
                decision = {'accept': 'allow', 'decline': 'deny'}.get(body.get('decision'))
                if not decision:
                    raise ValueError('请选择本次允许或拒绝')
                response = {'behavior': decision}
                if decision == 'allow':
                    updated = dict(pending['request'].get('input', {}))
                    if pending['request'].get('tool_name') == 'AskUserQuestion':
                        answers = {}
                        for index, question in enumerate(updated.get('questions') or []):
                            key = str(question.get('id') or question.get('question') or index)
                            values = ((body.get('answers') or {}).get(key) or {}).get('answers') or []
                            if not values or not all(isinstance(value, str) for value in values):
                                raise ValueError('请回答每一项问题')
                            answers[question['question']] = ', '.join(values)
                        updated['answers'] = answers
                    response['updatedInput'] = updated
                else:
                    response['message'] = '用户拒绝了本次操作'
                with owned.condition:
                    if owned.pending.pop(rid, None) is not pending:
                        raise ValueError('请求已处理或过期')
                owned.write({'type': 'control_response', 'response': {'subtype': 'success',
                             'request_id': rid, 'response': response}})
            else:
                raise ValueError('不支持的 Claude Code 操作')
            return {'status': 'accepted'}

    def close(self):
        with self.lock:
            self.closed = True
            for owned in self.owned.values():
                owned.close()
            self.owned.clear()
