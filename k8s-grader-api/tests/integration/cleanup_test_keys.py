#!/usr/bin/env python3
"""
Cleanup script to remove all test API keys from API Gateway and DynamoDB.
Use this to clean up any leftover test keys from previous test runs.
"""
import boto3
import sys
from typing import List, Dict, Any


def get_all_test_api_keys(apigateway_client) -> List[Dict[str, Any]]:
    """Get all API keys that match test pattern"""
    print("🔍 Searching for test API keys...")
    
    all_keys = []
    position = None
    
    while True:
        if position:
            response = apigateway_client.get_api_keys(
                nameQuery='integration-test-',
                includeValues=False,
                position=position
            )
        else:
            response = apigateway_client.get_api_keys(
                nameQuery='integration-test-',
                includeValues=False
            )
        
        items = response.get('items', [])
        all_keys.extend(items)
        
        position = response.get('position')
        if not position:
            break
    
    return all_keys


def delete_api_gateway_keys(apigateway_client, dry_run=False):
    """Delete all test API keys from API Gateway"""
    test_keys = get_all_test_api_keys(apigateway_client)
    
    if not test_keys:
        print("✅ No test API keys found in API Gateway")
        return 0
    
    print(f"📋 Found {len(test_keys)} test API keys in API Gateway:")
    for key in test_keys:
        print(f"   • {key.get('name')} (ID: {key.get('id')})")
    
    if dry_run:
        print("\n🔍 DRY RUN - No keys will be deleted")
        return len(test_keys)
    
    print(f"\n🗑️  Deleting {len(test_keys)} API keys...")
    deleted = 0
    
    for key in test_keys:
        try:
            apigateway_client.delete_api_key(apiKey=key.get('id'))
            print(f"   ✓ Deleted: {key.get('name')}")
            deleted += 1
        except Exception as e:
            print(f"   ✗ Failed to delete {key.get('name')}: {e}")
    
    return deleted


def get_test_emails_from_dynamodb(dynamodb_client, table_name: str) -> List[str]:
    """Get all test emails from DynamoDB"""
    try:
        response = dynamodb_client.scan(
            TableName=table_name,
            FilterExpression='begins_with(email, :prefix)',
            ExpressionAttributeValues={
                ':prefix': {'S': 'integration-test-'}
            }
        )
        
        items = response.get('Items', [])
        emails = [item['email']['S'] for item in items]
        return emails
    except Exception as e:
        print(f"⚠️  Warning: Could not scan {table_name}: {e}")
        return []


def cleanup_dynamodb_tables(dynamodb_client, stack_name: str, dry_run=False):
    """Clean up test data from all DynamoDB tables"""
    print("\n🔍 Searching for test data in DynamoDB...")
    
    # Get stack outputs to find table names
    cfn_client = boto3.client('cloudformation')
    try:
        response = cfn_client.describe_stacks(StackName=stack_name)
        stacks = response.get('Stacks', [])
        if not stacks:
            print(f"❌ Stack '{stack_name}' not found")
            return 0
        
        outputs = {}
        for output in stacks[0].get('Outputs', []):
            outputs[output['OutputKey']] = output['OutputValue']
    except Exception as e:
        print(f"❌ Failed to get stack outputs: {e}")
        return 0
    
    # Get all test emails from AccountTable
    account_table = outputs.get('AccountTable')
    if not account_table:
        print("⚠️  AccountTable not found in stack outputs")
        return 0
    
    test_emails = get_test_emails_from_dynamodb(dynamodb_client, account_table)
    
    if not test_emails:
        print("✅ No test users found in DynamoDB")
        return 0
    
    print(f"📋 Found {len(test_emails)} test users:")
    for email in test_emails:
        print(f"   • {email}")
    
    if dry_run:
        print("\n🔍 DRY RUN - No data will be deleted")
        return len(test_emails)
    
    # Clean up each test user
    print(f"\n🗑️  Cleaning up {len(test_emails)} test users...")
    
    tables_to_clean = [
        ('AccountTable', 'email'),
        ('ApiKeyTable', 'email'),
    ]
    
    cleaned = 0
    for email in test_emails:
        print(f"\n   Cleaning: {email}")
        
        for table_key, partition_key in tables_to_clean:
            table_name = outputs.get(table_key)
            if not table_name:
                continue
            
            try:
                dynamodb_client.delete_item(
                    TableName=table_name,
                    Key={partition_key: {'S': email}}
                )
                print(f"      ✓ Cleaned {table_key}")
            except dynamodb_client.exceptions.ResourceNotFoundException:
                pass  # Item doesn't exist, that's fine
            except Exception as e:
                print(f"      ✗ Failed to clean {table_key}: {e}")
        
        cleaned += 1
    
    return cleaned


def main():
    """Main cleanup function"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Clean up test API keys and data from integration tests'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be deleted without actually deleting'
    )
    parser.add_argument(
        '--stack-name',
        default='k8s-grader-api-dev',
        help='CloudFormation stack name (default: k8s-grader-api-dev)'
    )
    parser.add_argument(
        '--region',
        default='us-east-1',
        help='AWS region (default: us-east-1)'
    )
    parser.add_argument(
        '--api-gateway-only',
        action='store_true',
        help='Only clean up API Gateway keys'
    )
    parser.add_argument(
        '--dynamodb-only',
        action='store_true',
        help='Only clean up DynamoDB data'
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("TEST DATA CLEANUP")
    print("=" * 70)
    print()
    print(f"Stack Name: {args.stack_name}")
    print(f"Region: {args.region}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()
    
    if args.dry_run:
        print("⚠️  DRY RUN MODE - No data will be deleted")
        print()
    
    # Initialize clients
    apigateway_client = boto3.client('apigateway', region_name=args.region)
    dynamodb_client = boto3.client('dynamodb', region_name=args.region)
    
    total_cleaned = 0
    
    # Clean API Gateway
    if not args.dynamodb_only:
        api_keys_deleted = delete_api_gateway_keys(apigateway_client, args.dry_run)
        total_cleaned += api_keys_deleted
    
    # Clean DynamoDB
    if not args.api_gateway_only:
        users_cleaned = cleanup_dynamodb_tables(
            dynamodb_client,
            args.stack_name,
            args.dry_run
        )
        total_cleaned += users_cleaned
    
    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    if args.dry_run:
        print(f"🔍 DRY RUN: Would clean up {total_cleaned} items")
        print()
        print("To actually delete, run without --dry-run:")
        print(f"  python {sys.argv[0]}")
    else:
        print(f"✅ Cleaned up {total_cleaned} items")
        print()
        print("All test data has been removed!")
    
    print()


if __name__ == '__main__':
    main()
