#!/bin/bash

# Comprehensive E2E test - Complete multiple tasks
# This tests the real game flow across multiple tasks and NPCs
#
# NOTE: For a fully self-contained test (with automatic setup), use:
#   ./test_complete_flow.sh
#
# This script requires manual configuration:
#   API_BASE_URL, API_KEY, EMAIL environment variables

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
API_BASE_URL="${API_BASE_URL:-}"
API_KEY="${API_KEY:-}"
EMAIL="${EMAIL:-developer@example.com}"
GAME="${GAME:-game01}"

# NPCs to use (rotate through them)
NPCS=("Aiden" "Alice" "Carl" "El" "Herl" "AI")
NPC_INDEX=0

# Check configuration
if [ -z "$API_BASE_URL" ] || [ -z "$API_KEY" ]; then
    echo -e "${RED}❌ Error: API_BASE_URL and API_KEY must be set${NC}"
    exit 1
fi

# Function to call API
call_api() {
    local npc="$1"
    local response
    response=$(curl -s -X GET \
        "${API_BASE_URL}/task?email=${EMAIL}&game=${GAME}&npc=${npc}" \
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

# Function to get next NPC (rotate through list)
get_next_npc() {
    local npc="${NPCS[$NPC_INDEX]}"
    NPC_INDEX=$(( (NPC_INDEX + 1) % ${#NPCS[@]} ))
    echo "$npc"
}

# Function to complete one task
complete_task() {
    local task_num="$1"
    local npc="$2"  # Use provided NPC instead of rotating
    
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  Task #${task_num} - NPC: ${npc}${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
    
    local call_count=0
    local max_calls=20
    local task_id=""
    local task_completed=false
    
    while [ $call_count -lt $max_calls ]; do
        call_count=$((call_count + 1))
        
        echo -e "${YELLOW}  Call #${call_count}${NC}"
        
        # Make API call
        response=$(call_api "$npc")
        
        # Extract fields
        status=$(get_field "$response" "status")
        message=$(get_field "$response" "message")
        current_phase=$(get_field "$response" "current_phase")
        task_id_field=$(get_field "$response" "task_id")
        points=$(get_field "$response" "total_points")
        
        # Store task ID
        if [ -n "$task_id_field" ] && [ -z "$task_id" ]; then
            task_id="$task_id_field"
        fi
        
        echo -e "    Status: ${status}"
        
        # Handle different statuses
        case "$status" in
            "ERROR")
                echo -e "${RED}    ❌ ERROR: $message${NC}"
                return 1
                ;;
            "OK")
                if [ "$message" = "..." ]; then
                    echo -e "${BLUE}    💬 Random chat${NC}"
                    sleep 0.3
                    continue
                fi
                
                if [[ "$message" == *"All phases completed"* ]]; then
                    echo -e "${GREEN}    ✅ All phases completed!${NC}"
                else
                    echo -e "${GREEN}    ✅ Phase passed: ${current_phase}${NC}"
                fi
                sleep 0.3
                ;;
            "STARTED")
                echo -e "${GREEN}    ✅ Task started: ${task_id_field}${NC}"
                sleep 0.3
                ;;
            "COMPLETED")
                echo -e "${GREEN}    🎉 Task completed! Points: ${points}${NC}"
                task_completed=true
                break
                ;;
            "FAILED")
                echo -e "${RED}    ❌ Phase failed: $message${NC}"
                return 1
                ;;
            *)
                echo -e "${YELLOW}    ⚠️  Unknown status: $status${NC}"
                ;;
        esac
    done
    
    if [ "$task_completed" = true ]; then
        echo -e "${GREEN}  ✅ Task ${task_id} completed successfully!${NC}"
        return 0
    else
        echo -e "${RED}  ❌ Task did not complete within ${max_calls} calls${NC}"
        return 1
    fi
}

# Main test
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Comprehensive E2E Test - Multiple Tasks                   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo "  API URL: $API_BASE_URL"
echo "  Email: $EMAIL"
echo "  Game: $GAME"
echo "  NPCs: ${NPCS[*]}"
echo ""

# Track results
total_tasks=0
completed_tasks=0
failed_tasks=0

# Complete multiple tasks
for i in {1..5}; do
    total_tasks=$((total_tasks + 1))
    npc="${NPCS[$((i-1))]}"  # Use different NPC for each task
    
    echo ""
    if complete_task "$i" "$npc"; then
        completed_tasks=$((completed_tasks + 1))
    else
        failed_tasks=$((failed_tasks + 1))
        echo -e "${RED}Task #${i} failed, stopping test${NC}"
        break
    fi
    
    # Small delay between tasks
    sleep 1
done

# Final summary
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                    Final Summary                               ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  Total tasks attempted: $total_tasks"
echo "  Tasks completed: $completed_tasks"
echo "  Tasks failed: $failed_tasks"
echo ""

if [ $failed_tasks -eq 0 ]; then
    echo -e "${GREEN}✅ ALL TASKS COMPLETED SUCCESSFULLY!${NC}"
    echo -e "${GREEN}   The bug fix is working correctly across multiple tasks!${NC}"
    exit 0
else
    echo -e "${RED}❌ SOME TASKS FAILED!${NC}"
    echo -e "${RED}   Please review the errors above.${NC}"
    exit 1
fi
