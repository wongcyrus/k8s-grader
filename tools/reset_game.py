import json

import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")


def get_stack_outputs(stack_name):
    client = boto3.client("cloudformation", region_name="us-east-1")
    response = client.describe_stacks(StackName=stack_name)

    outputs = {}
    for stack in response["Stacks"]:
        for output in stack["Outputs"]:
            outputs[output["OutputKey"]] = output["OutputValue"]

    return outputs


def read_env_template(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def delete_all_items(dynamodb_resource, table_names):
    for table_name in table_names:
        try:
            table = dynamodb_resource.Table(table_name)
            # Retrieve primary key attributes
            key_attrs = [attr["AttributeName"] for attr in table.key_schema]
            # Build projection expression and attribute mapping
            expr_attr_names = {}
            projection_expr_parts = []
            for i, attr in enumerate(key_attrs):
                alias = f"#k{i}"
                expr_attr_names[alias] = attr
                projection_expr_parts.append(alias)
            projection_expr = ", ".join(projection_expr_parts)

            scan = table.scan(
                ProjectionExpression=projection_expr,
                ExpressionAttributeNames=expr_attr_names,
            )

            with table.batch_writer() as batch:
                for each in scan["Items"]:
                    # Build proper key dictionary from the retrieved attributes
                    key = {attr: each[attr] for attr in key_attrs}
                    batch.delete_item(Key=key)
            print(f"Deleted all items in {table_name}")
        except ClientError as e:
            print(f"Error deleting items in {table_name}: {e}")


if __name__ == "__main__":

    output_values = get_stack_outputs("k8s-grader-api-demo")

    game_task_table = output_values["GameTaskTable"]
    session_table = output_values["SessionTable"]
    test_record_table = output_values["TestRecordTable"]
    npc_task_table = output_values["NpcTaskTable"]
    npc_lock_table = output_values["NpcLockTable"]

    all_tables = [
        game_task_table,
        session_table,
        test_record_table,
        npc_task_table,
        npc_lock_table,
    ]

    delete_all_items(dynamodb_resource=dynamodb, table_names=all_tables)
