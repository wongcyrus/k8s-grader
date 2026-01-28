import json
import os
from typing import Any, Dict, Optional, Tuple

from common.status import GamePhrase, TestResult
from cryptography.fernet import Fernet

SECRET_HASH = os.getenv("SecretHash")


def setup_paths() -> None:
    os.environ["PATH"] += os.pathsep + "/opt/kubectl/"
    os.environ["PATH"] += os.pathsep + "/opt/helm/"


def error_response(message: str) -> Dict[str, Any]:
    return {
        "headers": {
            "Content-type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
        "statusCode": 200,
        "body": json.dumps({"status": "Error", "message": message}),
    }


def ok_response(message: str) -> Dict[str, Any]:
    return {
        "headers": {
            "Content-type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
        "statusCode": 200,
        "body": json.dumps({"status": "OK", "message": message}),
    }


def html_response(html_content: str) -> Dict[str, Any]:
    return {
        "headers": {
            "Content-Type": "text/html",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
        "statusCode": 200,
        "body": html_content,
    }


def text_response(text_content: str) -> Dict[str, Any]:
    return {
        "headers": {
            "Content-Type": "text/plain",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
        "statusCode": 200,
        "body": text_content,
    }


def test_result_response(
    game_phrase: GamePhrase,
    next_game_phrase: Optional[GamePhrase],
    test_result: TestResult,
    instruction: str,
    report_url: str,
    easter_egg_url: Optional[str],
) -> Dict[str, Any]:
    return {
        "headers": {
            "Content-Type": "text/html",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
        "statusCode": 200,
        "body": json.dumps(
            {
                "game_phrase": game_phrase.name,
                "next_game_phrase": next_game_phrase.name if next_game_phrase else "",
                "status": test_result.name,
                "message": instruction,
                "report_url": report_url,
                "easter_egg_url": easter_egg_url if easter_egg_url else "",
            }
        ),
    }


def extract_k8s_credentials(user_data: Dict[str, Any]) -> Tuple[str, str, str]:
    client_certificate = user_data.get("client_certificate")
    client_key = user_data.get("client_key")
    endpoint = user_data.get("endpoint")
    return client_certificate, client_key, endpoint


def get_email_game_and_npc_from_event(event: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    api_key = event["headers"].get("x-api-key")
    if not api_key:
        return None, None, None

    email = get_email_from_api_key(api_key)
    query_params = event.get("queryStringParameters")
    if query_params:
        return email, query_params.get("game"), query_params.get("npc")
    return None, None, None


def get_email_from_event(event: Dict[str, Any]) -> Optional[str]:
    api_key = event["headers"].get("x-api-key")
    return get_email_from_api_key(api_key) if api_key else None


def get_email_from_api_key(api_key: str) -> str:
    if not api_key:
        raise ValueError("API key is required")
    try:
        fernet = Fernet(SECRET_HASH)
        return fernet.decrypt(api_key.encode()).decode()
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid API key format: {e}") from e
