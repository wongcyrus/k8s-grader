#!/usr/bin/env python3
"""
Reset game state by clearing DynamoDB tables.

Usage:
    python reset_game.py [stack-name] [--region REGION] [--email EMAIL] [--game GAME]

Examples:
    # Reset all data for all users in default stack
    python reset_game.py

    # Reset specific stack
    python reset_game.py k8s-grader-api-prod

    # Reset specific user's data
    python reset_game.py --email user@example.com

    # Reset specific game for specific user
    python reset_game.py --email user@example.com --game game01
"""

import argparse
import sys
import boto3
from botocore.exceptions import ClientError


def get_stack_outputs(stack_name, region="us-east-1"):
    """Get CloudFormation stack outputs."""
    try:
        client = boto3.client("cloudformation", region_name=region)
        response = client.describe_stacks(StackName=stack_name)

        outputs = {}
        for stack in response["Stacks"]:
            for output in stack["Outputs"]:
                outputs[output["OutputKey"]] = output["OutputValue"]

        return outputs
    except ClientError as e:
        print(f"❌ Error getting stack outputs: {e}")
        sys.exit(1)


def delete_all_items(dynamodb_resource, table_name, filter_key=None, filter_value=None):
    """Delete all items from a table, optionally filtered by a key."""
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

        # Scan with optional filter
        scan_kwargs = {
            "ProjectionExpression": projection_expr,
            "ExpressionAttributeNames": expr_attr_names,
        }
        
        if filter_key and filter_value:
            scan_kwargs["FilterExpression"] = f"#{filter_key} = :{filter_key}"
            scan_kwargs["ExpressionAttributeNames"][f"#{filter_key}"] = filter_key
            scan_kwargs["ExpressionAttributeValues"] = {f":{filter_key}": filter_value}

        deleted_count = 0
        while True:
            scan = table.scan(**scan_kwargs)
            
            with table.batch_writer() as batch:
                for each in scan["Items"]:
                    # Build proper key dictionary from the retrieved attributes
                    key = {attr: each[attr] for attr in key_attrs}
                    batch.delete_item(Key=key)
                    deleted_count += 1
            
            # Check if there are more items to scan
            if "LastEvaluatedKey" not in scan:
                break
            scan_kwargs["ExclusiveStartKey"] = scan["LastEvaluatedKey"]
        
        if deleted_count > 0:
            print(f"  ✅ Deleted {deleted_count} items from {table_name}")
        else:
            print(f"  ℹ️  No items to delete in {table_name}")
            
    except ClientError as e:
        print(f"  ❌ Error deleting items in {table_name}: {e}")


def reset_game(stack_name="k8s-grader-api-dev", region="us-east-1", email=None, game=None):
    """Reset game state by clearing relevant DynamoDB tables."""
    
    print(f"\n🎮 K8s Grader - Reset Game State")
    print(f"{'=' * 50}")
    print(f"Stack: {stack_name}")
    print(f"Region: {region}")
    if email:
        print(f"Email filter: {email}")
    if game:
        print(f"Game filter: {game}")
    print()

    # Get stack outputs
    print("📋 Getting stack outputs...")
    output_values = get_stack_outputs(stack_name, region)
    
    dynamodb = boto3.resource("dynamodb", region_name=region)

    # New refactored tables
    task_state_table = output_values.get("TaskStateTable")
    npc_assignment_table = output_values.get("NpcAssignmentTable")
    npc_lock_table = output_values.get("NpcLockTable")
    test_record_table = output_values.get("TestRecordTable")

    if not all([task_state_table, npc_assignment_table, npc_lock_table, test_record_table]):
        print("❌ Error: Could not find all required table names in stack outputs")
        print("Available outputs:", list(output_values.keys()))
        sys.exit(1)

    print(f"✅ Found tables:")
    print(f"  - TaskStateTable: {task_state_table}")
    print(f"  - NpcAssignmentTable: {npc_assignment_table}")
    print(f"  - NpcLockTable: {npc_lock_table}")
    print(f"  - TestRecordTable: {test_record_table}")
    print()

    # Confirm deletion
    if not email and not game:
        confirm = input("⚠️  This will delete ALL game state for ALL users. Continue? (yes/no): ")
        if confirm.lower() != "yes":
            print("❌ Aborted")
            sys.exit(0)
    
    print("\n🗑️  Deleting items...")
    
    # Delete from TaskStateTable (filtered by email if provided)
    if email:
        delete_all_items(dynamodb, task_state_table, filter_key="email", filter_value=email)
    else:
        delete_all_items(dynamodb, task_state_table)
    
    # Delete from NpcAssignmentTable (filtered by email if provided)
    if email:
        delete_all_items(dynamodb, npc_assignment_table, filter_key="email", filter_value=email)
    else:
        delete_all_items(dynamodb, npc_assignment_table)
    
    # Delete from NpcLockTable (filtered by email if provided)
    if email:
        delete_all_items(dynamodb, npc_lock_table, filter_key="email", filter_value=email)
    else:
        delete_all_items(dynamodb, npc_lock_table)
    
    # Delete from TestRecordTable (filtered by email if provided)
    if email:
        delete_all_items(dynamodb, test_record_table, filter_key="email", filter_value=email)
    else:
        delete_all_items(dynamodb, test_record_table)

    print("\n✅ Reset complete!")
    print("\nNote: User accounts (AccountTable) and API keys (ApiKeyTable) were NOT deleted.")
    print("Users can continue using their existing credentials.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Reset K8s Grader game state by clearing DynamoDB tables",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Reset all data for all users in default stack
  python reset_game.py

  # Reset specific stack
  python reset_game.py k8s-grader-api-prod

  # Reset specific user's data
  python reset_game.py --email user@example.com

  # Reset with custom region
  python reset_game.py --region us-west-2
        """
    )
    
    parser.add_argument(
        "stack_name",
        nargs="?",
        default="k8s-grader-api-dev",
        help="CloudFormation stack name (default: k8s-grader-api-dev)"
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region (default: us-east-1)"
    )
    parser.add_argument(
        "--email",
        help="Filter by user email (only reset this user's data)"
    )
    parser.add_argument(
        "--game",
        help="Filter by game (only reset this game's data - requires --email)"
    )
    
    args = parser.parse_args()
    
    if args.game and not args.email:
        print("❌ Error: --game requires --email to be specified")
        sys.exit(1)
    
    reset_game(
        stack_name=args.stack_name,
        region=args.region,
        email=args.email,
        game=args.game
    )
