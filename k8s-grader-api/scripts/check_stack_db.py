#!/usr/bin/env python3
"""Inspect deployed DynamoDB tables resolved from CloudFormation stack outputs."""
from __future__ import annotations

import argparse
from typing import Dict, List

import boto3

TABLE_OUTPUT_KEYS = [
    "AccountTable",
    "ApiKeyTable",
    "TaskStateTable",
    "NpcAssignmentTable",
    "NpcLockTable",
    "NpcBackgroundTable",
    "ConversationTable",
    "TestRecordTable",
    "GameSourceTable",
    "GameAccessTable",
    "ExamCodeTable",
    "ExamSessionTable",
    "ExamWsConnectionTable",
]


def get_stack_outputs(stack_name: str, region: str) -> Dict[str, str]:
    cfn = boto3.client("cloudformation", region_name=region)
    response = cfn.describe_stacks(StackName=stack_name)
    outputs = response["Stacks"][0].get("Outputs", [])
    return {output["OutputKey"]: output["OutputValue"] for output in outputs}


def describe_tables(stack_name: str, region: str) -> List[Dict[str, str]]:
    outputs = get_stack_outputs(stack_name, region)
    ddb = boto3.client("dynamodb", region_name=region)
    rows: List[Dict[str, str]] = []

    for output_key in TABLE_OUTPUT_KEYS:
        table_name = outputs.get(output_key, "")
        if not table_name:
            rows.append(
                {
                    "output_key": output_key,
                    "table_name": "<missing output>",
                    "status": "MISSING",
                    "items": "-",
                    "keys": "-",
                }
            )
            continue

        description = ddb.describe_table(TableName=table_name)["Table"]
        key_schema = ", ".join(
            f"{entry['AttributeName']}:{entry['KeyType']}" for entry in description.get("KeySchema", [])
        )
        rows.append(
            {
                "output_key": output_key,
                "table_name": table_name,
                "status": description.get("TableStatus", "UNKNOWN"),
                "items": str(description.get("ItemCount", 0)),
                "keys": key_schema or "-",
            }
        )

    return rows


def print_table(rows: List[Dict[str, str]]) -> None:
    headers = ["OutputKey", "TableName", "Status", "Items", "Keys"]
    widths = {
        "OutputKey": max(len("OutputKey"), *(len(row["output_key"]) for row in rows)),
        "TableName": max(len("TableName"), *(len(row["table_name"]) for row in rows)),
        "Status": max(len("Status"), *(len(row["status"]) for row in rows)),
        "Items": max(len("Items"), *(len(row["items"]) for row in rows)),
        "Keys": max(len("Keys"), *(len(row["keys"]) for row in rows)),
    }

    def line(values: List[str]) -> str:
        return " | ".join(value.ljust(widths[header]) for value, header in zip(values, headers))

    print(line(headers))
    print("-+-".join("-" * widths[header] for header in headers))
    for row in rows:
        print(
            line(
                [
                    row["output_key"],
                    row["table_name"],
                    row["status"],
                    row["items"],
                    row["keys"],
                ]
            )
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Describe stack-backed DynamoDB tables.")
    parser.add_argument("--stack-name", default="k8s-grader-api-dev")
    parser.add_argument("--region", default="us-east-1")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = describe_tables(args.stack_name, args.region)
    print_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
