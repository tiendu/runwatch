SHELL := /bin/bash

SYSTEM_PYTHON ?= python3

VENV ?= .venv
PYTHON := $(VENV)/bin/python
RUNWATCH := $(VENV)/bin/runwatch

CONFIG ?= runwatch.toml
TARGET ?=
METRICS_URL ?= http://127.0.0.1:9109/metrics

HOST_PREFIX ?= /opt/runwatch
SYSTEM_CONFIG_DIR ?= /etc/runwatch
SYSTEMD_SERVICE ?= runwatch.service
SYSTEMD_UNIT_PATH ?= /etc/systemd/system/$(SYSTEMD_SERVICE)

.PHONY: \
	help install reinstall \
	init setup inspect check-once watch run serve validate doctor \
	test lint format format-check typecheck shellcheck check ci build clean \
	systemd-preview systemd-install systemd-restart systemd-status \
	systemd-logs metrics systemd-uninstall systemd-purge

help:
	@printf '%s\n' \
		'make install                 Install development environment' \
		'make inspect TARGET=nginx    Inspect once and exit' \
		'make watch TARGET=nginx      Watch in the terminal' \
		'make setup                   Configure persistent monitoring' \
		'make run                     Run persistent monitoring' \
		'make check                   Run all development checks' \
		'make build                   Build wheel and source archive' \
		'make systemd-install         Install and start host service' \
		'make systemd-status          Show service status' \
		'make systemd-logs            Follow journald logs' \
		'make systemd-purge           Remove service, config, and host install'

install:
	SYSTEM_PYTHON="$(SYSTEM_PYTHON)" \
	VENV="$(VENV)" \
	./scripts/bootstrap-dev.sh

reinstall: clean install

init: install
	@test -e "$(CONFIG)" || \
		"$(RUNWATCH)" init --output "$(CONFIG)"

setup: install
	"$(RUNWATCH)" setup --output "$(CONFIG)"

inspect: install
	@test -n "$(TARGET)" || { \
		echo 'Usage: make inspect TARGET=nginx' >&2; \
		exit 2; \
	}
	"$(RUNWATCH)" check "$(TARGET)"

check-once: inspect

watch: install
	@test -n "$(TARGET)" || { \
		echo 'Usage: make watch TARGET=nginx' >&2; \
		exit 2; \
	}
	"$(RUNWATCH)" watch "$(TARGET)"

run: install
	"$(RUNWATCH)" serve --config "$(CONFIG)"

serve: run

validate: install
	"$(RUNWATCH)" validate --config "$(CONFIG)"

doctor: install
	@if test -f "$(CONFIG)"; then \
		"$(RUNWATCH)" doctor --config "$(CONFIG)"; \
	else \
		"$(RUNWATCH)" doctor; \
	fi

test: install
	"$(PYTHON)" -m pytest

lint: install
	"$(PYTHON)" -m ruff check .

format: install
	"$(PYTHON)" -m ruff format .

format-check: install
	"$(PYTHON)" -m ruff format --check .

typecheck: install
	"$(PYTHON)" -m mypy src

shellcheck:
	bash -n scripts/*.sh
	command -v shellcheck >/dev/null 2>&1 && shellcheck scripts/*.sh || true

check: test lint format-check typecheck shellcheck

ci: check build

build: install
	rm -rf dist
	"$(PYTHON)" -m build

clean:
	rm -rf "$(VENV)" .venv-test
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	rm -rf build dist *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

systemd-preview: install
	@test -f "$(CONFIG)" || { \
		echo 'Run make setup or make init first.' >&2; \
		exit 2; \
	}
	"$(RUNWATCH)" install-systemd \
		--dry-run \
		--config-source "$(CONFIG)" \
		--config-path "$(SYSTEM_CONFIG_DIR)/runwatch.toml" \
		--unit-path "$(SYSTEMD_UNIT_PATH)" \
		--executable "$(HOST_PREFIX)/venv/bin/runwatch"

systemd-install:
	SYSTEM_PYTHON="$(SYSTEM_PYTHON)" \
	HOST_PREFIX="$(HOST_PREFIX)" \
	CONFIG="$(CONFIG)" \
	SYSTEM_CONFIG_DIR="$(SYSTEM_CONFIG_DIR)" \
	SYSTEMD_UNIT_PATH="$(SYSTEMD_UNIT_PATH)" \
	./scripts/install-host.sh

systemd-restart:
	sudo systemctl restart "$(SYSTEMD_SERVICE)"

systemd-status:
	systemctl status "$(SYSTEMD_SERVICE)" --no-pager

systemd-logs:
	journalctl -u "$(SYSTEMD_SERVICE)" -f

metrics:
	curl --fail --silent --show-error "$(METRICS_URL)"

systemd-uninstall:
	-sudo systemctl disable --now "$(SYSTEMD_SERVICE)"
	sudo rm -f "$(SYSTEMD_UNIT_PATH)"
	sudo systemctl daemon-reload
	-sudo systemctl reset-failed "$(SYSTEMD_SERVICE)"

systemd-purge:
	HOST_PREFIX="$(HOST_PREFIX)" \
	SYSTEM_CONFIG_DIR="$(SYSTEM_CONFIG_DIR)" \
	SYSTEMD_SERVICE="$(SYSTEMD_SERVICE)" \
	SYSTEMD_UNIT_PATH="$(SYSTEMD_UNIT_PATH)" \
	./scripts/purge-host.sh
