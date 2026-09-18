#!/usr/bin/env python3
"""Generate student API keys from a text file of email addresses."""

import argparse
import csv
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import boto3
from botocore.exceptions import ClientError


EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
KEYGEN_ERRORS = (
    "Secret and email parameter is missing.",
    "Invalid secret",
    "Invalid email address.",
    "API Gateway API not found.",
    "Failed to create API key.",
    "Usage plan not found.",
    "Failed to associate API key with usage plan.",
    "Failed to retrieve API key value.",
)


def read_emails(path: Path) -> List[str]:
    """Read unique email addresses, ignoring blank and comment lines."""
    emails: List[str] = []
    seen = set()
    invalid_lines = []

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError(f"Could not read email file {path}: {error}") from error

    for line_number, raw_line in enumerate(lines, start=1):
        email = raw_line.strip()
        if not email or email.startswith("#"):
            continue
        if not EMAIL_PATTERN.fullmatch(email):
            invalid_lines.append(f"line {line_number}: {email}")
            continue
        if email not in seen:
            emails.append(email)
            seen.add(email)

    if invalid_lines:
        raise ValueError("Invalid email address(es):\n  " + "\n  ".join(invalid_lines))
    if not emails:
        raise ValueError("The email file contains no email addresses.")
    return emails


def get_stack_configuration(stack_name: str, region: str) -> Tuple[str, str]:
    """Get the deployed REST URL and key-generation secret."""
    try:
        response = boto3.client("cloudformation", region_name=region).describe_stacks(
            StackName=stack_name
        )
    except ClientError as error:
        raise ValueError(f"Could not read CloudFormation stack {stack_name}: {error}") from error

    stack = response["Stacks"][0]
    outputs: Dict[str, str] = {
        output["OutputKey"]: output["OutputValue"] for output in stack.get("Outputs", [])
    }
    parameters: Dict[str, str] = {
        parameter["ParameterKey"]: parameter["ParameterValue"]
        for parameter in stack.get("Parameters", [])
    }
    base_url = outputs.get("BaseUrl")
    secret_hash = outputs.get("SecretHash") or parameters.get("SecretHash")

    if not base_url:
        raise ValueError(f"Stack {stack_name} does not have a BaseUrl output.")
    if not secret_hash:
        raise ValueError(f"Stack {stack_name} does not expose a SecretHash value.")
    return base_url, secret_hash


def generate_api_key(base_url: str, secret_hash: str, email: str) -> str:
    """Request an existing or new API key from the deployed keygen endpoint."""
    endpoint = f"{base_url.rstrip('/')}/keygen/?{urlencode({'secret': secret_hash, 'email': email})}"
    try:
        with urlopen(endpoint, timeout=30) as response:
            result = response.read().decode("utf-8").strip()
    except HTTPError as error:
        raise ValueError(f"HTTP {error.code}") from error
    except URLError as error:
        raise ValueError(f"Request failed: {error.reason}") from error

    if not result or result.startswith(KEYGEN_ERRORS):
        raise ValueError(result or "Empty response")
    return result


def write_keys(path: Path, keys: List[Tuple[str, str]]) -> None:
    """Write keys atomically and restrict the resulting file to its owner."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)
        writer = csv.writer(temporary_file)
        writer.writerow(["email", "api_key"])
        writer.writerows(keys)

    os.chmod(temporary_path, 0o600)
    temporary_path.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate API keys for emails listed one per line in a text file."
    )
    parser.add_argument("email_file", type=Path, help="Text file containing one email per line")
    parser.add_argument(
        "--output", required=True, type=Path, help="CSV file to receive email and API-key pairs"
    )
    parser.add_argument(
        "--stack-name", default="k8s-grader-api-dev", help="CloudFormation stack name"
    )
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    args = parser.parse_args()

    try:
        emails = read_emails(args.email_file)
        base_url, secret_hash = get_stack_configuration(args.stack_name, args.region)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    keys = []
    failures = []
    for email in emails:
        try:
            keys.append((email, generate_api_key(base_url, secret_hash, email)))
        except ValueError as error:
            failures.append((email, str(error)))

    if keys:
        write_keys(args.output, keys)
        print(f"Wrote {len(keys)} API key(s) to {args.output}.")
    if failures:
        print(f"Failed to generate {len(failures)} API key(s):", file=sys.stderr)
        for email, error in failures:
            print(f"  {email}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
