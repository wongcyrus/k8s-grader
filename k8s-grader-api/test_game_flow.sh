#!/bin/bash

# End-to-end test script for game flow
# Tests completing a task from start to finish

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
API_BASE_URL="${API_BASE_URL:-}"
API_KEY="${API_KEY:-}"
EMAIL="${EMAIL:-test@example.com}"
GAME="${GAME:-game01}"
TASK="${TASK:-01_default_namespace}"
NPC="${NPC:-Aiden}"

# Check configuration
if [ -z "$API_BASE_URL" ] || [ -z "$API_KEY" ]; then
    echo -e "${RED}❌ Error: API_BASE_URL and API_KEY must be set${NC}"
    echo ""
    echo "Usage:"
    echo "  export API_BASE_URL='https://xxx.execute-api.us-east-1.amazonaws.com/Prod'"
    echo "  export API_KEY='your-api-key'"
    echo "  ./test_game_flow.sh"
    echo ""
    echo "Optional:"
    echo "  export EMAIL='your-email@example.com'"
    echo "  export GAME='game01'"
    echo "  export TASK='01_default_namespace'"
    echo "  export NPC='Aiden'"
    exit 1
fi

# Function to call API
call_api() {
    local response
    response=$(curl -s -X GET \
        "${API_BASE_URL}/task?email=${EMAIL}&game=${GAME}&npc=${NPC}" \
        -H "x-api-key: ${API_KEY}" \
        -H "Content-Type: application/json")
    echo "$response"
}

# Function to extract JSON field
get_field() {
    local json="$1"
    local field="$2"
    echo "$json" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('$field', ''))" 2>/dev/null || echo ""
}

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           Game Flow End-to-End Test                            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo "  API URL: $API_BASE_URL"
echo "  Email: $EMAIL"
echo "  Game: $GAME"
echo "  Task: $TASK"
echo "  NPC: $NPC"
echo ""

# Track state
call_count=0
max_calls=15
bugs_found=0
phases_seen=()

echo -e "${BLUE}Starting test...${NC}"
echo ""

while [ $call_count -lt $max_calls ]; do
    call_count=$((call_count + 1))
    
    echo -e "${YELLOW}--- Call #${call_count} ---${NC}"
    
    # Make API call
    response=$(call_api)
    
    # Extract fields
    status=$(get_field "$response" "status")
    message=$(get_field "$response" "message")
    current_phase=$(get_field "$response" "current_phase")
    next_phase=$(get_field "$response" "next_phase")
    
    echo "Status: $status"
    echo "Message: $message"
    echo "Current Phase: $current_phase"
    echo "Next Phase: $next_phase"
    
    # Check for random chat
    if [ "$status" = "OK" ] && [ "$message" = "..." ]; then
        echo -e "${BLUE}💬 Random chat, calling again...${NC}"
        sleep 0.5
        continue
    fi
    
    # Check for errors
    if [ "$status" = "ERROR" ]; then
        echo -e "${RED}❌ ERROR: $message${NC}"
        bugs_found=$((bugs_found + 1))
        break
    fi
    
    # Check for task start
    if [ "$status" = "STARTED" ]; then
        echo -e "${GREEN}✅ Task started${NC}"
        phases_seen+=("$current_phase")
        sleep 0.5
        continue
    fi
    
    # Check for phase completion
    if [ "$status" = "OK" ]; then
        echo -e "${GREEN}✅ Phase passed${NC}"
        
        # Check if phase was already seen (bug: re-executing)
        for phase in "${phases_seen[@]}"; do
            if [ "$phase" = "$current_phase" ]; then
                echo -e "${RED}❌ BUG: Re-executing already passed phase '$current_phase'${NC}"
                bugs_found=$((bugs_found + 1))
            fi
        done
        phases_seen+=("$current_phase")
        
        # Check for "All phases completed" without COMPLETED status
        if [[ "$message" == *"All phases completed"* ]]; then
            echo -e "${YELLOW}⚠️  'All phases completed' message shown${NC}"
            # Next call should be COMPLETED
        fi
        
        sleep 0.5
        continue
    fi
    
    # Check for task completion
    if [ "$status" = "COMPLETED" ]; then
        echo -e "${GREEN}🎉 Task completed!${NC}"
        
        # Verify it stays completed
        echo ""
        echo -e "${YELLOW}--- Verification Call ---${NC}"
        verify_response=$(call_api)
        verify_status=$(get_field "$verify_response" "status")
        
        if [ "$verify_status" = "COMPLETED" ]; then
            echo -e "${GREEN}✅ Verification passed: Task stays COMPLETED${NC}"
        else
            echo -e "${RED}❌ BUG: After completion, status is $verify_status${NC}"
            bugs_found=$((bugs_found + 1))
        fi
        
        break
    fi
    
    # Check for failure
    if [ "$status" = "FAILED" ]; then
        echo -e "${RED}❌ Phase failed: $message${NC}"
        bugs_found=$((bugs_found + 1))
        break
    fi
    
    # Unknown status
    echo -e "${YELLOW}⚠️  Unknown status: $status${NC}"
    sleep 0.5
done

# Summary
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                    Test Summary                                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Total API calls: $call_count"
echo "Phases executed: ${#phases_seen[@]}"
echo "Bugs found: $bugs_found"
echo ""

if [ $bugs_found -eq 0 ]; then
    echo -e "${GREEN}✅ ALL TESTS PASSED! No bugs found.${NC}"
    exit 0
else
    echo -e "${RED}❌ TESTS FAILED! $bugs_found bug(s) found.${NC}"
    exit 1
fi
