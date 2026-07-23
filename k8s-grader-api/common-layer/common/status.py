from enum import Enum


class GamePhrase(Enum):
    SETUP = "setup"
    READY = "ready"
    ANSWER = "answer"
    CHALLENGE = "challenge"
    CHECK = "check"
    CLEANUP = "cleanup"


class TestResult(Enum):
    OK = 0
    TESTS_FAILED = 1
    INTERRUPTED = 2
    INTERNAL_ERROR = 3
    USAGE_ERROR = 4
    NO_TESTS_COLLECTED = 5
    TIME_OUT = 6


TestResult.__test__ = False
