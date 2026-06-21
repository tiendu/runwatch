#!/usr/bin/env bash

set -Eeuo pipefail

system_python="${SYSTEM_PYTHON:-python3}"
venv="${VENV:-.venv}"
python="${venv}/bin/python"
stamp="${venv}/.runwatch-dev-installed"

create_venv() {
    echo "Creating virtual environment at ${venv}"
    rm -rf -- "${venv}"
    "${system_python}" -m venv "${venv}"
}

ensure_pip() {
    if "${python}" -m pip --version >/dev/null 2>&1; then
        return
    fi

    echo "pip is missing from ${venv}; bootstrapping with ensurepip"

    if ! "${python}" -m ensurepip --upgrade; then
        echo \
            "Unable to bootstrap pip. Install the system venv package and retry." \
            >&2
        exit 1
    fi
}

if [[ ! -x "${python}" ]]; then
    create_venv
fi

ensure_pip

if [[ ! -f "${stamp}" || pyproject.toml -nt "${stamp}" ]]; then
    "${python}" -m pip install -e ".[dev]"
    touch "${stamp}"
fi
