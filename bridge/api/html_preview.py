"""Fixed HTML preview shell policy; workspace content never enters this response."""

SHELL_PATH = '/html-preview-shell'
SHELL_FILE = 'features/workspace/html-preview-shell.html'
SHELL_CSP = (
    "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; "
    "style-src 'unsafe-inline'; img-src data:; font-src data:; media-src data:; "
    "connect-src 'none'; frame-src 'none'; object-src 'none'; worker-src 'none'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
)
