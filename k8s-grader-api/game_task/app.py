import logging
import random
from datetime import datetime
from typing import Any, Dict

from common.database import (
    get_ai_instruction_template,
    get_ai_random_chat,
    get_game_session,
    get_npc_background,
    get_npc_lock,
    get_ongoing_npc_task,
    get_tasks_by_email_and_game,
    get_user_data,
    save_game_session,
    save_npc_task_as_ongoing,
    save_test_record,
)
from common.file import clear_tmp_directory, create_json_input, write_user_files
from common.handler import (
    error_response,
    extract_k8s_credentials,
    get_email_game_and_npc_from_event,
    ok_response,
    setup_paths,
    test_result_response,
)
from common.pytest import (
    get_ai_instruction,
    get_current_task,
    get_instruction,
    get_next_game_phrase,
    run_tests,
)
from common.s3 import generate_presigned_url, get_bucket_key, upload_test_result
from common.session import generate_session
from common.status import GamePhrase, TestResult

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

setup_paths()


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:  # pylint: disable=W0613

    email, game, npc = get_email_game_and_npc_from_event(event)
    if not email or not game or not npc:
        return error_response("Email, Game, or NPC parameter is missing.")
    if not game.isalnum():
        return error_response("Game parameter must be a single alphanumeric word.")

    finished_tasks = get_tasks_by_email_and_game(email, game)
    current_task = get_current_task(game, finished_tasks)
    logger.info(current_task)
    if not current_task:
        return ok_response("All tasks are completed")

    npc_background = get_npc_background(npc)
    main_background = get_npc_background("main_character")
    if not npc_background or not main_background:
        return error_response(
            f"NPC {npc} or main character not found in the background database"
        )

    if random.random() < 0.3:
        message = get_ai_random_chat(npc)
        if message is None:
            message = "..."
        return ok_response(message)

    if get_npc_lock(email, game, npc):
        return error_response(f"{npc} does not have any task for you!")
    ongoing_npc, _ = get_ongoing_npc_task(email, game)
    if ongoing_npc and ongoing_npc != npc:
        return error_response(f"You need to complete task from {ongoing_npc} first!")

    user_data = get_user_data(email)
    if not user_data:
        return error_response(f"{email} not found in the database")

    client_certificate, client_key, endpoint = extract_k8s_credentials(user_data)

    if not all([client_certificate, client_key, endpoint]):
        return error_response("K8s credentials are missing.")

    clear_tmp_directory()
    write_user_files(client_certificate, client_key)

    instruction = None
    session = get_game_session(email, game, current_task)
    if session is None:
        session = generate_session(email, game, current_task)
        ai_instruction_template = get_ai_instruction_template(game, current_task, npc)
        if ai_instruction_template:
            instruction = get_ai_instruction(ai_instruction_template, session)
        else:
            instruction = get_instruction(game, current_task, session)

        if not instruction:
            return error_response("Instruction not found!")
    else:
        instruction = session["$instruction"]
    session["$instruction"] = instruction
    # Always update the k8s credentials from DynamoDB to make sure they are up-to-date.
    session["$client_certificate"] = client_certificate
    session["$client_key"] = client_key
    session["$endpoint"] = endpoint

    try:
        create_json_input(endpoint, session)
        test_result = run_tests(GamePhrase.SETUP, game, current_task)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        upload_test_result(
            "/tmp/report.html", GamePhrase.SETUP, now_str, email, game, current_task
        )
        report_url = generate_presigned_url(
            GamePhrase.SETUP, now_str, email, game, current_task
        )
        bucket, key = get_bucket_key(
            email, game, current_task, GamePhrase.SETUP, now_str
        )
        save_test_record(
            email,
            game,
            current_task,
            GamePhrase.SETUP,
            test_result,
            bucket,
            key,
            report_url,
            now_str,
        )

    except (FileNotFoundError, ValueError, KeyError) as e:
        return error_response(f"{type(e).__name__}: {str(e)}")

    if test_result == TestResult.OK:
        save_game_session(email, game, current_task, session)
        logger.info(session)

        next_game_phrase = get_next_game_phrase(game, current_task, GamePhrase.SETUP)
        save_npc_task_as_ongoing(email, game, npc, current_task)
        return test_result_response(
            GamePhrase.SETUP,
            next_game_phrase,
            test_result,
            instruction,
            report_url,
            None,
        )
    return error_response("Setup failed!")
