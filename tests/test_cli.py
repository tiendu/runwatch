from runwatch.cli import build_parser, parse_args


def test_check_command_accepts_plain_target() -> None:
    args = build_parser().parse_args(["check", "nginx"])

    assert args.command == "check"
    assert args.target == "nginx"
    assert args.sample_seconds == 1.0
    assert not hasattr(args, "func")


def test_watch_command_accepts_explicit_pid() -> None:
    args = parse_args(["watch", "--pid", "123", "--interval", "5"])

    assert args.pid == 123
    assert args.interval == 5.0


def test_doctor_command_accepts_config_and_json() -> None:
    args = parse_args(["doctor", "--config", "runwatch.toml", "--metrics-port", "9200", "--json"])

    assert args.command == "doctor"
    assert args.config == "runwatch.toml"
    assert args.metrics_port == 9200
    assert args.json is True
