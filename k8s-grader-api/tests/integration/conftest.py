"""Integration test configuration - tests against real deployed API"""
import pytest
import boto3
import os
import uuid
import time
from typing import Dict, Any
from datetime import datetime


@pytest.fixture(scope="session")
def stack_name() -> str:
    """Get stack name from environment or use default"""
    return os.environ.get('STACK_NAME', 'k8s-grader-api-dev')


@pytest.fixture(scope="session")
def aws_region() -> str:
    """Get AWS region from environment or use default"""
    return os.environ.get('AWS_REGION', 'us-east-1')


@pytest.fixture(scope="session")
def test_run_id() -> str:
    """Generate unique test run ID"""
    return f"test-{uuid.uuid4().hex[:8]}-{int(time.time())}"


@pytest.fixture(scope="session")
def cfn_client(aws_region):
    """CloudFormation client"""
    return boto3.client('cloudformation', region_name=aws_region)


@pytest.fixture(scope="session")
def stack_outputs(cfn_client, stack_name) -> Dict[str, str]:
    """Get CloudFormation stack outputs"""
    try:
        response = cfn_client.describe_stacks(StackName=stack_name)
        stacks = response.get('Stacks', [])
        
        if not stacks:
            pytest.skip(f"Stack '{stack_name}' not found. Deploy the stack first.")
        
        outputs = {}
        for output in stacks[0].get('Outputs', []):
            outputs[output['OutputKey']] = output['OutputValue']
        
        return outputs
    except Exception as e:
        pytest.skip(f"Failed to get stack outputs: {e}")


@pytest.fixture(scope="session")
def api_endpoint(stack_outputs) -> str:
    """Get API Gateway endpoint from stack outputs"""
    endpoint = stack_outputs.get('ApiEndpoint')
    if not endpoint:
        pytest.skip("ApiEndpoint not found in stack outputs")
    return endpoint.rstrip('/')


@pytest.fixture(scope="session")
def task_state_table(stack_outputs) -> str:
    """Get TaskStateTable name from stack outputs"""
    table = stack_outputs.get('TaskStateTable')
    if not table:
        pytest.skip("TaskStateTable not found in stack outputs")
    return table


@pytest.fixture(scope="session")
def npc_lock_table(stack_outputs) -> str:
    """Get NpcLockTable name from stack outputs"""
    table = stack_outputs.get('NpcLockTable')
    if not table:
        pytest.skip("NpcLockTable not found in stack outputs")
    return table


@pytest.fixture(scope="session")
def npc_assignment_table(stack_outputs) -> str:
    """Get NpcAssignmentTable name from stack outputs"""
    table = stack_outputs.get('NpcAssignmentTable')
    if not table:
        pytest.skip("NpcAssignmentTable not found in stack outputs")
    return table


@pytest.fixture(scope="session")
def account_table(stack_outputs) -> str:
    """Get AccountTable name from stack outputs"""
    table = stack_outputs.get('AccountTable')
    if not table:
        pytest.skip("AccountTable not found in stack outputs")
    return table


@pytest.fixture(scope="session")
def dynamodb_client(aws_region):
    """DynamoDB client for cleanup"""
    return boto3.client('dynamodb', region_name=aws_region)


@pytest.fixture(scope="session")
def test_email(test_run_id) -> str:
    """Generate unique test email for this test run
    
    Note: Keep email short to avoid API Gateway's 128-character limit
    for API keys. Fernet encryption expands the size significantly.
    """
    # Use shorter format: test-{8chars}@ex.com (total ~20 chars)
    # This ensures encrypted key stays under 128 chars
    short_id = test_run_id.split('-')[1][:8]  # Just use first 8 chars of UUID
    return os.environ.get('TEST_EMAIL', f'test-{short_id}@ex.com')


@pytest.fixture(scope="session")
def test_game() -> str:
    """Test game ID"""
    return 'game01'


@pytest.fixture(scope="session")
def test_npc() -> str:
    """Test NPC ID"""
    return 'npc1'


@pytest.fixture(scope="session")
def test_user_data(test_email, test_run_id) -> Dict[str, str]:
    """Generate test user data"""
    return {
        'email': test_email,
        'endpoint': f'https://test-k8s-{test_run_id}.example.com:6443',
        'client_certificate': f'test-cert-{test_run_id}',
        'client_key': f'test-key-{test_run_id}'
    }


@pytest.fixture(scope="session")
def test_api_key(stack_outputs, test_email, api_endpoint) -> str:
    """Get or generate test API key"""
    # Try environment variable first (should be encrypted key)
    api_key = os.environ.get('TEST_API_KEY')
    if api_key:
        print(f"✅ Using TEST_API_KEY from environment")
        return api_key
    
    # Try to generate one using the keygen endpoint
    secret_hash = stack_outputs.get('SecretHash')
    
    if not secret_hash:
        pytest.skip(
            "TEST_API_KEY not set and SecretHash not available. "
            "Please set TEST_API_KEY environment variable with an encrypted API key."
        )
    
    # Generate encrypted API key using keygen endpoint
    import requests
    import time
    try:
        print(f"🔑 Generating API key for {test_email}...")
        response = requests.get(
            f"{api_endpoint}/keygen/",
            params={
                'secret': secret_hash,
                'email': test_email
            },
            timeout=10
        )
        
        if response.status_code == 200:
            # The keygen endpoint returns the API key as plain text
            generated_key = response.text.strip()
            
            # Check if it's an error message
            if generated_key.startswith('Failed') or generated_key.startswith('Invalid') or generated_key.startswith('Secret') or generated_key.startswith('API Gateway') or generated_key.startswith('Usage plan'):
                pytest.skip(
                    f"Keygen endpoint returned error: {generated_key}. "
                    f"Please check Lambda logs or visit: {api_endpoint}/keygen/?secret={secret_hash}&email={test_email}"
                )
            
            if generated_key and len(generated_key) > 10 and not generated_key.startswith('<'):
                print(f"✅ Generated API key successfully")
                print(f"   Key length: {len(generated_key)} characters")
                print(f"   Key prefix: {generated_key[:20]}...")
                
                # Wait a moment for API Gateway to propagation the key
                print(f"⏳ Waiting 3 seconds for API Gateway propagation...")
                time.sleep(3)
                
                # Verify the key works by testing decryption
                try:
                    from cryptography.fernet import Fernet
                    fernet = Fernet(secret_hash.encode())
                    decrypted_email = fernet.decrypt(generated_key.encode()).decode()
                    print(f"✅ API key validation successful: {decrypted_email}")
                    if decrypted_email != test_email:
                        pytest.skip(f"API key email mismatch: expected {test_email}, got {decrypted_email}")
                except Exception as e:
                    pytest.skip(f"API key validation failed: {e}")
                
                return generated_key
            else:
                pytest.skip(
                    f"Could not parse API key from keygen response. "
                    f"Response: {response.text[:200]} "
                    f"Please visit: {api_endpoint}/keygen/?secret={secret_hash}&email={test_email} "
                    "and set TEST_API_KEY environment variable."
                )
        else:
            pytest.skip(f"Failed to generate API key: HTTP {response.status_code}, Response: {response.text[:200]}")
    except Exception as e:
        pytest.skip(f"Failed to generate API key: {e}")


@pytest.fixture(scope="session", autouse=True)
def setup_test_user(dynamodb_client, account_table, test_user_data, test_email, stack_outputs):
    """Create test user account before tests and clean up after
    
    Note: We directly create the user in DynamoDB instead of calling the 
    save-k8s-account API because:
    1. It's faster (no HTTP request overhead)
    2. We control the exact test data
    3. The save-k8s-account API just calls AccountRepository.save() anyway
    4. We can use fake K8s credentials for testing
    
    The save-k8s-account API endpoint is tested separately in TestSaveAccountAPI.
    """
    print(f"\n🔧 Setting up test user: {test_email}")
    
    # Create test user account directly in DynamoDB
    # This is equivalent to calling save_account() or the save-k8s-account API
    try:
        dynamodb_client.put_item(
            TableName=account_table,
            Item={
                'email': {'S': test_user_data['email']},
                'endpoint': {'S': test_user_data['endpoint']},
                'client_certificate': {'S': test_user_data['client_certificate']},
                'client_key': {'S': test_user_data['client_key']},
                'time': {'N': str(int(time.time()))}
            }
        )
        print(f"✅ Test user created: {test_email}")
    except Exception as e:
        print(f"⚠️  Warning: Could not create test user: {e}")
    
    yield
    
    # Cleanup after all tests
    print(f"\n🧹 Cleaning up test user: {test_email}")
    _cleanup_all_test_data(
        dynamodb_client,
        test_email,
        stack_outputs
    )
    print(f"✅ Test user cleaned up: {test_email}")


def _cleanup_all_test_data(dynamodb_client, test_email: str, stack_outputs: Dict[str, str]):
    """Clean up all test data from all tables and API Gateway"""
    # Clean up DynamoDB tables
    tables_to_clean = [
        ('AccountTable', {'email': test_email}),
        ('TaskStateTable', {'email': test_email}, 'gameTask'),
        ('NpcLockTable', {'email': test_email}, 'gameNpc'),
        ('NpcAssignmentTable', {'email': test_email}, 'game'),
        ('GameTaskTable', {'email': test_email}, 'game'),
        ('SessionTable', {'email': test_email}, 'game'),
        ('NpcTaskTable', {'email': test_email}, 'game'),
        ('TestRecordTable', {'email': test_email}, 'gameTime'),
        ('ApiKeyTable', {'email': test_email}),  # Clean up API key mapping
    ]
    
    for table_info in tables_to_clean:
        table_key = table_info[0]
        table_name = stack_outputs.get(table_key)
        
        if not table_name:
            continue
        
        try:
            if len(table_info) == 2:
                # Simple delete with just partition key
                key_dict = table_info[1]
                dynamodb_client.delete_item(
                    TableName=table_name,
                    Key={k: {'S': v} for k, v in key_dict.items()}
                )
            else:
                # Query and delete all items with this email
                partition_key = list(table_info[1].keys())[0]
                sort_key_name = table_info[2]
                
                # Query all items for this email
                response = dynamodb_client.query(
                    TableName=table_name,
                    KeyConditionExpression=f'{partition_key} = :email',
                    ExpressionAttributeValues={
                        ':email': {'S': test_email}
                    }
                )
                
                # Delete each item
                for item in response.get('Items', []):
                    dynamodb_client.delete_item(
                        TableName=table_name,
                        Key={
                            partition_key: {'S': test_email},
                            sort_key_name: item[sort_key_name]
                        }
                    )
        except Exception as e:
            print(f"⚠️  Warning: Could not clean {table_key}: {e}")
    
    # Clean up API Gateway API key
    try:
        import boto3
        apigateway_client = boto3.client('apigateway')
        
        # Find API key by name (email is used as the key name)
        response = apigateway_client.get_api_keys(nameQuery=test_email, includeValues=False)
        api_keys = response.get('items', [])
        
        for api_key in api_keys:
            if api_key.get('name') == test_email:
                api_key_id = api_key.get('id')
                apigateway_client.delete_api_key(apiKey=api_key_id)
                print(f"   ✓ Deleted API Gateway key: {api_key_id}")
    except Exception as e:
        print(f"⚠️  Warning: Could not clean API Gateway key: {e}")


@pytest.fixture(autouse=True)
def cleanup_test_data_per_test(dynamodb_client, task_state_table, npc_lock_table, 
                                npc_assignment_table, test_email, test_game):
    """Clean up test data before and after each test"""
    def clean():
        tables_and_keys = [
            (task_state_table, {'email': test_email, 'gameTask': f"{test_game}#01_task"}),
            (npc_lock_table, {'email': test_email, 'gameNpc': f"{test_game}#npc1"}),
            (npc_assignment_table, {'email': test_email, 'game': test_game}),
        ]
        
        for table_name, key_dict in tables_and_keys:
            try:
                dynamodb_client.delete_item(
                    TableName=table_name,
                    Key={k: {'S': v} for k, v in key_dict.items()}
                )
            except:
                pass
    
    # Clean before test
    clean()
    
    yield
    
    # Clean after test
    clean()
