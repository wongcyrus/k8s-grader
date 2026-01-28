import logging
import random
from datetime import datetime
from typing import Any, Dict, Optional

from common.database import (
    delete_game_session,
    delete_ongoing_npc_task,
    get_ai_random_chat,
    get_game_session,
    get_npc_background,
    get_npc_lock,
    get_ongoing_npc_task,
    get_tasks_by_email_and_game,
    get_user_data,
    save_game_task,
    save_npc_lock,
    save_test_record,
)
from common.file import clear_tmp_directory, create_json_input, write_user_files
from common.google_spreadsheet import get_easter_egg_link
from common.handler import (
    error_response,
    extract_k8s_credentials,
    get_email_game_and_npc_from_event,
    ok_response,
    setup_paths,
    test_result_response,
)
from common.pytest import get_current_task, get_next_game_phrase, run_tests
from common.s3 import generate_presigned_url, get_bucket_key, upload_test_result
from common.status import GamePhrase, TestResult

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


setup_paths()


def get_game_phrase(event: Dict[str, Any]) -> Optional[GamePhrase]:
    query_params = event.get("queryStringParameters")
    if not query_params:
        return None
    phrase = query_params.get("phrase").lower()
    return {
        "ready": GamePhrase.READY,
        "challenge": GamePhrase.CHALLENGE,
        "check": GamePhrase.CHECK,
    }.get(phrase)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:  # pylint: disable=W0613

    game_phrase = get_game_phrase(event)
    if not game_phrase:
        return error_response("Phrase parameter is missing or not supported.")

    email, game, npc = get_email_game_and_npc_from_event(event)
    if not email or not game or not npc:
        return error_response("Email, Game, or NPC parameter is missing")
    if not game.isalnum():
        return error_response("Game parameter must be a single alphanumeric word")

    npc_background = get_npc_background(npc)
    if not npc_background:
        return error_response(f"NPC {npc} not found in the background database")

    if get_npc_lock(email, game, npc):
        return error_response(f"{npc} does not have any task for you!")
    ongoing_npc, _ = get_ongoing_npc_task(email, game)
    if ongoing_npc and ongoing_npc != npc:
        return error_response(f"You need to complete task from {ongoing_npc} first!")

    if random.random() < 0.3:
        message = get_ai_random_chat(npc)
        if message is None:
            message = "..."
        return ok_response(message)

    user_data = get_user_data(email)
    if not user_data:
        return error_response("Email not found in the database")

    client_certificate, client_key, endpoint = extract_k8s_credentials(user_data)

    if not all([client_certificate, client_key, endpoint]):
        return error_response("K8s credentials are missing.")

    clear_tmp_directory()
    write_user_files(client_certificate, client_key)

    finished_tasks = get_tasks_by_email_and_game(email, game)
    current_task = get_current_task(game, finished_tasks)
    logger.info(current_task)
    if not current_task:
        return ok_response("All tasks are completed!")

    session = get_game_session(email, game, current_task)
    if session is None:
        return error_response("Session not found, and no ongoing task.")
    logger.info(session)

    # In case the key or endpoint is changed, remove the session.
    required_keys = ["$endpoint", "$client_key", "$client_certificate"]
    for key in required_keys:
        if session[key] != locals()[key[1:]]:
            delete_game_session(email, game, current_task)
            return error_response("Cluster setting is difference from setup!")

    try:
        create_json_input(endpoint, session)
        test_result = run_tests(game_phrase, game, current_task)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        upload_test_result(
            "/tmp/report.html", game_phrase, now_str, email, game, current_task
        )
        report_url = generate_presigned_url(
            game_phrase, now_str, email, game, current_task
        )

        bucket, key = get_bucket_key(email, game, current_task, game_phrase, now_str)
        save_test_record(
            email,
            game,
            current_task,
            game_phrase,
            test_result,
            bucket,
            key,
            report_url,
            now_str,
        )
        easter_egg_url = get_easter_egg_link(test_result)
        if test_result == TestResult.OK and game_phrase == GamePhrase.CHECK:
            save_game_task(email, game, current_task)
            test_cleanup_result = run_tests(GamePhrase.CLEANUP, game, current_task)
            upload_test_result(
                "/tmp/report.html", game_phrase, now_str, email, game, current_task
            )
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            upload_test_result(
                "/tmp/report.html",
                GamePhrase.CLEANUP,
                now_str,
                email,
                game,
                current_task,
            )
            bucket, key = get_bucket_key(
                email, game, current_task, GamePhrase.CLEANUP, now_str
            )
            save_test_record(
                email,
                game,
                current_task,
                GamePhrase.CLEANUP,
                test_cleanup_result,
                bucket,
                key,
                report_url,
                now_str,
            )
            delete_ongoing_npc_task(email, game)
            save_npc_lock(email, game, npc)
            return test_result_response(
                game_phrase,
                None,
                test_result,
                f"{current_task} Completed!",
                report_url,
                easter_egg_url,
            )
    except (KeyError, ValueError, RuntimeError) as e:
        return error_response(f"{type(e).__name__}: {str(e)}")

    next_game_phrase = game_phrase
    if test_result == TestResult.OK:
        next_game_phrase = get_next_game_phrase(game, current_task, game_phrase)

    return test_result_response(
        game_phrase,
        next_game_phrase,
        test_result,
        f"For {game_phrase.value} of {test_result.name}. {session['$instruction']}",
        report_url,
        easter_egg_url,
    )
