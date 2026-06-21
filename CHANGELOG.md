# Changelog

## 0.2.5

- Validate TOML types, unknown keys, thresholds, URLs, ports, and duplicate names.
- Escape generated TOML strings safely.
- Normalize expected CLI failures without tracebacks.
- Use collision-safe atomic file writes with explicit permissions.
- Make systemd installation transactional and restore changed files when activation fails.
- Isolate result-sink failures so monitoring cycles continue.
- Treat normal unprivileged PID 1 descriptor restrictions as informational in `doctor`.
- Add stricter Ruff and pytest settings plus CI for Python 3.11, 3.12, and 3.13.
- Expand reliability coverage across CLI, config, filesystem, architecture, and installation failure modes.

## 0.2.4

- Separate CLI parsing, command workflows, execution, persistent service lifecycle, and signals.

## 0.2.3

- Add `runwatch doctor` and improve systemd scope, peer, and Unix socket reporting.
