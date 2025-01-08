from common.pytest import get_current_task, run_tests, GamePhase
from common.database import get_email_from_event, get_game_session, get_tasks_by_email_and_game, get_user_data
from common.file import clear_tmp_directory, write_user_files, create_json_input
import json
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


os.environ["PATH"] += os.pathsep + "/opt/kubectl/"
os.environ["PATH"] += os.pathsep + "/opt/helm/"


def lambda_handler(event, context):

    email = get_email_from_event(event)
    game = event.get('queryStringParameters', {}).get('game')
    if not email:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Email parameter is missing"})
        }

    user_data = get_user_data(email)
    if not user_data:
        return {
            "statusCode": 404,
            "body": json.dumps({"message": "Email not found in the database"})
        }

    client_certificate = user_data.get('client_certificate')
    client_key = user_data.get('client_key')
    endpoint = user_data.get('endpoint')

    if not all([client_certificate, client_key, endpoint]):
        return {
            "statusCode": 500,
            "body": json.dumps({"message": "Incomplete user data"})
        }
    clear_tmp_directory()
    write_user_files(client_certificate, client_key)

    finished_tasks = get_tasks_by_email_and_game(email, game)
    current_task = get_current_task(game, finished_tasks)
    logger.info(current_task)
    session = get_game_session(email, game, current_task)
    if session is None:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": "Sesson is missing"})
        }
    logger.info(session)

    try:
        create_json_input(endpoint, {"namespace": "demo"})
        retcode = run_tests(GamePhase.CHECK, "game01",
                            "test_02_create_namespace.py")
        with open('/tmp/report.html', 'r', encoding="utf-8") as report:
            report_content = report.read()
    except (OSError, IOError) as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"{type(e).__name__}: {str(e)}"})
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Unexpected error: {type(e).__name__}: {str(e)}"})
        }

    return {
        "statusCode": 200,
        "body": json.dumps({"retcode": retcode, "report_content": report_content})
    }
