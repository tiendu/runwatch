#!/usr/bin/env bash

set -Eeuo pipefail

system_python="${SYSTEM_PYTHON:-python3}"
host_prefix="${HOST_PREFIX:-/opt/runwatch}"
config="${CONFIG:-runwatch.toml}"
system_config_dir="${SYSTEM_CONFIG_DIR:-/etc/runwatch}"
unit_path="${SYSTEMD_UNIT_PATH:-/etc/systemd/system/runwatch.service}"

host_venv="${host_prefix}/venv"
host_python="${host_venv}/bin/python"
host_runwatch="${host_venv}/bin/runwatch"
system_config_path="${system_config_dir}/runwatch.toml"

if [[ ! -f "${config}" ]]; then
    echo "Config not found: ${config}" >&2
    echo "Run 'make setup' or create the config first." >&2
    exit 2
fi

if ! sudo test -x "${host_python}"; then
    echo "Creating host virtual environment at ${host_venv}"
    sudo "${system_python}" -m venv "${host_venv}"
fi

if ! sudo "${host_python}" -m pip --version >/dev/null 2>&1; then
    sudo "${host_python}" -m ensurepip --upgrade
fi

echo "Installing Runwatch into ${host_venv}"
sudo "${host_python}" -m pip install --upgrade "$(pwd)"

echo "Installing systemd service"
sudo "${host_runwatch}" install-systemd \
    --config-source "${config}" \
    --config-path "${system_config_path}" \
    --unit-path "${unit_path}" \
    --executable "${host_runwatch}" \
    --force \
    --enable
