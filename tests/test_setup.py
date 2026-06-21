from collections.abc import Sequence

from runwatch.prompts import Prompter


class FakePrompter(Prompter):
    def text(self, message: str, default: str | None = None) -> str:
        return default or message

    def confirm(self, message: str, default: bool = True) -> bool:
        return default

    def select(self, message: str, choices: Sequence[str]) -> int:
        return 0


def test_prompter_protocol_can_be_faked() -> None:
    prompt = FakePrompter()

    assert prompt.text("x", "y") == "y"
    assert prompt.confirm("x") is True
    assert prompt.select("x", ["a"]) == 0


def test_user_scope_is_persisted_as_process_selector(monkeypatch: object) -> None:
    from runwatch.setup_wizard import _persistent_spec
    from runwatch.targets import ResolvedTarget, TargetSpec

    def resolve(_self: object, spec: TargetSpec) -> ResolvedTarget:
        return ResolvedTarget(
            name=spec.name,
            kind="systemd",
            selector=spec.value,
            manager="systemd-user",
            unit="app-org.mozilla.firefox-1.scope",
            cgroup="/user.slice/user-1000.slice/user@1000.service/app.slice/"
            "app-org.mozilla.firefox-1.scope",
            main_pid=123,
            pids=(123,),
        )

    monkeypatch.setattr("runwatch.setup_wizard.LinuxTargetResolver.resolve", resolve)  # type: ignore[attr-defined]
    spec = _persistent_spec(TargetSpec(name="firefox", kind="auto", value="firefox"))

    assert spec.kind == "process"
    assert spec.value == "firefox"
