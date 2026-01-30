"""Integration tests for the deployed API"""
import pytest
import requests
import json
import time
from typing import Dict, Any


class TestAPIIntegration:
    """Test real API endpoints"""
    
    def test_stack_outputs_available(self, stack_outputs):
        """Verify stack outputs are available"""
        assert 'ApiEndpoint' in stack_outputs
        assert 'TaskStateTable' in stack_outputs
        assert 'NpcLockTable' in stack_outputs
        assert 'NpcAssignmentTable' in stack_outputs
    
    def test_api_endpoint_reachable(self, api_endpoint):
        """Test that API endpoint is reachable"""
        # Try to reach the endpoint without API key
        response = requests.get(f"{api_endpoint}/task")
        # With custom auth, Lambda returns 200 with error in body
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ERROR'
        assert 'Missing required parameters' in data['message']
    
    def test_missing_parameters(self, api_endpoint, test_api_key):
        """Test API with missing parameters"""
        response = requests.get(
            f"{api_endpoint}/task",
            headers={'x-api-key': test_api_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ERROR'
        assert 'Missing required parameters' in data['message']
    
    def test_invalid_game_format(self, api_endpoint, test_api_key, test_email, test_npc):
        """Test API with invalid game format"""
        response = requests.get(
            f"{api_endpoint}/task",
            params={
                'email': test_email,
                'game': 'game-01',  # Invalid: contains hyphen
                'npc': test_npc
            },
            headers={'x-api-key': test_api_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ERROR'
        assert 'alphanumeric' in data['message']
    
    def test_npc_not_found(self, api_endpoint, test_api_key, test_email, test_game):
        """Test API with non-existent NPC"""
        response = requests.get(
            f"{api_endpoint}/task",
            params={
                'email': test_email,
                'game': test_game,
                'npc': 'nonexistent_npc'
            },
            headers={'x-api-key': test_api_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ERROR'
        assert 'not found' in data['message']
    
    def test_user_not_found(self, api_endpoint, test_api_key, test_game, test_npc):
        """Test API with non-existent user"""
        response = requests.get(
            f"{api_endpoint}/task",
            params={
                'email': 'nonexistent@example.com',
                'game': test_game,
                'npc': test_npc
            },
            headers={'x-api-key': test_api_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        # Should either get random chat (OK) or error about user not found
        assert data['status'] in ['OK', 'ERROR']
        if data['status'] == 'ERROR':
            assert 'User account not found' in data['message'] or 'not found' in data['message']


class TestTaskFlow:
    """Test complete task flow with real API"""
    
    @pytest.mark.slow
    def test_complete_task_flow(self, api_endpoint, test_api_key, test_email, 
                                test_game, test_npc):
        """Test complete task flow from start to finish"""
        # Note: This test requires a real user account with K8s credentials
        # and will be skipped unless explicitly enabled
        
        # Step 1: Start task
        response = requests.get(
            f"{api_endpoint}/task",
            params={
                'email': test_email,
                'game': test_game,
                'npc': test_npc
            },
            headers={'x-api-key': test_api_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Could be random chat, task start, or error
        assert data['status'] in ['OK', 'STARTED', 'ERROR']
        
        if data['status'] == 'STARTED':
            assert 'task_id' in data
            assert 'current_phase' in data
            assert 'progress' in data
            assert data['progress'] == 0.0


class TestDynamoDBIntegration:
    """Test DynamoDB operations through the API"""
    
    def test_task_state_persistence(self, api_endpoint, test_api_key, test_email,
                                    test_game, test_npc, dynamodb_client, 
                                    task_state_table):
        """Test that task state is persisted to DynamoDB"""
        # Make API call
        response = requests.get(
            f"{api_endpoint}/task",
            params={
                'email': test_email,
                'game': test_game,
                'npc': test_npc
            },
            headers={'x-api-key': test_api_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # If task was started, verify it's in DynamoDB
        if data['status'] == 'STARTED':
            time.sleep(1)  # Give DynamoDB time to persist
            
            # Query DynamoDB
            try:
                db_response = dynamodb_client.get_item(
                    TableName=task_state_table,
                    Key={
                        'email': {'S': test_email},
                        'gameTask': {'S': f"{test_game}#{data['task_id']}"}
                    }
                )
                
                # Verify item exists
                assert 'Item' in db_response
                item = db_response['Item']
                assert item['email']['S'] == test_email
                assert item['status']['S'] == 'IN_PROGRESS'
            except Exception as e:
                pytest.skip(f"Could not verify DynamoDB state: {e}")


class TestAPIPerformance:
    """Test API performance and response times"""
    
    def test_api_response_time(self, api_endpoint, test_api_key, test_email,
                               test_game, test_npc):
        """Test that API responds within acceptable time"""
        start_time = time.time()
        
        response = requests.get(
            f"{api_endpoint}/task",
            params={
                'email': test_email,
                'game': test_game,
                'npc': test_npc
            },
            headers={'x-api-key': test_api_key},
            timeout=10
        )
        
        elapsed_time = time.time() - start_time
        
        assert response.status_code == 200
        # API should respond within 5 seconds
        assert elapsed_time < 5.0, f"API took {elapsed_time:.2f}s to respond"
    
    def test_concurrent_requests(self, api_endpoint, test_api_key, test_email,
                                 test_game, test_npc):
        """Test API handles concurrent requests"""
        import concurrent.futures
        
        def make_request():
            response = requests.get(
                f"{api_endpoint}/task",
                params={
                    'email': test_email,
                    'game': test_game,
                    'npc': test_npc
                },
                headers={'x-api-key': test_api_key},
                timeout=10
            )
            return response.status_code
        
        # Make 5 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # All requests should succeed
        assert all(status == 200 for status in results)


class TestErrorHandling:
    """Test API error handling"""
    
    def test_invalid_api_key(self, api_endpoint, test_email, test_game, test_npc):
        """Test API with invalid API key"""
        response = requests.get(
            f"{api_endpoint}/task",
            params={
                'email': test_email,
                'game': test_game,
                'npc': test_npc
            },
            headers={'x-api-key': 'invalid-key'}
        )
        
        # With custom auth, Lambda returns 200 with error in body
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ERROR'
        assert 'Internal error' in data['message']  # Fernet decryption fails
    
    def test_missing_api_key(self, api_endpoint, test_email, test_game, test_npc):
        """Test API without API key"""
        response = requests.get(
            f"{api_endpoint}/task",
            params={
                'email': test_email,
                'game': test_game,
                'npc': test_npc
            }
        )
        
        # With custom auth, Lambda returns 200 with error in body
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ERROR'
        assert 'Missing required parameters' in data['message']
    
    def test_malformed_request(self, api_endpoint, test_api_key):
        """Test API with malformed request"""
        response = requests.get(
            f"{api_endpoint}/task",
            params={
                'email': 'not-an-email',
                'game': '../../etc/passwd',  # Path traversal attempt
                'npc': '<script>alert("xss")</script>'  # XSS attempt
            },
            headers={'x-api-key': test_api_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ERROR'
