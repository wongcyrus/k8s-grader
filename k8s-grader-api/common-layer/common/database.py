import json
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import boto3
from boto3.dynamodb.conditions import Key
from common.status import GamePhrase, TestResult

dynamodb = boto3.resource("dynamodb")

account_table = dynamodb.Table(os.getenv("AccountTable"))
game_task_table = dynamodb.Table(os.getenv("GameTaskTable"))
session_table = dynamodb.Table(os.getenv("SessionTable"))
api_key_table = dynamodb.Table(os.getenv("ApiKeyTable"))
test_record_table = dynamodb.Table(os.getenv("TestRecordTable"))
npc_task_table = dynamodb.Table(os.getenv("NpcTaskTable"))
npc_lock_table = dynamodb.Table(os.getenv("NpcLockTable"))
npc_background_table = dynamodb.Table(os.getenv("NpcBackgroundTable"))
conversation_table = dynamodb.Table(os.getenv("ConversationTable"))
game_source_table = dynamodb.Table(os.getenv("GameSourceTable"))


def is_endpoint_exist(email: str, endpoint: str) -> bool:
    response = account_table.query(
        IndexName="EndpointIndex", KeyConditionExpression=Key("endpoint").eq(endpoint)
    )
    items = response.get("Items", [])
    if items:
        return items[0].get("email") != email
    return False


def save_account(email: str, endpoint: str, client_certificate: str, client_key: str) -> None:
    account_table.put_item(
        Item={
            "email": email,
            "endpoint": endpoint,
            "client_certificate": client_certificate,
            "client_key": client_key,
            "time": int(time.time()),
        }
    )


def get_user_data(email: str) -> Optional[Dict[str, Any]]:
    response = account_table.get_item(Key={"email": email})
    return response.get("Item")


def get_tasks_by_email_and_game(email: str, game: str) -> List[str]:
    if not email or not game:
        return []
    if not game.isalnum():
        raise ValueError("Game parameter must be alphanumeric")
    
    response = game_task_table.query(
        KeyConditionExpression=Key("email").eq(email)
        & Key("game").begins_with(f"{game}#")
    )

    items = response.get("Items", [])
    return sorted([item["game"].split("#", 1)[1] for item in items])


def save_game_task(email: str, game: str, task: str) -> None:
    game_task_table.put_item(
        Item={"email": email, "game": f"{game}#{task}", "time": int(time.time())}
    )


def delete_game_task(email: str, game: str, task: str) -> None:
    game_task_table.delete_item(Key={"email": email, "game": f"{game}#{task}"})


def save_game_session(email: str, game: str, task: str, session: Dict[str, Any]) -> None:
    session_table.put_item(
        Item={
            "email": email,
            "game": f"{game}#{task}",
            "session": json.dumps(session),
            "time": int(time.time()),
        }
    )


def delete_game_session(email: str, game: str, task: str) -> None:
    session_table.delete_item(Key={"email": email, "game": f"{game}#{task}"})


def get_game_session(email: str, game: str, task: str) -> Optional[Dict[str, Any]]:
    response = session_table.get_item(Key={"email": email, "game": f"{game}#{task}"})
    item = response.get("Item")
    if item:
        return json.loads(item["session"])
    return None


def get_api_key(email: str) -> Optional[str]:
    response = api_key_table.get_item(Key={"email": email})
    item = response.get("Item")
    if item:
        return item["api_key"]
    return None


def save_api_key(email: str, api_key: str) -> None:
    api_key_table.put_item(Item={"email": email, "api_key": api_key})


def save_test_record(
    email: str,
    game: str,
    current_task: str,
    game_phase: GamePhrase,
    test_result: TestResult,
    bucket: str,
    key: str,
    report_url: str,
    now_str: str,
) -> None:
    test_record_table.put_item(
        Item={
            "email": email,
            "gameTime": game + "#" + now_str,
            "task": current_task,
            "gamePhase": game_phase.name,
            "testResult": test_result.name,
            "bucket": bucket,
            "key": key,
            "reportUrl": report_url,
            "time": now_str,
        }
    )


def save_npc_task_as_ongoing(email: str, game: str, npc: str, task: str) -> None:
    npc_task_table.put_item(
        Item={
            "email": email,
            "game": game,
            "npc": npc,
            "task": task,
            "time": int(time.time()),
        }
    )


def get_ongoing_npc_task(email: str, game: str) -> Tuple[Optional[str], Optional[str]]:
    response = npc_task_table.get_item(Key={"email": email, "game": game})
    item = response.get("Item")
    if item:
        return item["npc"], item["task"]
    return None, None


def delete_ongoing_npc_task(email: str, game: str) -> None:
    npc_task_table.delete_item(Key={"email": email, "game": game})


def save_npc_lock(email: str, game: str, npc: str) -> None:
    if not email or not game or not npc:
        raise ValueError("Email, game, and npc are required")
    expiration_time = int((datetime.now() + timedelta(minutes=30)).timestamp())
    npc_lock_table.put_item(
        Item={
            "email": email,
            "gameNpc": game + "#" + npc,
            "ttl": expiration_time,
            "time": int(time.time()),
        }
    )


def get_npc_lock(email: str, game: str, npc: str) -> Optional[Dict[str, Any]]:
    response = npc_lock_table.get_item(
        Key={"email": email, "gameNpc": game + "#" + npc}
    )
    item = response.get("Item")
    if item:
        return item
    return None


def get_npc_background(name: str) -> Optional[Dict[str, str]]:
    response = npc_background_table.get_item(Key={"name": name})
    item = response.get("Item")
    if item:
        return {
            "name": item.get("name"),
            "age": item.get("age"),
            "gender": item.get("gender"),
            "background": item.get("background"),
        }
    return None


def save_npc_background(name: str, age: str, gender: str, background: str) -> None:
    npc_background_table.put_item(
        Item={
            "name": name,
            "age": age,
            "gender": gender,
            "background": background,
            "time": int(time.time()),
        }
    )


def get_ai_instruction_template(game: str, task: str, npc: str) -> Optional[str]:
    key = f"{game}#{task}#{npc}"
    response = conversation_table.get_item(Key={"key": key})
    if response.get("Item"):
        return response.get("Item")["instruction"]
    return None


def get_ai_random_chat(npc: str) -> Optional[str]:
    response = conversation_table.get_item(Key={"key": npc})
    if response.get("Item"):
        return response.get("Item")["instruction"]
    return None


def get_game_source(game: str) -> Optional[str]:
    response = game_source_table.get_item(Key={"game": game})
    return response.get("Item")["source"] if response.get("Item") else None


def save_game_source(game: str, source: str) -> None:
    game_source_table.put_item(
        Item={
            "game": game,
            "source": source,
            "time": int(time.time()),
        }
    )
