from runwatch.main import execute_check


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
