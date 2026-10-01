"""Exercise clients that drive tasks directly instead of through RPG NPCs."""

DOOM_TASK_SOURCE = "doom"
HKZERO_TASK_SOURCE = "hkzero"
INTERACTIVE_TASK_SOURCES = frozenset({DOOM_TASK_SOURCE, HKZERO_TASK_SOURCE})


def is_interactive_task_source(source: str | None) -> bool:
    return source in INTERACTIVE_TASK_SOURCES
