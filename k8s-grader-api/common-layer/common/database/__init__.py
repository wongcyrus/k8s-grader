"""Database package"""
from .repositories import (
    TaskStateRepository,
    NpcRepository,
    AccountRepository,
    ApiKeyRepository,
    GameTaskRepository,
    SessionRepository,
    TestRecordRepository,
    NpcTaskRepository,
    NpcBackgroundRepository,
    NpcLockRepository,
    ConversationRepository,
    GameSourceRepository,
    GameAccessRepository,
    ExamCodeRepository,
    ExamSessionRepository,
    normalize_endpoint,
)

__all__ = [
    'TaskStateRepository',
    'NpcRepository',
    'AccountRepository',
    'ApiKeyRepository',
    'GameTaskRepository',
    'SessionRepository',
    'TestRecordRepository',
    'NpcTaskRepository',
    'NpcBackgroundRepository',
    'NpcLockRepository',
    'ConversationRepository',
    'GameSourceRepository',
    'GameAccessRepository',
    'ExamCodeRepository',
    'ExamSessionRepository',
    'normalize_endpoint',
    # Backward-compatible function exports
    'save_game_source',
    'save_npc_background',
    'get_game_source',
    'get_npc_background',
    'get_api_key',
    'save_api_key',
    'is_endpoint_exist',
    'save_account',
    'get_user_data',
    'normalize_endpoint_url',
    'get_ai_instruction_template',
    'get_ai_random_chat',
]

# Backward-compatible wrapper functions for legacy code
# These use singleton instances of repositories

_game_source_repo = None
_npc_background_repo = None
_api_key_repo = None
_account_repo = None
_conversation_repo = None


def _get_game_source_repo():
    global _game_source_repo
    if _game_source_repo is None:
        _game_source_repo = GameSourceRepository()
    return _game_source_repo


def _get_npc_background_repo():
    global _npc_background_repo
    if _npc_background_repo is None:
        _npc_background_repo = NpcBackgroundRepository()
    return _npc_background_repo


def _get_api_key_repo():
    global _api_key_repo
    if _api_key_repo is None:
        _api_key_repo = ApiKeyRepository()
    return _api_key_repo


def _get_account_repo():
    global _account_repo
    if _account_repo is None:
        _account_repo = AccountRepository()
    return _account_repo


def _get_conversation_repo():
    global _conversation_repo
    if _conversation_repo is None:
        _conversation_repo = ConversationRepository()
    return _conversation_repo


# Backward-compatible functions
def save_game_source(game: str, source: str) -> None:
    """Save game source URL (backward-compatible wrapper)"""
    _get_game_source_repo().save(game, source)


def get_game_source(game: str):
    """Get game source URL (backward-compatible wrapper)"""
    return _get_game_source_repo().get(game)


def save_npc_background(name: str, age: str, gender: str, background: str) -> None:
    """Save NPC background (backward-compatible wrapper)"""
    _get_npc_background_repo().save(name, age, gender, background)


def get_npc_background(name: str):
    """Get NPC background (backward-compatible wrapper)"""
    return _get_npc_background_repo().get(name)


def get_api_key(email: str):
    """Get API key (backward-compatible wrapper)"""
    return _get_api_key_repo().get(email)


def save_api_key(email: str, api_key: str) -> None:
    """Save API key (backward-compatible wrapper)"""
    _get_api_key_repo().save(email, api_key)


def is_endpoint_exist(email: str, endpoint: str) -> bool:
    """Check if endpoint exists (backward-compatible wrapper)"""
    return _get_account_repo().is_endpoint_exist(email, endpoint)


def save_account(
    email: str,
    endpoint: str,
    client_certificate: str | None,
    client_key: str | None,
) -> None:
    """Save account (backward-compatible wrapper)"""
    _get_account_repo().save(email, endpoint, client_certificate, client_key)


def get_user_data(email: str):
    """Get user data (backward-compatible wrapper)"""
    return _get_account_repo().get(email)


def normalize_endpoint_url(endpoint: str) -> str:
    """Normalize account endpoints (backward-compatible wrapper)."""
    return normalize_endpoint(endpoint)


def get_ai_instruction_template(game: str, task: str, npc: str):
    """Get AI instruction template (backward-compatible wrapper)"""
    return _get_conversation_repo().get_instruction_template(game, task, npc)


def get_ai_random_chat(npc: str):
    """Get AI random chat (backward-compatible wrapper)"""
    return _get_conversation_repo().get_random_chat(npc)
