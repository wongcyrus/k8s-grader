"""Integration test configuration - tests against real deployed API"""
import pytest
import boto3
import os
from typing import Dict, Any, Optional


@pytest.fixture(scope="session")
def stack_name() -> str:
    """Get stack name from environment or use default"""
    return os.environ.get('STACK_NAME', 'k8s-grader-api-dev')


@pytest.fixture(scope="session")
def aws_region() -> str:
    """Get AWS region from environment or use default"""
    return os.environ.get('AWS_REGION', 'us-east-1')


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
def dynamodb_client(aws_region):
    """DynamoDB client for cleanup"""
    return boto3.client('dynamodb', region_name=aws_region)


@pytest.fixture(scope="session")
def test_api_key(stack_outputs, test_email) -> str:
    """Get test API key - must be encrypted with email"""
    # For integration tests, we need an ENCRYPTED API key that contains the email
    # The TestApiKey from stack outputs is just an API Gateway key ID, not encrypted
    
    # Try environment variable first (should be encrypted key)
    api_key = os.environ.get('TEST_API_KEY')
    if api_key:
        return api_key
    
    # If not set, we need to generate one using the keygen endpoint
    # This requires SECRET_HASH from stack outputs
    secret_hash = stack_outputs.get('SecretHash')
    api_endpoint = stack_outputs.get('ApiEndpoint')
    
    if not secret_hash or not api_endpoint:
        pytest.skip(
            "TEST_API_KEY not set and cannot auto-generate. "
            "Please set TEST_API_KEY environment variable with an encrypted API key. "
            "Generate one using: {api_endpoint}/keygen/?secret={secret_hash}&email={test_email}"
        )
    
    # Generate encrypted API key using keygen endpoint
    import requests
    try:
        response = requests.get(
            f"{api_endpoint}/keygen/",
            params={
                'secret': secret_hash,
                'email': test_email
            },
            timeout=10
        )
        
        if response.status_code == 200:
            # Extract API key from HTML response
            html = response.text
            # The keygen endpoint returns HTML with the API key
            # We need to parse it or use a different approach
            pytest.skip(
                "Cannot auto-generate encrypted API key. "
                f"Please visit: {api_endpoint}/keygen/?secret={secret_hash}&email={test_email} "
                "and set TEST_API_KEY environment variable with the generated key."
            )
        else:
            pytest.skip(f"Failed to generate API key: HTTP {response.status_code}")
    except Exception as e:
        pytest.skip(f"Failed to generate API key: {e}")


@pytest.fixture(scope="session")
def test_email() -> str:
    """Test email for integration tests"""
    return os.environ.get('TEST_EMAIL', 'integration-test@example.com')


@pytest.fixture(scope="session")
def test_game() -> str:
    """Test game ID"""
    return 'game01'


@pytest.fixture(scope="session")
def test_npc() -> str:
    """Test NPC ID"""
    return 'npc1'


@pytest.fixture(autouse=True)
def cleanup_test_data(dynamodb_client, task_state_table, npc_lock_table, 
                      npc_assignment_table, test_email, test_game):
    """Clean up test data before and after each test"""
    def clean():
        try:
            # Clean TaskStateTable
            dynamodb_client.delete_item(
                TableName=task_state_table,
                Key={
                    'email': {'S': test_email},
                    'gameTask': {'S': f"{test_game}#01_task"}
                }
            )
        except:
            pass
        
        try:
            # Clean NpcLockTable
            dynamodb_client.delete_item(
                TableName=npc_lock_table,
                Key={
                    'email': {'S': test_email},
                    'gameNpc': {'S': f"{test_game}#npc1"}
                }
            )
        except:
            pass
        
        try:
            # Clean NpcAssignmentTable
            dynamodb_client.delete_item(
                TableName=npc_assignment_table,
                Key={
                    'email': {'S': test_email},
                    'game': {'S': test_game}
                }
            )
        except:
            pass
    
    # Clean before test
    clean()
    
    yield
    
    # Clean after test
    clean()
