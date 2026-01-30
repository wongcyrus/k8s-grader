"""Pytest configuration and fixtures"""
import pytest
import sys
import os
from moto import mock_aws
import boto3

# Add common layer to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'common-layer'))

from common.models.phase_config import PhaseConfig
from common.models.task_manifest import TaskManifest
from common.models.task_state import TaskState, TaskStatus, PhaseStatus
from common.status import TestResult


@pytest.fixture
def aws_credentials(monkeypatch):
    """Mock AWS credentials"""
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    monkeypatch.setenv('AWS_SECURITY_TOKEN', 'testing')
    monkeypatch.setenv('AWS_SESSION_TOKEN', 'testing')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    monkeypatch.setenv('TaskStateTable', 'TaskStateTable')
    monkeypatch.setenv('NpcLockTable', 'NpcLockTable')
    monkeypatch.setenv('NpcAssignmentTable', 'NpcAssignmentTable')
    # Add SECRET_HASH for handler tests
    monkeypatch.setenv('SecretHash', '2M540grRh05JjA0N0f3ptfGqSq-AN6v1zym1rKEIk-g=')


@pytest.fixture
def dynamodb_tables(aws_credentials):
    """Create mock DynamoDB tables"""
    with mock_aws():
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        
        # Create TaskStateTable
        task_table = dynamodb.create_table(
            TableName='TaskStateTable',
            KeySchema=[
                {'AttributeName': 'email', 'KeyType': 'HASH'},
                {'AttributeName': 'gameTask', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'email', 'AttributeType': 'S'},
                {'AttributeName': 'gameTask', 'AttributeType': 'S'},
                {'AttributeName': 'status', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[{
                'IndexName': 'StatusIndex',
                'KeySchema': [
                    {'AttributeName': 'email', 'KeyType': 'HASH'},
                    {'AttributeName': 'status', 'KeyType': 'RANGE'}
                ],
                'Projection': {'ProjectionType': 'ALL'}
            }],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Create NpcLockTable
        lock_table = dynamodb.create_table(
            TableName='NpcLockTable',
            KeySchema=[
                {'AttributeName': 'email', 'KeyType': 'HASH'},
                {'AttributeName': 'gameNpc', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'email', 'AttributeType': 'S'},
                {'AttributeName': 'gameNpc', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Create NpcAssignmentTable
        assignment_table = dynamodb.create_table(
            TableName='NpcAssignmentTable',
            KeySchema=[
                {'AttributeName': 'email', 'KeyType': 'HASH'},
                {'AttributeName': 'game', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'email', 'AttributeType': 'S'},
                {'AttributeName': 'game', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        yield {
            'task_table': task_table,
            'lock_table': lock_table,
            'assignment_table': assignment_table
        }


@pytest.fixture
def sample_phase_config():
    """Sample phase configuration"""
    return PhaseConfig(
        id="setup",
        name="Setup",
        description="Initialize the task environment",
        test_file="test_01_setup.py",
        required=True,
        auto_run=False,
        timeout_seconds=30,
        max_attempts=3,
        points=0
    )


@pytest.fixture
def sample_phases():
    """Sample list of phases"""
    return [
        PhaseConfig(
            id="setup",
            name="Setup",
            description="Initialize environment",
            test_file="test_01_setup.py",
            required=True,
            auto_run=False,
            timeout_seconds=30,
            max_attempts=3,
            points=0
        ),
        PhaseConfig(
            id="challenge",
            name="Challenge",
            description="Complete the task",
            test_file="test_04_challenge.py",
            required=True,
            auto_run=False,
            timeout_seconds=60,
            max_attempts=5,
            points=100
        ),
        PhaseConfig(
            id="check",
            name="Verification",
            description="Verify solution",
            test_file="test_05_check.py",
            required=True,
            auto_run=False,
            timeout_seconds=30,
            max_attempts=3,
            points=50
        ),
        PhaseConfig(
            id="cleanup",
            name="Cleanup",
            description="Clean up resources",
            test_file="test_06_cleanup.py",
            required=True,
            auto_run=True,
            timeout_seconds=30,
            max_attempts=1,
            points=0
        )
    ]


@pytest.fixture
def sample_manifest(sample_phases):
    """Sample task manifest"""
    return TaskManifest(
        task_id="01_test_task",
        title="Test Task",
        description="A test task for unit testing",
        difficulty="beginner",
        estimated_minutes=15,
        phases=sample_phases,
        prerequisites=[],
        tags=["test", "unit"],
        hints=["This is a test hint"]
    )


@pytest.fixture
def sample_task_state():
    """Sample task state"""
    return TaskState(
        email="test@example.com",
        game="game01",
        task_id="01_test_task",
        npc="test_npc",
        status=TaskStatus.NOT_STARTED,
        current_phase_id=None,
        phase_states={},
        session_data={"test_key": "test_value"},
        total_points=0
    )


@pytest.fixture
def in_progress_task_state(sample_task_state):
    """Task state in progress"""
    sample_task_state.status = TaskStatus.IN_PROGRESS
    sample_task_state.current_phase_id = "setup"
    return sample_task_state
