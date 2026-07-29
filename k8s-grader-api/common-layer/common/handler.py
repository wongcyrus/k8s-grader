import json
import os
import re
from typing import Any, Dict, Optional, Tuple

from common.kubeconfig import build_kubeconfig
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


def extract_k8s_access_config(user_data: Dict[str, Any]) -> Dict[str, Any]:
    endpoint = user_data.get("endpoint")
    client_certificate = user_data.get("client_certificate")
    client_key = user_data.get("client_key")
    bearer_token = user_data.get("bearer_token")
    ca_certificate = user_data.get("ca_certificate")
    kubeconfig = user_data.get("kubeconfig")
    auth_type = user_data.get("auth_type")
    insecure_skip_tls_verify = bool(user_data.get("insecure_skip_tls_verify", False))

    if not kubeconfig and endpoint and (bearer_token or (client_certificate and client_key)):
        kubeconfig = build_kubeconfig(
            endpoint,
            client_certificate=client_certificate,
            client_key=client_key,
            bearer_token=bearer_token,
            ca_certificate=ca_certificate,
            insecure_skip_tls_verify=insecure_skip_tls_verify or not bool(ca_certificate),
        )

    if not auth_type:
        if bearer_token:
            auth_type = "token"
        elif client_certificate and client_key:
            auth_type = "client_certificate"
        else:
            auth_type = ""

    return {
        "endpoint": endpoint,
        "client_certificate": client_certificate,
        "client_key": client_key,
        "bearer_token": bearer_token,
        "ca_certificate": ca_certificate,
        "kubeconfig": kubeconfig,
        "auth_type": auth_type,
        "insecure_skip_tls_verify": insecure_skip_tls_verify,
    }


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
    except Exception as e:
        # Catch all decryption errors including InvalidToken, padding errors, etc.
        raise ValueError(f"Invalid or expired API key: {type(e).__name__}") from e


def to_player_safe_game_message(message: Optional[str]) -> str:
    if not message:
        return ""

    no_task_match = re.match(r"^(.+?) does not have any task for you!?$", message)
    if no_task_match:
        return f"{no_task_match.group(1)} has no task for you right now."

    assigned_npc_match = re.match(r"^Complete task from (.+) first!?$", message)
    if assigned_npc_match:
        return f"Finish your task from {assigned_npc_match.group(1)} first."

    missing_npc_match = re.match(r"^NPC '(.+)' not found$", message)
    if missing_npc_match:
        return f"{missing_npc_match.group(1)} is unavailable right now."

    if message in {"API key is required"} or message.startswith("Invalid or expired API key:"):
        return "Your game link is invalid or expired. Please open a fresh game link."

    if message == "User account not found":
        return "Please save your Kubernetes account first."

    if message == "K8s credentials missing or incomplete":
        return "Your Kubernetes account details are incomplete. Please save them again."

    if message in {"Missing required websocket parameters", "Missing subscribe parameters"}:
        return "This game link is missing required details. Please reopen the game from the correct link."

    if message == "Missing websocket connection details":
        return "The game connection is incomplete. Please refresh and try again."

    if message == "Game parameter must be alphanumeric":
        return "This game link is invalid. Please reopen the game from the correct link."

    if message == "GameCommandDurableFunctionArn is not configured":
        return "The game server is not ready right now. Please try again later."

    return message
