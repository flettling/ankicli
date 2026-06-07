from dataclasses import dataclass
from typing import Any, Callable


class SafetyError(RuntimeError):
    pass


@dataclass(frozen=True)
class MutatingCommandContext:
    profile: str
    is_desktop_base: bool
    write: bool = False
    no_backup: bool = False
    confirm_schema_change: bool = False

    def validate(self) -> None:
        if self.is_desktop_base and not self.write:
            raise SafetyError("desktop Anki mutation requires --write")
        if self.is_desktop_base and self.no_backup:
            raise SafetyError("--no-backup is forbidden for detected desktop Anki")


def run_guarded_mutation(
    context: MutatingCommandContext,
    backup: Callable[..., dict[str, Any]],
    mutate: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    context.validate()
    backup_result = None
    if not context.no_backup:
        backup_result = backup(force=True)
    result = mutate()
    return {"backup": backup_result, "result": result}
