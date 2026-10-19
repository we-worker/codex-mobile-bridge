# SSH CLI upstream model catalogs

The native CLI path previously rejected every SSH API catalog and asked for a manual model ID. It now reads the effective configuration from the joined daemon and performs catalog discovery on that same SSH host. Local gateway authentication is never substituted.

The target worker reads only the named provider environment variables from a verified same-user daemon. PID generation, executable and CODEX_HOME are checked by the target platform reader. The worker returns normalized public model metadata and an opaque identity digest; launch credentials and auth-file contents are not returned. Existing config/read snapshots are sent back to their original host through SSH stdin, not command arguments or temporary files.

Host, remote home, cwd, provider, config, account, auth-file digest and selected environment form the cache identity. Upstream model IDs remain authoritative, and native metadata fills missing effort information only for exact IDs. Identity is checked again around a fetch. Same-identity failures preserve the last successful result and timestamp; changed identities cannot reuse that result. The existing manual and 12-hour refresh policy is retained.

The source bundle includes both POSIX platform readers and their dependencies so a frozen Windows or Mac gateway can query a Linux target. Windows-over-SSH is outside the existing POSIX SSH execution contract; local Windows CLI uses its native reader.

Validation: focused model/session/cache/resource tests; isolated standalone-source execution; a real Codex CLI 0.160.0 daemon on the authorized Linux SSH host using only a loopback mock upstream. Cold/warm reads, manual refresh, failed-refresh retention, credential rotation and cleanup passed with zero model messages. This does not claim public-upstream connectivity on a host without the required network access.
