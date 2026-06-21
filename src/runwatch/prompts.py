from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class Prompter(Protocol):
    def text(self, message: str, default: str | None = None) -> str: ...

    def confirm(self, message: str, default: bool = True) -> bool: ...

    def select(self, message: str, choices: Sequence[str]) -> int: ...


class TerminalPrompter:
    def text(self, message: str, default: str | None = None) -> str:
        suffix = f" [{default}]" if default is not None else ""
        while True:
            value = input(f"{message}{suffix}: ").strip()
            if value:
                return value
            if default is not None:
                return default
            print("A value is required.")

    def confirm(self, message: str, default: bool = True) -> bool:
        suffix = " [Y/n]" if default else " [y/N]"
        while True:
            value = input(f"{message}{suffix}: ").strip().lower()
            if not value:
                return default
            if value in {"y", "yes"}:
                return True
            if value in {"n", "no"}:
                return False
            print("Enter yes or no.")

    def select(self, message: str, choices: Sequence[str]) -> int:
        print(message)
        for index, choice in enumerate(choices, start=1):
            print(f"  {index}. {choice}")
        while True:
            value = input("Selection: ").strip()
            try:
                index = int(value)
            except ValueError:
                print("Enter a number.")
                continue
            if 1 <= index <= len(choices):
                return index - 1
            print(f"Enter a number from 1 to {len(choices)}.")
