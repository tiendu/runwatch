# runwatch

A small Linux service and process monitor written in Python.

`runwatch` has two main workflows:

```bash
# Inspect once, print the answer, and exit.
runwatch check nginx

# Continuously watch in the current terminal.
runwatch watch nginx
```

Persistent monitoring is optional:

```bash
runwatch setup
sudo make systemd-install
```

The systemd service emits structured JSON logs and exposes an OpenMetrics-compatible endpoint.

## What it discovers

For a systemd service or process, `runwatch` reports:

```text
systemd unit and service state
main PID and complete process tree
cgroup
command, user, and uptime
CPU usage
memory usage
disk read/write totals and rates
process and thread counts
total file descriptors and open regular files
listening TCP/UDP ports and connection states
Unix-domain sockets and known IPC paths
```

A PID that belongs to a specific systemd service or application scope is promoted to that complete cgroup. Generic containers such as `user@1000.service`, `session-*.scope`, and `*.slice` are deliberately ignored; Runwatch falls back to the selected process tree instead of measuring an entire login session.

Per-target network byte accounting is deliberately not guessed. Linux does not expose reliable process network byte counters through normal `/proc` or `psutil` APIs. Ports and connections work now; upload/download rates would require an optional eBPF collector later.

For desktop and session services, Runwatch separates Internet networking from local IPC:

```text
File descriptors  24
Regular files     0

TCP/UDP listeners
  none visible

IPC
  Unix sockets     5 (1 named, 4 unnamed)
  Named paths
    /run/user/1000/bus
```

`File descriptors` includes pipes, sockets, event descriptors, and regular files. `Regular files` is the narrower count returned by the process file inventory.

## Internal structure

The application boundary is intentionally small:

```text
cli.py              argument definitions and parsing only
main.py             application entrypoint and command dispatch
commands/           one workflow adapter per CLI command
execution.py        safe check execution, result dispatch, and exit codes
check_factory.py    construct configured checks
target_runtime.py   one-shot and foreground target monitoring
service.py          persistent monitoring lifecycle and scheduling
signals.py          SIGINT/SIGTERM handling
```

Both the installed `runwatch` command and `python -m runwatch` enter through
`runwatch.main:main`. Domain collectors do not depend on the CLI layer.

## Installation

```bash
make install
```

The project uses Hatchling and a `src/` layout.

## One-shot inspection

```bash
runwatch check nginx
runwatch check nginx.service
runwatch check --pid 1842
runwatch check --pid-file /run/worker.pid
runwatch check --process /opt/app/bin/worker
```

CPU and disk throughput need two samples. The default sampling window is one second:

```bash
runwatch check nginx --sample-seconds 2
```

Machine-readable output:

```bash
runwatch check nginx --json
```

Health and collection visibility are reported separately. A healthy target remains healthy when Linux permissions hide some file descriptors or sockets.

```text
Health            OK — process tree is active with 18 processes
Visibility        partial — regular files 16/18; TCP/UDP sockets 16/18
```

Use `--verbose` to show individual collection errors:

```bash
runwatch check firefox --verbose
```

Exit codes:

```text
0  target is healthy
1  target has a health warning
2  target is missing, stopped, ambiguous, or failed
```

## Terminal watch

```bash
runwatch watch nginx
runwatch watch nginx --interval 5
runwatch watch nginx --json
```

`watch` runs in the foreground and stops with Ctrl+C. It does not require a config file or a systemd installation.


## Host diagnostics

Run the built-in doctor before persistent deployment or when collection looks incomplete:

```bash
runwatch doctor
runwatch doctor --config runwatch.toml
runwatch doctor --json
```

It checks:

```text
Linux and Python compatibility
system and user systemd managers
/proc and cgroup visibility
cross-process permissions
TCP/UDP and Unix socket inspection
optional eBPF prerequisites
TOML validity and configured target resolution
metrics port availability or an existing Runwatch endpoint
```

Doctor exit codes are `0` when required checks pass, `1` when warnings remain, and `2` when a required capability or explicit configuration is invalid. Informational limitations, such as an unavailable optional eBPF collector, do not fail the command.

## Persistent monitoring

Run the guided setup:

```bash
runwatch setup
```

The wizard discovers each target, confirms whether it is managed by systemd, and writes `runwatch.toml`.

A persistent config looks like this:

```toml
[serve]
interval_seconds = 30
max_workers = 4

[metrics]
enabled = true
address = "127.0.0.1"
port = 9109
include_runtime_metrics = false

[system]
enabled = true
cpu_warn_percent = 80
memory_warn_percent = 85
disk_warn_percent = 90
disk_paths = ["/"]

[[targets]]
name = "nginx"
type = "systemd"
value = "nginx.service"
include_children = true

[[targets]]
name = "worker"
type = "pid_file"
value = "/run/worker.pid"
include_children = true
```

Run it in the foreground:

```bash
runwatch serve --config runwatch.toml
```

Configured targets and HTTP health checks run concurrently through a bounded thread pool. Monitoring cycles never overlap.

## Install as a host service

```bash
make setup
make systemd-preview
make systemd-install
```

The installed command is:

```text
/opt/runwatch/venv/bin/runwatch serve --config /etc/runwatch/runwatch.toml
```

The unit runs as root because inspecting cgroups, sockets, open files, and processes owned by other users often requires elevated visibility. The generated unit applies read-only filesystem and systemd sandboxing restrictions. Runwatch does not execute remediation commands or modify monitored services.

Useful commands:

```bash
make systemd-status
make systemd-logs
make metrics
make systemd-restart
make systemd-uninstall
```

## Metrics

The endpoint is Prometheus/OpenMetrics compatible. Prometheus is not required; compatible collectors include VictoriaMetrics, OpenTelemetry Collector, Grafana Alloy, Telegraf, Datadog Agent, and similar tools.

Examples:

```text
runwatch_target_up{name="nginx"} 1
runwatch_target_visibility_complete{name="nginx"} 1
runwatch_target_collection_errors{name="nginx"} 0
runwatch_target_processes{name="nginx"} 5
runwatch_target_threads{name="nginx"} 5
runwatch_target_cpu_usage_cores{name="nginx"} 0.018
runwatch_target_memory_bytes{name="nginx"} 44777472
runwatch_target_io_read_bytes_total{name="nginx"} 19087360
runwatch_target_io_write_bytes_total{name="nginx"} 4927488
runwatch_target_io_read_bytes_per_second{name="nginx"} 1258291
runwatch_target_file_descriptors{name="nginx"} 73
runwatch_target_open_regular_files{name="nginx"} 12
runwatch_target_internet_listening_sockets{name="nginx"} 4
runwatch_target_unix_sockets{name="nginx"} 2
runwatch_target_unix_sockets_named{name="nginx"} 1
runwatch_target_unix_sockets_unnamed{name="nginx"} 1
runwatch_target_unique_remote_peers{name="nginx"} 8
runwatch_target_connections{name="nginx",state="established"} 24
```

Host, HTTP, and universal check metrics remain available:

```text
runwatch_check_up
runwatch_check_status
runwatch_check_duration_seconds
runwatch_system_cpu_usage_ratio
runwatch_system_memory_usage_ratio
runwatch_system_disk_usage_ratio
runwatch_http_up
runwatch_http_request_duration_seconds
```

The safe default is `127.0.0.1:9109`. Bind to `0.0.0.0` only when a remote collector needs access and a firewall or trusted network restricts the port.

## Development

```bash
make install
make inspect TARGET=nginx
make watch TARGET=nginx
make doctor
make check
make clean
```

`make check` runs pytest, Ruff, formatting validation, and strict MyPy.
