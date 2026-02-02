"""
End-to-end test for complete game flow.

This test simulates a real user playing the game by making sequential API calls
to complete a task from start to finish.

NPCs available: Aiden, AI, Alice, Carl, El, Herl
"""
import os
import time
import requests
import json
from typing import Dict, Any, List


class GameFlowTester:
    """Test the complete game flow with real API calls"""
    
    def __init__(self, base_url: str, api_key: str, email: str = "test@example.com"):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.email = email
        self.headers = {
            'x-api-key': api_key,
            'Content-Type': 'application/json'
        }
    
    def call_api(self, game: str, npc: str) -> Dict[str, Any]:
        """Make API call to task handler"""
        url = f"{self.base_url}/task"
        params = {
            'email': self.email,
            'game': game,
            'npc': npc
        }
        
        print(f"\n📞 Calling API: game={game}, npc={npc}")
        response = requests.get(url, params=params, headers=self.headers)
        
        if response.status_code != 200:
            print(f"❌ HTTP {response.status_code}: {response.text}")
            return {'status': 'ERROR', 'message': f'HTTP {response.status_code}'}
        
        data = response.json()
        print(f"📥 Response: {json.dumps(data, indent=2)}")
        return data
    
    def test_complete_task_flow(self, game: str = "game01", task_id: str = "01_default_namespace", npc: str = "Aiden"):
        """
        Test completing a full task from start to finish.
        
        Expected flow:
        1. Start task (STARTED)
        2. Execute setup phase (OK, moves to answer)
        3. Execute answer phase (OK, moves to check)
        4. Execute check phase (OK, moves to completion)
        5. Task completed (COMPLETED)
        6. Call again (COMPLETED - should not re-execute)
        """
        print(f"\n{'='*80}")
        print(f"🎮 Testing Complete Task Flow: {task_id} with NPC {npc}")
        print(f"{'='*80}")
        
        results = []
        max_calls = 10  # Safety limit
        call_count = 0
        
        while call_count < max_calls:
            call_count += 1
            print(f"\n--- Call #{call_count} ---")
            
            response = self.call_api(game, npc)
            results.append(response)
            
            status = response.get('status')
            message = response.get('message', '')
            current_phase = response.get('current_phase')
            
            # Check for random chat (30% chance)
            if status == 'OK' and message == '...':
                print("💬 Random chat response, calling again...")
                time.sleep(0.5)
                continue
            
            # Check for errors
            if status == 'ERROR':
                print(f"❌ ERROR: {message}")
                break
            
            # Check for task start
            if status == 'STARTED':
                print(f"✅ Task started: {response.get('task_id')}, phase: {current_phase}")
                time.sleep(0.5)
                continue
            
            # Check for phase completion
            if status == 'OK':
                next_phase = response.get('next_phase')
                print(f"✅ Phase passed: current={current_phase}, next={next_phase}")
                
                if next_phase is None and 'All phases completed' in message:
                    print("⚠️  All phases completed but task not marked as COMPLETED yet!")
                
                time.sleep(0.5)
                continue
            
            # Check for task completion
            if status == 'COMPLETED':
                print(f"🎉 Task completed! Points: {response.get('total_points')}")
                
                # Make one more call to verify it stays completed
                print("\n--- Verification Call ---")
                verify_response = self.call_api(game, npc)
                results.append(verify_response)
                
                if verify_response.get('status') == 'COMPLETED':
                    print("✅ Verification passed: Task stays COMPLETED")
                else:
                    print(f"❌ BUG FOUND: After completion, status is {verify_response.get('status')}")
                
                break
            
            # Check for failure
            if status == 'FAILED':
                print(f"❌ Phase failed: {message}")
                print(f"   Current phase: {current_phase}")
                print(f"   Attempts: {response.get('attempts')}/{response.get('max_attempts')}")
                break
            
            # Unknown status
            print(f"⚠️  Unknown status: {status}")
            break
        
        # Analyze results
        print(f"\n{'='*80}")
        print(f"📊 Test Summary")
        print(f"{'='*80}")
        print(f"Total API calls: {len(results)}")
        
        # Check for bugs
        bugs_found = []
        
        # Bug 1: "All phases completed" but status not COMPLETED
        for i, result in enumerate(results):
            if result.get('status') == 'OK' and 'All phases completed' in result.get('message', ''):
                if i + 1 < len(results) and results[i + 1].get('status') != 'COMPLETED':
                    bugs_found.append(f"Call #{i+1}: 'All phases completed' but next call status is {results[i+1].get('status')}")
        
        # Bug 2: Re-executing already passed phase
        phases_executed = []
        for i, result in enumerate(results):
            phase = result.get('current_phase')
            if phase and result.get('status') in ['OK', 'STARTED']:
                if phase in phases_executed:
                    bugs_found.append(f"Call #{i+1}: Re-executing already passed phase '{phase}'")
                phases_executed.append(phase)
        
        # Bug 3: Task not completing after all phases pass
        has_all_phases_completed = any('All phases completed' in r.get('message', '') for r in results)
        has_completed_status = any(r.get('status') == 'COMPLETED' for r in results)
        
        if has_all_phases_completed and not has_completed_status:
            bugs_found.append("Task showed 'All phases completed' but never reached COMPLETED status")
        
        # Print results
        if bugs_found:
            print("\n❌ BUGS FOUND:")
            for bug in bugs_found:
                print(f"   - {bug}")
            return False
        else:
            print("\n✅ All tests passed! No bugs found.")
            return True
    
    def test_multiple_npcs(self, game: str = "game01"):
        """Test with multiple NPCs to ensure they work correctly"""
        npcs = ["Aiden", "AI", "Alice", "Carl", "El", "Herl"]
        
        print(f"\n{'='*80}")
        print(f"🎮 Testing Multiple NPCs")
        print(f"{'='*80}")
        
        for npc in npcs:
            print(f"\n--- Testing NPC: {npc} ---")
            success = self.test_complete_task_flow(game, "01_default_namespace", npc)
            
            if not success:
                print(f"❌ Test failed for NPC {npc}")
                return False
            
            # Wait between NPCs
            time.sleep(2)
        
        print(f"\n✅ All NPCs tested successfully!")
        return True


def main():
    """Run the game flow tests"""
    # Get configuration from environment
    base_url = os.getenv('API_BASE_URL', 'https://your-api-gateway-url.amazonaws.com/Prod')
    api_key = os.getenv('API_KEY', 'your-api-key-here')
    email = os.getenv('TEST_EMAIL', 'test@example.com')
    
    if 'your-api' in base_url or 'your-api' in api_key:
        print("❌ Please set API_BASE_URL and API_KEY environment variables")
        print("\nExample:")
        print("  export API_BASE_URL='https://xxx.execute-api.us-east-1.amazonaws.com/Prod'")
        print("  export API_KEY='your-api-key'")
        print("  python test_game_flow_e2e.py")
        return
    
    tester = GameFlowTester(base_url, api_key, email)
    
    # Test single task
    print("\n" + "="*80)
    print("TEST 1: Complete Single Task")
    print("="*80)
    success = tester.test_complete_task_flow()
    
    if not success:
        print("\n❌ Test failed! Please check the bugs found above.")
        exit(1)
    
    # Optionally test multiple NPCs (commented out by default)
    # print("\n" + "="*80)
    # print("TEST 2: Multiple NPCs")
    # print("="*80)
    # success = tester.test_multiple_npcs()
    
    print("\n" + "="*80)
    print("✅ ALL TESTS PASSED!")
    print("="*80)


if __name__ == '__main__':
    main()
