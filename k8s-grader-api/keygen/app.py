import logging
import os
import re
from typing import Any, Dict, Optional

import boto3
from common.database import get_api_key, save_api_key
from common.handler import text_response
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SECRET_HASH = os.getenv("SecretHash")
API_GATEWAY_API_NAME = os.getenv("ApiGateWayName")
USAGE_PLAN_ID_NAME = os.getenv("UsagePlanName")
STAGE_NAME = os.getenv("StageName")

client = boto3.client("apigateway")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:  # pylint: disable=W0613
    query_params = event.get("queryStringParameters")
    if not query_params:
        return text_response("Secret and email parameter is missing.")

    secret = query_params.get("secret")
    email = query_params.get("email")
    if not secret or not email:
        return text_response("Secret and email parameter is missing.")
    if secret != SECRET_HASH:
        return text_response("Invalid secret")
    if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
        return text_response("Invalid email address.")

    api_key = get_api_key(email)
    if api_key:
        return text_response(api_key)

    rest_api_id = get_rest_api_id(API_GATEWAY_API_NAME)
    if not rest_api_id:
        return text_response("API Gateway API not found.")

    token = generate_token(secret, email)
    api_key = create_api_key(email, token, rest_api_id)
    if not api_key:
        return text_response("Failed to create API key.")

    usage_plan_id = get_usage_plan_id(USAGE_PLAN_ID_NAME)
    if not usage_plan_id:
        return text_response("Usage plan not found.")

    if not associate_api_key_with_usage_plan(api_key, usage_plan_id):
        return text_response("Failed to associate API key with usage plan.")

    api_key_value = get_api_key_value(api_key)
    if not api_key_value:
        return text_response("Failed to retrieve API key value.")

    save_api_key(email, api_key_value)
    return text_response(api_key_value)


def get_rest_api_id(api_name: str) -> Optional[str]:
    rest_apis = client.get_rest_apis().get("items", [])
    for api in rest_apis:
        if api.get("name") == api_name:
            return api.get("id")
    return None


def generate_token(secret: str, email: str) -> str:
    fernet = Fernet(secret)
    return fernet.encrypt(email.encode()).decode()


def create_api_key(name: str, value: str, rest_api_id: str) -> Optional[str]:
    try:
        response = client.create_api_key(
            name=name,
            value=value,
            enabled=True,
            stageKeys=[{"restApiId": rest_api_id, "stageName": STAGE_NAME}],
        )
        return response.get("id")
    except Exception as e:
        logger.error(f"Error creating API key: {e}")
        return None


def get_usage_plan_id(plan_name: str) -> Optional[str]:
    usage_plans = client.get_usage_plans().get("items", [])
    for plan in usage_plans:
        if plan.get("name") == plan_name:
            return plan.get("id")
    return None


def associate_api_key_with_usage_plan(api_key: str, usage_plan_id: str) -> bool:
    try:
        client.create_usage_plan_key(
            usagePlanId=usage_plan_id, keyId=api_key, keyType="API_KEY"
        )
        logger.info(f"Successfully associated API key {api_key} with usage plan {usage_plan_id}")
        return True
    except client.exceptions.ConflictException:
        logger.warning(f"API key {api_key} already associated with usage plan {usage_plan_id}")
        return True
    except client.exceptions.ClientError as e:
        logger.error("Error associating API key with usage plan: %s", e, exc_info=True)
        return False


def get_api_key_value(api_key: str) -> Optional[str]:
    response = client.get_api_key(apiKey=api_key, includeValue=True)
    return response.get("value")
