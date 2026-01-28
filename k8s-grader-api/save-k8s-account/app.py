import base64
import logging
from typing import Any, Dict, Optional

from common.database import is_endpoint_exist, save_account
from common.handler import (
    error_response,
    get_email_from_event,
    html_response,
    ok_response,
)
from requests_toolbelt.multipart import decoder

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def read_html_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def decode_post_data(event: Dict[str, Any]) -> bytes:
    return (
        base64.b64decode(event["body"])
        if event.get("isBase64Encoded")
        else event["body"].encode("utf-8")
    )


def parse_multipart_data(post_data: bytes, content_type: str) -> Dict[str, Any]:
    multipart_data = decoder.MultipartDecoder(post_data, content_type)
    fs = {}
    for part in multipart_data.parts:
        content_disposition = part.headers[b"Content-Disposition"].decode("utf-8")
        name = content_disposition.split("name=")[1].split(";")[0].strip('"')
        fs[name] = part
    return fs


def validate_input(email: str, endpoint: str, client_certificate: str, client_key: str) -> Optional[str]:
    if not client_certificate or not client_key:
        return "Missing client-certificate or client-key"
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return "Invalid email format"
    if not endpoint or (not endpoint.startswith("http://") and not endpoint.startswith("https://")):
        return "Invalid endpoint format"
    if len(client_certificate) < 100 or len(client_key) < 100:
        return "Invalid certificate or key length"
    return None


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:  # pylint: disable=W0613
    if event["httpMethod"] == "GET":
        html_content = read_html_file("save-account.html")
        return html_response(html_content)

    if event["httpMethod"] == "POST":
        content_type = event["headers"].get("Content-Type") or event["headers"].get(
            "content-type"
        )
        if content_type.startswith("multipart/form-data"):
            post_data = decode_post_data(event)
            fs = parse_multipart_data(post_data, content_type)

            email = get_email_from_event(event)
            endpoint = fs["endpoint"].text
            client_certificate = fs["client-certificate"].text
            client_key = fs["client-key"].text

            validation_error = validate_input(
                email, endpoint, client_certificate, client_key
            )
            if validation_error:
                return error_response(validation_error)

            if is_endpoint_exist(email, endpoint):
                return error_response(
                    "Endpoint already exists, and no Sharing K8s cluster!"
                )

            save_account(email, endpoint, client_certificate, client_key)
            return ok_response("Data saved successfully")

        return error_response("Unsupported content type")

    return error_response("Unsupported HTTP method")
