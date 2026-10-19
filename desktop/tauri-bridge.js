/* Native adapter, injected before the shared desktop page is evaluated. */
(() => {
  'use strict';
  const invoke = (action, payload = null) => window.__TAURI__.core.invoke('bridge', {action, payload})
    .catch(error => { throw error instanceof Error ? error : new Error(typeof error === 'string' ? error : JSON.stringify(error)); });
  const methods = {
    checkUpdate:'check-update', skipUpdate:'skip-update', installUpdate:'install-update', language:'language', setLanguage:'set-language',
    notificationWatches:'notification-watches', transferSettings:'transfer-settings', devices:'devices', pairing:'pairing',
    installCloudflared:'install-cloudflared', checkCloudflared:'check-cloudflared', copyServerDiagnostics:'copy-server-diagnostics',
    serverSetup:'server-setup', tailscaleSetup:'tailscale-setup', tailscaleAuthorize:'tailscale-authorize',
    connectionCredentials:'connection-credentials', readCredentials:'read-credentials', snapshot:'snapshot', accounts:'accounts',
    desktopSessions:'desktop-sessions', cliAccess:'cli-access', harness:'harness', account:'account', save:'save', start:'start', stop:'stop', logs:'logs',
    testNotification:'test-notification', exportDeployment:'export-deployment', copyDeployment:'copy-deployment',
    checkEntry:'check-entry', choose:'choose', open:'open', copy:'copy'
  };
  Object.defineProperty(window, 'bridgeDesktop', {
    value: Object.freeze(Object.fromEntries(Object.entries(methods).map(([name, action]) => [name, payload => invoke(action, payload)]))),
    writable: false, configurable: false
  });
})();
