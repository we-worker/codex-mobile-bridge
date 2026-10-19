"""Private Tauri stdio host; never a network or arbitrary process API."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urljoin

from bridge.app.desktop import Desktop
from bridge.features.notifications.channels import read_json, write_json

WORKERS = frozenset(('snapshot', 'save', 'start', 'stop', 'logs', 'test-notification',
    'check-entry', 'tailscale-setup', 'devices', 'account', 'accounts', 'harness',
    'desktop-sessions', 'notification-watches', 'transfer-settings', 'pairing',
    'server-setup', 'read-credentials', 'connection-credentials', 'deployment', 'export-deployment'))
LINKS = {
    'releases': 'https://github.com/we-worker/codex-mobile-bridge/actions/workflows/tauri.yml',
    'project-home': 'https://github.com/we-worker/codex-mobile-bridge',
    'project-issues': 'https://github.com/we-worker/codex-mobile-bridge/issues',
    'project-pulls': 'https://github.com/we-worker/codex-mobile-bridge/pulls',
    'tailscale-help': 'https://tailscale.com/docs/how-to/quickstart',
    'setup-tailscale': 'https://tailscale.com/docs/how-to/quickstart',
    'cloudflare-dashboard': 'https://one.dash.cloudflare.com/',
    'cloudflare-domain-help': 'https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/',
    'server-https-help': 'https://caddyserver.com/docs/running',
    'server-ssh-help': 'https://man.openbsd.org/sshd_config#AllowTcpForwarding',
    'cloudflare-help': 'https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/',
    'ntfy-help': 'https://docs.ntfy.sh/subscribe/phone/',
    'bark-help': 'https://bark.day.app/#/tutorial',
    'pushplus-home': 'https://www.pushplus.plus/uc-profile.html',
    'pushplus-verify': 'https://www.pushplus.plus/center/real-auth?source=push',
    'pushplus-limits': 'https://www.pushplus.plus/doc/guide/use.html',
}


def checked_url(value, hosts=None):
    if not isinstance(value, str) or any(c in value for c in '\r\n\0'):
        raise ValueError('地址不可用')
    url = urlsplit(value)
    if url.scheme not in (('https',) if hosts else ('http', 'https')) or not url.hostname or url.username or url.password:
        raise ValueError('地址不可用')
    if hosts and (url.hostname not in hosts or url.port not in (None, 443)):
        raise ValueError('地址不可用')
    return value


class Host:
    def __init__(self, data_dir, desktop_dir, version):
        self.desktop_dir, self.desktop, self.version = Path(desktop_dir).resolve(), Desktop(data_dir), version
        self.secrets = {}
        try:
            self.language = read_json(self.desktop_dir/'language.json', {}).get('language', 'zh-CN')
        except (OSError, ValueError):
            self.language = 'zh-CN'
        if self.language not in ('en', 'zh-CN'):
            self.language = 'zh-CN'
        self.publish_language()

    def publish_language(self):
        write_json(self.desktop.data_dir/'ui-language.json', {'language': 'en' if self.language == 'en' else 'zh'})

    def close(self):
        self.secrets.clear()
        self.desktop.close_local()

    def update(self):
        # Electron archives must never be installed over a Tauri application.
        return {'state': 'unsupported', 'current': self.version, 'message': '此版本请从项目下载页面手动更新。'}

    def snapshot(self):
        return {**self.desktop.snapshot(), 'update': self.update(), 'updateManaged': False,
                'desktopHost': 'tauri', 'desktopLanguage': self.language, 'cloudflaredInstall': {}}

    def dispatch(self, action, payload=None):
        value = {} if payload is None else payload
        if action == 'language':
            return self.language
        if action == 'set-language':
            if value not in ('en', 'zh-CN'):
                raise ValueError('Unsupported language')
            self.language = value
            write_json(self.desktop_dir/'language.json', {'language': value})
            self.publish_language()
            return value
        if action == 'check-update':
            return self.update()
        if action == 'set-data-dir':
            if not isinstance(value, str) or not Path(value).is_absolute():
                raise ValueError('请选择有效的数据目录')
            self.desktop.close_local(check_busy=True)
            self.desktop = Desktop(value)
            self.secrets.clear()
            self.publish_language()
            write_json(self.desktop_dir/'bridge-location.json', {'dataDir': str(self.desktop.data_dir)})
            return str(self.desktop.data_dir)
        if action == 'open':
            return self.open_target(value)
        if action == 'copy':
            if value not in self.desktop.snapshot()['urls']:
                raise ValueError('地址不可用')
            return checked_url(value)
        if action == 'tailscale-authorize':
            snapshot = self.desktop.snapshot()
            if not any(c['id'] == value.get('id') and c['accessMode'] == 'tailscale' for c in snapshot['preferences']['connections']):
                raise ValueError('请选择 Tailscale 连接。')
            address = snapshot.get('externalStatus', {}).get(value['id'], {}).get('authUrl')
            return checked_url(address or self.desktop.tailscale_setup(value).get('authUrl'), {'login.tailscale.com'})
        if action == 'check-cloudflared':
            executable = value.strip() if isinstance(value, str) and value.strip() else self.desktop.preferences()['cloudflared']
            if not executable or not Path(executable).is_absolute():
                raise ValueError('请先选择 cloudflared 程序。')
            return {'path': executable, 'version': probe_cloudflared(executable)}
        if action == 'install-cloudflared':
            if self.desktop.status()['running']:
                raise ValueError('请先停止网关再安装 cloudflared。')
            from bridge.resources import project_root
            name = 'cloudflared.exe' if os.name == 'nt' else 'cloudflared'
            source = Path(getattr(sys, '_MEIPASS', project_root()/'dist'))/'cloudflared'/name
            if not source.is_file():
                raise ValueError('未找到随附程序，请在设置中选择已下载的 cloudflared。')
            directory = self.desktop.data_dir/'bin'
            directory.mkdir(parents=True, exist_ok=True)
            target, staging = directory/name, directory/(name+'.tmp')
            shutil.copyfile(source, staging)
            try:
                staging.chmod(0o700)
                version = probe_cloudflared(str(staging))
                staging.replace(target)
            finally:
                staging.unlink(missing_ok=True)
            return {'path': str(target), 'version': version}
        if action not in WORKERS:
            raise ValueError('未知操作')
        if not isinstance(value, dict):
            raise ValueError('操作参数格式错误')
        if action == 'snapshot':
            return self.snapshot()
        if action == 'start':
            value = {**value, 'connectionSecrets': self.secrets}
        if action == 'read-credentials' and value.get('id') in self.secrets:
            return dict(self.secrets[value['id']])
        if action == 'connection-credentials':
            return self.connection_credentials(value)
        if action == 'server-setup':
            if value.get('action') not in ('host', 'trust', 'inspect', 'diagnostics'):
                raise ValueError('不支持的服务器操作')
            value = {**value, 'secrets': self.secrets.get(value.get('id'))}
        if action == 'accounts' and value.get('action') == 'openLogin':
            result = self.desktop.accounts({'action': 'list'})
            enrollment = result.get('enrollment', {})
            if enrollment.get('phase') != 'waiting':
                raise ValueError('登录已过期，请重新登录')
            return {'url': checked_url(enrollment.get('authUrl'), {'auth.openai.com', 'chatgpt.com', 'auth0.openai.com'}), 'result': result}
        method = getattr(self.desktop, action.replace('-', '_'))
        result = method() if action in ('stop', 'logs') else method(value)
        return self.snapshot() if action == 'save' else result

    def connection_credentials(self, value):
        if not any(c['id'] == value.get('id') for c in self.desktop.preferences()['connections']):
            raise ValueError('请先保存连接配置。')
        secret = value.get('secrets')
        if not isinstance(secret, dict) or set(secret) - {'password', 'passphrase', 'tunnelToken', 'authKey', 'clear'}:
            raise ValueError('连接凭据格式不正确')
        for key, text in secret.items():
            if (key == 'clear' and not isinstance(text, bool)) or (key != 'clear' and (not isinstance(text, str) or len(text) > 16384 or '\0' in text)):
                raise ValueError('连接凭据格式不正确')
        if secret.get('clear') or value.get('remember'):
            self.desktop.connection_credentials({'id': value['id'], 'secrets': secret})
            self.secrets.pop(value['id'], None)
        else:
            self.secrets[value['id']] = {**self.secrets.get(value['id'], {}), **secret}
        return {'message': '连接凭据已保存到系统凭据存储。' if value.get('remember') else '连接凭据仅保留在本次 App 运行内存中。'}

    def open_target(self, value):
        if value in LINKS:
            return {'kind': 'url', 'value': LINKS[value]}
        if value in ('credentials', 'data'):
            return {'kind': 'path', 'value': str(self.desktop.data_dir/'首次登录.txt' if value == 'credentials' else self.desktop.data_dir)}
        if value in ('setup-lan', 'setup-quick', 'setup-cloudflare', 'setup-server', 'setup-nas'):
            return {'kind': 'url', 'value': 'https://try2love.github.io/codex-mobile-bridge/setup.html?lang='+('en' if self.language == 'en' else 'zh')+'#'+value[6:]}
        snapshot = self.desktop.snapshot()
        if value == 'harness':
            state = self.desktop.harness({'action': 'status'})
            if not state.get('running') or not snapshot['urls']:
                raise ValueError('请先启动网关和 Harness')
            value = urljoin(snapshot['urls'][0], '/harness/')
        elif value not in snapshot['urls']:
            raise ValueError('地址不可用')
        return {'kind': 'url', 'value': checked_url(value)}


def probe_cloudflared(executable):
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    try:
        result = subprocess.run([executable, '--version'], capture_output=True, timeout=10, check=True, **options)
        version = result.stdout.decode('utf-8').strip()
        if not version.startswith('cloudflared version ') or len(version) > 4096:
            raise ValueError()
        return version
    except (OSError, ValueError, subprocess.SubprocessError):
        raise ValueError('cloudflared 无法运行，请检查程序架构和执行权限。') from None


def stream(data_dir, desktop_dir):
    from bridge.resources import project_root
    version_path = Path(getattr(sys, '_MEIPASS', project_root()/'dist'))/'update-version.json'
    version = read_json(version_path, {}).get('version') or json.loads((project_root()/'package.json').read_text(encoding='utf-8'))['version']
    host = Host(data_dir, desktop_dir, version)
    try:
        while True:
            line = sys.stdin.readline(1024*1024+1)
            if not line:
                break
            if len(line) > 1024*1024 or not line.endswith('\n'):
                raise ValueError('本机请求超出大小限制')
            try:
                request = json.loads(line)
                result = host.dispatch(request['action'], request.get('payload'))
                response = {'ok': True, 'result': result}
            except Exception as exc:
                response = {'ok': False, 'error': str(exc), 'validation': getattr(exc, 'validation', None)}
            print(json.dumps(response, ensure_ascii=False), flush=True)
    finally:
        host.close()
