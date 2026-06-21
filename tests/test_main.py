from __future__ import annotations

import argparse

from runwatch import main as main_module
from runwatch.execution import execute_check


class BrokenCheck:
    name = "broken"
    check_type = "test"

    def run(self) -> object:
        raise RuntimeError("boom")


def test_execute_check_converts_unhandled_exception_to_failure() -> None:
    result = execute_check(BrokenCheck())  # type: ignore[arg-type]

    assert result.status == "fail"
    assert result.name == "broken"
    assert result.message == "RuntimeError: boom"


def test_run_dispatches_parsed_command() -> None:
    called: list[str] = []

    def handler(args: argparse.Namespace) -> int:
        called.append(args.command)
        return 7

    # The registry is intentionally the only bridge between parsing and workflows.
    main_module.COMMAND_HANDLERS["test-command"] = handler
    try:
        assert main_module.run(argparse.Namespace(command="test-command")) == 7
    finally:
        del main_module.COMMAND_HANDLERS["test-command"]

    assert called == ["test-command"]


def test_main_returns_stable_code_for_expected_error(
    capsys: object,
    monkeypatch: object,
) -> None:
    from runwatch.errors import ConfigError

    def fail(_args: argparse.Namespace) -> int:
        raise ConfigError("bad config")

    # pytest fixtures are intentionally left untyped to avoid importing pytest types here.
    monkeypatch.setitem(main_module.COMMAND_HANDLERS, "expected-error", fail)  # type: ignore[attr-defined]
    monkeypatch.setattr(  # type: ignore[attr-defined]
        main_module,
        "parse_args",
        lambda _argv: argparse.Namespace(command="expected-error"),
    )
    code = main_module.main(["expected-error"])
    captured = capsys.readouterr()  # type: ignore[attr-defined]

    assert code == 2
    assert captured.err == "runwatch: bad config\n"
