import base64
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from common.database import is_endpoint_exist, save_account
from common.handler import (
    error_response,
    get_email_from_event,
    html_response,
    ok_response,
    setup_paths,
)
from requests_toolbelt.multipart import decoder

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

setup_paths()

FAKE_CLIENT_CERTIFICATE = (
    "-----BEGIN CERTIFICATE-----\n"
    "MIIDETCCAfmgAwIBAgIUCxQDsZWdnX07iV9S4aVdycKsLsUwDQYJKoZIhvcNAQEL\n"
    "BQAwGDEWMBQGA1UEAwwNbWluaWt1YmUtZmFrZTAeFw0yNjA3MjEwMjMxMzJaFw0y\n"
    "NjA3MjIwMjMxMzJaMBgxFjAUBgNVBAMMDW1pbmlrdWJlLWZha2UwggEiMA0GCSqG\n"
    "SIb3DQEBAQUAA4IBDwAwggEKAoIBAQDvgZCqYf9slAmyI/ALS6O4PtMYd1hrYKxD\n"
    "/uddr6S+YLtnoAPjpQMmyp29LSR1DIAE5gt4I/BvMgBhlydRaNnNnIzElOJApXcv\n"
    "UtxHI3DQah0d2LWe5/4kKYoQq/iSTbcJlBUaW6Uta966egPa8bVwMS4ZF49OPlQG\n"
    "TG17CDtbMuqDFDMf3kqCa8H7Iko1QOwToJd6gKPHWi+P39dz7ez6Qz0l+hPQhABI\n"
    "lVzXDsc5RHw7f52QZlDaiofceAmodzhkLWLMYYEa55PyXaiksP31rU9Wl/DaJeW0\n"
    "b8ulY1+HcGkzP/q095YyMxubmBACQn8t/b6zJy/SOLILRgsvZfJZAgMBAAGjUzBR\n"
    "MB0GA1UdDgQWBBReM++taRun6Y3xBXtcrD3eDctLADAfBgNVHSMEGDAWgBReM++t\n"
    "aRun6Y3xBXtcrD3eDctLADAPBgNVHRMBAf8EBTADAQH/MA0GCSqGSIb3DQEBCwUA\n"
    "A4IBAQB0kpPoIvdQvIbwukkvpRVCLy5fBkmE5ExlLz3wGSt/gznmiik7pZmynPH0\n"
    "e1Oiwi1cblSs+KSX4AHxBXw7L3tBvgdO+KI/deh8b/y+8AwtQCffgFb/xXJBjKRH\n"
    "EZOUr8+wStT2PuVhU2wYUv7KTXwdHdkT7FWgeSHBwkpl9GTyd1dLTU90xTzhhYOW\n"
    "Not/+P78YE2XWJXc6Agy4m4CsL533RNDpZ7ICp1uhqvgN8nhv6V7Z75fo8xlXQm1\n"
    "xRC2C2DRvEJUnOeb+YM/ICVjD8531ViqXsPaRbJ2+Z7Z8vqr6tpLDCEww8PYKyfG\n"
    "GtVicEA5g4fszaZjFAKZ/rRCq0Si\n"
    "-----END CERTIFICATE-----"
)
FAKE_CLIENT_KEY = (
    "-----BEGIN PRIVATE KEY-----\n"
    "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDvgZCqYf9slAmy\n"
    "I/ALS6O4PtMYd1hrYKxD/uddr6S+YLtnoAPjpQMmyp29LSR1DIAE5gt4I/BvMgBh\n"
    "lydRaNnNnIzElOJApXcvUtxHI3DQah0d2LWe5/4kKYoQq/iSTbcJlBUaW6Uta966\n"
    "egPa8bVwMS4ZF49OPlQGTG17CDtbMuqDFDMf3kqCa8H7Iko1QOwToJd6gKPHWi+P\n"
    "39dz7ez6Qz0l+hPQhABIlVzXDsc5RHw7f52QZlDaiofceAmodzhkLWLMYYEa55Py\n"
    "XaiksP31rU9Wl/DaJeW0b8ulY1+HcGkzP/q095YyMxubmBACQn8t/b6zJy/SOLIL\n"
    "RgsvZfJZAgMBAAECggEAAh9TDZt4NLlcG6LDZAo7zWxrGPanxy3QYPrfiH4/trsr\n"
    "NfgeSLRj4oJdovlFLy9Y7BIwzFP/M7EM/VBmVguYkICgY7aRCbMdqwLwNkYrYAFs\n"
    "uCC9PUb/gskGcu7fMUa0hkZ0aGsi+9POobbmlVhae//HkYvapn4ZZwPi3Xn9cqms\n"
    "tESEoBbxufmXkXOfMVJaQhJtjyMlx8O07gAvIqzyGL06phs8vA9/mD7YnhcECEYO\n"
    "e8/91ngoVF/Kh9w/XRSDtcXZTCDL0XsAleZdOqFMcXUsUq++BZe7qdRZ4AeXND89\n"
    "vj9qFciroC6vqotwTYsQY3CxyRshycnP1RTuxKrpHQKBgQD69pgWvScREBGNS0Rl\n"
    "AwQWfpjB2LGGCjXOLVz73moTdoLKIA8kIRqYmL8nOUAYweyKlMMUcLsmj89Z+icV\n"
    "vP0ZmQO7iUk8AQC6jALxOdTEa5N+pjhIkYPkZQ4AfcplvS5jOXN/OU/nshNGfX8t\n"
    "fGbfFqyfnxinQ6s088b3K4cQLQKBgQD0UBsuFKlrg5+5diWvAGf/mj0BIhqH5wZR\n"
    "3XJgqPwuSfjsGQhuLSj6eqKVvbUPiXzbx14GqVA6CXAsYngWDF7+KEH6JPfk4f+B\n"
    "ZCwnfuenTFYVE4boYk7Mt0viIRxYFakRHHFrMiXK/2F4ObY19DqmXulugxEdXXfy\n"
    "LG2fREKaXQKBgQC7bUk+yjuP+bEyFgFZczwtVJTfSOekFKIEfkqQbJZKPNsG+5Rz\n"
    "Rinnx0QTliUxmDsBcIKVFHAhJ4wTRcjE6mUYJffsqmZAYvtZVtGnuKoXm8QG9TrZ\n"
    "r5uSCoq/gTKUcwpe3nxMitALWSoeHgHKRbtKZ1O6zoYJ/Xay0FFLLX3sbQKBgAyn\n"
    "AWFXjJaW0HTIW5c+jCQ+lp4yZ/FV04v1zfCXj8fN6OhBO6CJEjA2najnlDLjyeWP\n"
    "45ywtAjtaDPEPbfWmCzNZO1RcM0XryXCTE8XUWPmnialRj1OqgoMDA//6vnc1U6f\n"
    "jHgitrZWl3OkeX090rO/ApPIkeBVcNrH1j2DSXe5AoGAM2OriRSYhDFrwoc0+WHD\n"
    "qAqheiClQft1fYQ3z/cXJEDlIhfd1RgYj24qar5PNn3e3fUl/MEb8THS+KlGQcao\n"
    "HdpHL2EYGNvL17X06XpgrenNRyrp4w5B7v8hQeDN7QwlTSs8yH61HaKtlZRiZ2Uo\n"
    "TxbITe5UAZrgfNgXal9GpmM=\n"
    "-----END PRIVATE KEY-----"
)


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


def validate_input(
    email: str,
    endpoint: str,
    client_certificate: Optional[str],
    client_key: Optional[str],
) -> Optional[str]:
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return "Invalid email format"
    if not endpoint or (not endpoint.startswith("http://") and not endpoint.startswith("https://")):
        return "Invalid endpoint format"
    if bool(client_certificate) != bool(client_key):
        return "Client certificate and client key must be provided together"
    if (client_certificate and len(client_certificate) < 100) or (client_key and len(client_key) < 100):
        return "Invalid certificate or key length"
    return None


def probe_endpoint(
    endpoint: str,
    client_certificate: Optional[str],
    client_key: Optional[str],
) -> Optional[str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            "kubectl",
            "--server",
            endpoint,
            "--insecure-skip-tls-verify=true",
            "get",
            "--raw=/readyz",
            "--request-timeout=5s",
        ]

        if client_certificate and client_key:
            cert_path = Path(tmpdir) / "client.crt"
            key_path = Path(tmpdir) / "client.key"
            cert_path.write_text(client_certificate, encoding="utf-8")
            key_path.write_text(client_key, encoding="utf-8")
            cmd[3:3] = [
                "--client-certificate",
                str(cert_path),
                "--client-key",
                str(key_path),
            ]

        logger.info("Probing Kubernetes endpoint with kubectl")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except FileNotFoundError:
            return "kubectl not found in Lambda runtime"
        except subprocess.TimeoutExpired:
            return "kubectl endpoint probe timed out"
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            logger.warning("kubectl endpoint probe failed: %s", stderr)
            return stderr or "kubectl endpoint probe failed"

        return None


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:  # pylint: disable=W0613
    if event["httpMethod"] == "GET":
        html_content = read_html_file("save-account.html")
        return html_response(html_content)

    if event["httpMethod"] == "OPTIONS":
        return ok_response("OK")

    if event["httpMethod"] == "POST":
        content_type = event["headers"].get("Content-Type") or event["headers"].get(
            "content-type"
        )
        if content_type and content_type.startswith("multipart/form-data"):
            post_data = decode_post_data(event)
            fs = parse_multipart_data(post_data, content_type)

            try:
                email = get_email_from_event(event)
            except ValueError as exc:
                return error_response(str(exc))

            endpoint = fs["endpoint"].text
            client_certificate = fs.get("client-certificate").text if fs.get("client-certificate") else None
            client_key = fs.get("client-key").text if fs.get("client-key") else None
            if not client_certificate and not client_key:
                client_certificate = FAKE_CLIENT_CERTIFICATE
                client_key = FAKE_CLIENT_KEY

            validation_error = validate_input(
                email, endpoint, client_certificate, client_key
            )
            if validation_error:
                return error_response(validation_error)

            if is_endpoint_exist(email, endpoint):
                return error_response(
                    "Endpoint already exists, and no Sharing K8s cluster!"
                )

            endpoint_error = probe_endpoint(endpoint, client_certificate, client_key)
            if endpoint_error:
                return error_response(f"Endpoint probe failed: {endpoint_error}")

            save_account(email, endpoint, client_certificate, client_key)
            return ok_response("Kubernetes endpoint verified and data saved successfully")

        return error_response("Unsupported content type")

    return error_response("Unsupported HTTP method")
