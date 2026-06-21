#!/usr/bin/env bash

set -Eeuo pipefail

host_prefix="${HOST_PREFIX:-/opt/runwatch}"
system_config_dir="${SYSTEM_CONFIG_DIR:-/etc/runwatch}"
service="${SYSTEMD_SERVICE:-runwatch.service}"
unit_path="${SYSTEMD_UNIT_PATH:-/etc/systemd/system/${service}}"

printf '%s\n' \
    "This will remove:" \
    "  ${unit_path}" \
    "  ${system_config_dir}" \
    "  ${host_prefix}"

if [[ "${RUNWATCH_PURGE_CONFIRM:-}" != "yes" ]]; then
    read -r -p "Continue? [y/N] " answer

    case "${answer}" in
        y | Y | yes | YES)
            ;;
        *)
            echo "Cancelled."
            exit 0
            ;;
    esac
fi

sudo systemctl disable --now "${service}" 2>/dev/null || true
sudo rm -f -- "${unit_path}"
sudo systemctl daemon-reload
sudo systemctl reset-failed "${service}" 2>/dev/null || true

sudo rm -rf -- "${host_prefix}"
sudo rm -rf -- "${system_config_dir}"
