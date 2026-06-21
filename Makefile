SHELL := /bin/bash

SYSTEM_PYTHON ?= python3

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(PYTHON) -m pip
RUNWATCH := $(VENV)/bin/runwatch

CONFIG ?= runwatch.toml
TARGET ?=
METRICS_URL ?= http://127.0.0.1:9109/metrics

HOST_PREFIX ?= /opt/runwatch
HOST_VENV := $(HOST_PREFIX)/venv
HOST_PYTHON := $(HOST_VENV)/bin/python
HOST_PIP := $(HOST_PYTHON) -m pip
HOST_RUNWATCH := $(HOST_VENV)/bin/runwatch
SYSTEMD_SERVICE ?= runwatch.service

.PHONY: help venv install reinstall init setup inspect check-once watch run serve validate doctor \
	test lint format format-check typecheck check build clean \
	systemd-preview systemd-install systemd-restart systemd-status \
	systemd-logs metrics systemd-uninstall systemd-purge

help:
	@printf '%s\n' \
		'make install                 Install locally with development dependencies' \
		'make inspect TARGET=nginx    Inspect one service/process and exit' \
		'make watch TARGET=nginx      Watch one service/process in the terminal' \
		'make setup                   Run the persistent-monitoring setup wizard' \
		'make run                     Run persistent monitoring in the foreground' \
		'make validate                Validate $(CONFIG)' \
		'make doctor                  Check host visibility and configuration' \
		'make check                   Run tests, linting, format check, and MyPy' \
		'make build                   Build Hatchling wheel and source archive' \
		'make clean                   Remove local development artifacts' \
		'make systemd-install         Install under /opt/runwatch and start at boot' \
		'make systemd-status          Show the runwatch service status' \
		'make systemd-logs            Follow structured logs from journald' \
		'make metrics                 Read the local OpenMetrics endpoint'

venv:
	@set -euo pipefail; \
	if [ ! -x "$(PYTHON)" ]; then \
		echo "Creating virtual environment at $(VENV)"; \
		rm -rf "$(VENV)"; \
		"$(SYSTEM_PYTHON)" -m venv "$(VENV)"; \
	fi; \
	if ! "$(PYTHON)" -m pip --version >/dev/null 2>&1; then \
		echo "pip is missing from $(VENV); bootstrapping with ensurepip"; \
		"$(PYTHON)" -m ensurepip --upgrade || { \
			echo "Unable to bootstrap pip. Install the system venv package and retry." >&2; \
			exit 1; \
		}; \
	fi; \
	"$(PYTHON)" -m pip install --upgrade pip

install: venv
	$(PIP) install -e ".[dev]"

reinstall: clean install

init: install
	@test -e $(CONFIG) || $(RUNWATCH) init --output $(CONFIG)

setup: install
	$(RUNWATCH) setup --output $(CONFIG)

inspect: install
	@test -n "$(TARGET)" || { echo 'Usage: make inspect TARGET=nginx' >&2; exit 2; }
	$(RUNWATCH) check "$(TARGET)"

check-once: inspect

watch: install
	@test -n "$(TARGET)" || { echo 'Usage: make watch TARGET=nginx' >&2; exit 2; }
	$(RUNWATCH) watch "$(TARGET)"

run: install
	$(RUNWATCH) serve --config $(CONFIG)

serve: run

validate: install
	$(RUNWATCH) validate --config $(CONFIG)

doctor: install
	@if [ -f "$(CONFIG)" ]; then \
		$(RUNWATCH) doctor --config "$(CONFIG)"; \
	else \
		$(RUNWATCH) doctor; \
	fi

test: install
	$(PYTHON) -m pytest

lint: install
	$(PYTHON) -m ruff check .

format: install
	$(PYTHON) -m ruff format .

format-check: install
	$(PYTHON) -m ruff format --check .

typecheck: install
	$(PYTHON) -m mypy src

check: test lint format-check typecheck

build: install
	rm -rf dist
	$(PYTHON) -m build

clean:
	rm -rf $(VENV) .venv-test
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	rm -rf build dist *.egg-info src/*.egg-info
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +

systemd-preview: install
	@test -f "$(CONFIG)" || { echo 'Run make setup or make init first.' >&2; exit 2; }
	$(RUNWATCH) install-systemd \
		--dry-run \
		--config-source $(CONFIG) \
		--executable $(HOST_RUNWATCH)

systemd-install:
	@test -f "$(CONFIG)" || { echo 'Run make setup or create $(CONFIG) first.' >&2; exit 2; }
	@set -euo pipefail; \
	if ! sudo test -x "$(HOST_PYTHON)"; then \
		sudo "$(SYSTEM_PYTHON)" -m venv "$(HOST_VENV)"; \
	fi; \
	if ! sudo "$(HOST_PYTHON)" -m pip --version >/dev/null 2>&1; then \
		sudo "$(HOST_PYTHON)" -m ensurepip --upgrade; \
	fi
	sudo $(HOST_PYTHON) -m pip install --upgrade pip
	sudo $(HOST_PIP) install --upgrade "$(CURDIR)"
	sudo $(HOST_RUNWATCH) install-systemd \
		--config-source $(CONFIG) \
		--executable $(HOST_RUNWATCH) \
		--force \
		--enable

systemd-restart:
	sudo systemctl restart $(SYSTEMD_SERVICE)

systemd-status:
	systemctl status $(SYSTEMD_SERVICE) --no-pager

systemd-logs:
	journalctl -u $(SYSTEMD_SERVICE) -f

metrics:
	curl --fail --silent --show-error $(METRICS_URL)

systemd-uninstall:
	-sudo systemctl disable --now $(SYSTEMD_SERVICE)
	sudo rm -f /etc/systemd/system/$(SYSTEMD_SERVICE)
	sudo systemctl daemon-reload
	-sudo systemctl reset-failed $(SYSTEMD_SERVICE)

systemd-purge: systemd-uninstall
	sudo rm -rf $(HOST_PREFIX)
	sudo rm -rf /etc/runwatch /var/lib/runwatch /var/log/runwatch
