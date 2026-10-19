"""Own one foreground Serve/Funnel session; never reset the user's tailnet."""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

from bridge.features.notifications.channels import read_json, write_json
from bridge.resources import project_root


EMBEDDED_ERRORS = {
    'funnel_unavailable': 'Tailscale Funnel 尚未为此网络启用，或当前账号没有 Funnel 权限。'
                         '请先在 Tailscale 管理后台启用 HTTPS / Funnel；私有组网可改用 Serve。',
    'https_unavailable': 'Tailscale 尚未为当前网络启用 HTTPS 或 MagicDNS，请先在管理后台开启。',
    'authentication_failed': '内嵌 Tailscale 登录失败，请重新授权或检查认证密钥。',
    'listener_failed': '内嵌 Tailscale 无法监听所选 HTTPS 端口，请检查端口或切换为 8443/10000。',
    'invalid_configuration': '内嵌 Tailscale 配置无效，请检查设备名称、端口和运行方式。',
    'invalid_launch': '无法把登录凭据安全交给内嵌 Tailscale。',
    'verification_failed': '内嵌 Tailscale 已启动，但尚未验证它确实连到当前网关；'
                           '正在等待 Tailscale 域名或 Funnel 生效后重试。',
    'tailscale_failed': '内嵌 Tailscale 未能连接，请检查网络和管理员策略。',
    'stopped': '内嵌 Tailscale 已停止。',
}


def is_embedded(entry):
    return entry.get('tailscaleRuntime', 'system') == 'embedded'


def embedded_executable():
    name = 'codex-tsnet.exe' if os.name == 'nt' else 'codex-tsnet'
    bundle = Path(getattr(sys, '_MEIPASS', project_root() / 'dist'))
    candidates = [bundle/'tsnet'/name, project_root()/'dist/tsnet'/name]
    found = shutil.which('codex-tsnet')
    if found:
        candidates.append(Path(found))
    return next((str(path) for path in candidates
                 if path.is_file() and os.access(path, os.X_OK)), '')


def executable():
    if sys.platform == 'darwin':
        from bridge.platforms.macos import tailscale as native
    elif sys.platform == 'win32':
        from bridge.platforms.windows import tailscale as native
    else:
        from bridge.platforms.linux import tailscale as native
    candidates = native.candidates()
    found = shutil.which('tailscale')
    if found:
        candidates.append(Path(found))
    return next((str(p) for p in candidates if p.is_file() and os.access(p, os.X_OK)), '')


def command_json(binary, arguments):
    try:
        result = subprocess.run([binary, *arguments], stdin=subprocess.DEVNULL, capture_output=True,
                                encoding='utf-8', errors='replace', timeout=8,
                                **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('无法连接 Tailscale，请打开客户端并检查系统网络权限。') from exc
    try:
        value = json.loads(result.stdout)
        if not isinstance(value, dict):
            raise ValueError()
    except (ValueError, TypeError) as exc:
        # CLI output can contain account details and login URLs; do not relay it.
        raise ValueError('无法读取 Tailscale 状态，请更新官方客户端并完成登录。') from exc
    if result.returncode and not value.get('BackendState'):
        raise ValueError('无法读取 Tailscale 状态，请更新官方客户端并完成登录。')
    return value


def authorization_url(value):
    if not isinstance(value, str) or len(value) > 2048 or any(c.isspace() for c in value):
        return ''
    try:
        parsed = urlsplit(value)
        if (parsed.scheme == 'https' and parsed.hostname == 'login.tailscale.com'
                and parsed.port in (None, 443) and not parsed.username and not parsed.password):
            return value
    except ValueError:
        pass
    return ''


def device_url(status, port):
    host = status.get('Self', {}).get('DNSName', '').rstrip('.').lower()
    if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+ts\.net', host):
        raise ValueError('Tailscale 尚未提供固定域名，请启用 MagicDNS 并完成登录。')
    return 'https://' + host + (':' + str(port) if port != 443 else '')


def port_in_use(config, port):
    """Foreground sessions and background rules belong to their original owners."""
    if not isinstance(config, dict):
        return False
    if str(port) in config.get('TCP', {}):
        return True
    if any(str(host).rsplit(':', 1)[-1] == str(port) for host in config.get('Web', {})):
        return True
    return any(port_in_use(item, port) for item in config.get('Foreground', {}).values())


def identity_url(host, port):
    host = host.rstrip('.').lower()
    if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+ts\.net', host):
        raise ValueError('Tailscale 尚未提供固定域名，请启用 MagicDNS 并完成登录。')
    return 'https://' + host + (':' + str(port) if port != 443 else '')


def status_path(data_dir, entry):
    return Path(data_dir)/('ssh-status-' + entry['id'] + '.json')


def embedded_status(entry, data_dir, runtime_pid=None, instance_id=None):
    if not data_dir:
        return {}
    value = read_json(status_path(data_dir, entry), {})
    if not isinstance(value, dict):
        return {}
    if runtime_pid is not None and value.get('pid') != runtime_pid:
        return {}
    if instance_id is not None and value.get('instanceId') != instance_id:
        return {}
    return value


def inspect_embedded(entry, data_dir=None, runtime_pid=None, instance_id=None):
    binary = embedded_executable()
    if not binary:
        return {'state': 'missing', 'available': False,
                'message': '当前版本未包含内嵌 Tailscale 程序，请使用完整桌面安装包。'}
    status = embedded_status(entry, data_dir, runtime_pid, instance_id)
    state = status.get('state')
    if state == 'connected' and status.get('url') and status.get('nodeId'):
        return {'state': 'ready', 'available': True, 'runtime': 'embedded',
                'url': status['url'], 'nodeId': status['nodeId'],
                'message': '已读取内嵌 Tailscale 的固定地址。地址只对当前已登记设备身份生效。'}
    if state == 'authorization':
        return {'state': 'authorization', 'available': True, 'runtime': 'embedded',
                'authUrl': authorization_url(status.get('authUrl', '')),
                'message': '请在 Tailscale 官方页面完成内嵌节点授权，然后重新检测。'}
    if state in ('starting', 'connecting', 'retrying', 'authenticating'):
        return {'state': 'starting', 'available': True, 'runtime': 'embedded',
                'message': status.get('message') or '内嵌 Tailscale 正在启动。'}
    if state in ('blocked', 'failed'):
        return {'state': state, 'available': True, 'runtime': 'embedded',
                'message': status.get('message') or '内嵌 Tailscale 暂不可用。'}
    return {'state': 'stopped', 'available': True, 'runtime': 'embedded',
            'message': '内嵌 Tailscale 尚未启动。保存配置并启动网关后，点击继续授权并重新检测。'}


def inspect(entry, data_dir=None, runtime_pid=None, instance_id=None):
    if is_embedded(entry):
        return inspect_embedded(entry, data_dir, runtime_pid, instance_id)
    binary = executable()
    if not binary:
        return {'state': 'missing', 'available': False,
                'message': '未找到 Tailscale，请先安装官方客户端并完成登录。'}
    status = command_json(binary, ['status', '--json'])
    version = str(status.get('Version', ''))
    match = re.match(r'(\d+)\.(\d+)', version)
    if not match or tuple(map(int, match.groups())) < (1, 52):
        raise ValueError('请更新 Tailscale 至 1.52 或更高版本。')
    if status.get('BackendState') != 'Running':
        return {'state': 'login', 'available': True, 'version': version,
                'authUrl': authorization_url(status.get('AuthURL', '')),
                'message': '请在 Tailscale 客户端完成登录并开启连接，然后重新检测。'}
    node = status.get('Self') or {}
    if node.get('KeyExpired'):
        raise ValueError('Tailscale 设备授权已过期，请重新登录。')
    node_id = node.get('ID', '')
    if not isinstance(node_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', node_id):
        raise ValueError('无法读取 Tailscale 设备身份，请更新官方客户端并完成登录。')
    return {'state': 'ready', 'available': True, 'version': version,
            'url': device_url(status, entry.get('tailscalePort', 443)), 'nodeId': node_id,
            'message': '已读取 Tailscale 固定地址。保存配置后启动网关，再检测固定入口。'}


def require_identity(entry):
    if is_embedded(entry):
        if not embedded_executable():
            raise ValueError('当前版本未包含内嵌 Tailscale 程序，请使用完整桌面安装包。')
        return {'state': 'pending', 'available': True, 'runtime': 'embedded'}
    state = inspect(entry)
    if state['state'] != 'ready':
        raise ValueError(state['message'])
    if state['url'] != entry.get('publicUrl') or state['nodeId'] != entry.get('tailscaleNodeId'):
        raise ValueError('Tailscale 账号或设备地址已变化，请重新检测并保存连接配置。')
    return state


def embedded_credentials(entry, data_dir, temporary=None):
    if temporary is not None:
        return temporary
    if is_embedded(entry) and entry.get('tailscaleAuthMode') == 'authKey':
        from bridge.features.accounts.secrets import read
        return read(data_dir, entry['id'])
    return {}


def check_entry_embedded(entry, data_dir, runtime_pid, instance_id):
    status = embedded_status(entry, data_dir, runtime_pid)
    if status.get('state') != 'connected':
        raise ValueError(status.get('message') or '内嵌 Tailscale 入口尚未连接')
    url = str(status.get('url') or '')
    if ((entry.get('publicUrl') and url != entry.get('publicUrl'))
            or (entry.get('tailscaleNodeId') and status.get('nodeId') != entry.get('tailscaleNodeId'))):
        raise ValueError('内嵌 Tailscale 设备地址或身份已变化，请重新检测并确认')
    if not instance_id or status.get('instanceId') != instance_id:
        raise ValueError('内嵌 Tailscale 入口没有连到当前网关；请重启网关后再检测')
    return {'message': '内嵌 Tailscale 已通过自身网络访问当前网关。'
                       '请再用手机验证登录与聊天。',
            'url': url}


class TailscaleTunnel:
    def __init__(self, entry, port, data_dir, secrets=None, allow_origin=None, instance_id=''):
        self.entry, self.port, self.data_dir = entry, port, Path(data_dir)
        self.secrets = secrets or {}
        self.allow_origin = allow_origin
        self.instance_id = instance_id
        self.stopped = threading.Event()
        self.lock = threading.Lock()
        self.process = self.thread = None
        self.last_status = None

    def status(self, state, message, auth_url='', url=None, node_id=None, instance_id=''):
        instance_id = instance_id or self.instance_id
        record = {'pid': os.getpid(), 'state': state, 'message': message,
                  'runtime': self.entry.get('tailscaleRuntime', 'system'),
                  'url': self.entry['publicUrl'] if url is None else url,
                  'authUrl': authorization_url(auth_url)}
        if node_id is not None:
            record['nodeId'] = node_id
        if instance_id:
            record['instanceId'] = instance_id
        if self.process:
            record['childPid'] = self.process.pid
        if record != self.last_status:
            write_json(status_path(self.data_dir, self.entry), record)
            self.last_status = record

    def start(self):
        self.thread = threading.Thread(target=self._run, name='tailscale-entry', daemon=True)
        self.thread.start()

    def _run(self):
        if is_embedded(self.entry):
            self._run_embedded()
        else:
            self._run_system()

    def _publish_origin(self, origin='', node_id=''):
        if self.allow_origin:
            self.allow_origin(self.entry['id'], origin or '', node_id or '')

    def _run_system(self):
        delay = 3
        while not self.stopped.is_set():
            self.status('connecting', '正在建立 Tailscale 固定入口…')
            process = None
            try:
                require_identity(self.entry)
                binary = executable()
                config = command_json(binary, ['serve', 'status', '--json'])
                if port_in_use(config, self.entry['tailscalePort']):
                    self.status('blocked', '此 Tailscale 端口已被其他服务使用，请选择其他端口；不会覆盖已有配置。')
                    return
                # Foreground sessions are removed by tailscaled when this CLI
                # disconnects. Never use --bg, reset, down, or logout here.
                flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
                with self.lock:
                    if self.stopped.is_set():
                        return
                    process = self.process = subprocess.Popen(
                        [binary, self.entry['tailscaleMode'], '--https=' + str(self.entry['tailscalePort']),
                         'http://127.0.0.1:' + str(self.port)], stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                        encoding='utf-8', errors='replace', **flags)
                for line in process.stdout:
                    if self.stopped.is_set():
                        break
                    urls = re.findall(r'https://[^\s<>"\x1b]+', line)
                    auth_url = next((authorization_url(url) for url in urls if authorization_url(url)), '')
                    if auth_url:
                        self.status('authorization', '请完成 Tailscale HTTPS 或 Funnel 授权，完成后会继续连接。', auth_url)
                    elif 'Available on the internet' in line or 'Available within your tailnet' in line:
                        delay = 3
                        self.status('connected', 'Tailscale 入口已启动，请检测固定入口并用手机验证。')
                process.wait()
            except (OSError, ValueError) as exc:
                if not self.stopped.is_set():
                    self.status('retrying', str(exc) if isinstance(exc, ValueError) else 'Tailscale 入口已断开，正在重试。')
            finally:
                if process:
                    self._terminate(process)
                    if process.stdout:
                        process.stdout.close()
                with self.lock:
                    self.process = None
            if self.stopped.is_set():
                break
            if self.last_status and self.last_status['state'] in ('connected', 'connecting', 'authorization'):
                self.status('retrying', 'Tailscale 入口未保持连接，请检查客户端、网络及 Funnel 授权。')
            if self.stopped.wait(delay):
                break
            delay = min(60, delay * 2)

    def _run_embedded(self):
        delay = 3
        while not self.stopped.is_set():
            self._publish_origin()
            self.status('connecting', '正在启动 App 内嵌 Tailscale…')
            process = None
            try:
                binary = embedded_executable()
                if not binary:
                    self.status('missing', '当前版本未包含内嵌 Tailscale 程序，请使用完整桌面安装包。')
                    return
                state_dir = self.data_dir/'tsnet'/self.entry['id']
                state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
                argv = [
                    binary,
                    '--state-dir', str(state_dir),
                    '--hostname', self.entry.get('tailscaleHostname') or 'codex-mobile-bridge',
                    '--mode', self.entry['tailscaleMode'],
                    '--port', str(self.entry['tailscalePort']),
                    '--upstream', 'http://127.0.0.1:' + str(self.port),
                ]
                if self.instance_id:
                    argv.extend(['--instance-id', self.instance_id])
                with self.lock:
                    if self.stopped.is_set():
                        return
                    process = self.process = subprocess.Popen(
                        argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                        errors='replace', **flags)
                launch = {'authKey': self.secrets.get('authKey', '')}
                process.stdin.write(json.dumps(launch, ensure_ascii=False) + '\n')
                process.stdin.flush()
                process.stdin.close()
                for line in process.stdout:
                    if self.stopped.is_set():
                        break
                    try:
                        event = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    if not isinstance(event, dict):
                        continue
                    state = event.get('state')
                    if state == 'auth_required':
                        self.status('authorization', '请完成内嵌 Tailscale 登录授权，完成后会继续连接。',
                                    event.get('authUrl', ''))
                    elif state in ('listening', 'connected'):
                        url = str(event.get('url') or '')
                        node_id = str(event.get('nodeId') or '')
                        event_instance = str(event.get('instanceId') or '')
                        if (not url or not node_id
                                or not self.instance_id
                                or event_instance != self.instance_id):
                            continue
                        self._publish_origin(url, node_id)
                        delay = 3
                        self.status('connected', 'App 内嵌 Tailscale 入口已启动，请检测固定入口并用手机验证。',
                                    url=url, node_id=node_id,
                                    instance_id=event_instance)
                    elif state in ('failed', 'error'):
                        code = str(event.get('code') or 'tailscale_failed')
                        self.status('failed', EMBEDDED_ERRORS.get(code, EMBEDDED_ERRORS['tailscale_failed']))
                process.wait()
            except (OSError, ValueError) as exc:
                if not self.stopped.is_set():
                    self.status('retrying', str(exc) if isinstance(exc, ValueError)
                                else '内嵌 Tailscale 已断开，正在重试。')
            finally:
                self._publish_origin()
                if process:
                    self._terminate(process)
                    if process.stdout:
                        process.stdout.close()
                with self.lock:
                    self.process = None
            if self.stopped.is_set():
                break
            if self.last_status and self.last_status['state'] in ('connected', 'connecting', 'authorization'):
                self.status('retrying', '内嵌 Tailscale 未保持连接，请检查网络、Tailnet 策略和 HTTPS/Funnel 权限。')
            if self.stopped.wait(delay):
                break
            delay = min(60, delay * 2)

    @staticmethod
    def _terminate(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

    def close(self):
        self.stopped.set()
        with self.lock:
            if self.process:
                self._terminate(self.process)
        if self.thread:
            self.thread.join(timeout=20)
        self._publish_origin()
        self.status('stopped', 'Tailscale 固定入口已停止')
