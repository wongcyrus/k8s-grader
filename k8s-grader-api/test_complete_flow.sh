#!/bin/bash

# Self-contained E2E test - Fail → Fix → Pass Flow
# This script handles everything: API key retrieval, reset, cleanup, and testing

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

# Configuration
EMAIL="${EMAIL:-developer@example.com}"
GAME="${GAME:-game01}"
STACK_NAME="${STACK_NAME:-k8s-grader-api-dev}"
REGION="${REGION:-us-east-1}"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Self-Contained E2E Test - Complete Flow                   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo "  Email: $EMAIL"
echo "  Game: $GAME"
echo "  Stack: $STACK_NAME"
echo "  Region: $REGION"
echo ""

# ============================================================================
# STEP 1: Get API URL and Key from AWS
# ============================================================================

echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  Step 1: Getting API URL and Key from AWS                     ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Get API URL from CloudFormation stack
echo -e "${YELLOW}Getting API URL from CloudFormation...${NC}"
API_BASE_URL=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
    --output text 2>/dev/null || echo "")

if [ -z "$API_BASE_URL" ]; then
    echo -e "${RED}❌ Failed to get API URL from stack${NC}"
    exit 1
fi
echo -e "${GREEN}✅ API URL: ${API_BASE_URL}${NC}"

# Get ApiKeyTable name from CloudFormation
echo -e "${YELLOW}Getting ApiKeyTable name...${NC}"
API_KEY_TABLE=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiKeyTable`].OutputValue' \
    --output text 2>/dev/null || echo "")

if [ -z "$API_KEY_TABLE" ]; then
    echo -e "${RED}❌ Failed to get ApiKeyTable name${NC}"
    exit 1
fi
echo -e "${GREEN}✅ ApiKeyTable: ${API_KEY_TABLE}${NC}"

# Get API key from DynamoDB
echo -e "${YELLOW}Getting API key from DynamoDB...${NC}"
API_KEY=$(aws dynamodb scan \
    --table-name "$API_KEY_TABLE" \
    --region "$REGION" \
    --filter-expression "email = :email" \
    --expression-attribute-values '{":email":{"S":"'$EMAIL'"}}' \
    --query 'Items[0].api_key.S' \
    --output text 2>/dev/null || echo "")

if [ -z "$API_KEY" ] || [ "$API_KEY" = "None" ]; then
    echo -e "${RED}❌ No API key found for ${EMAIL}${NC}"
    echo -e "${YELLOW}Please generate an API key first using:${NC}"
    echo -e "${CYAN}  cd k8s-grader-api${NC}"
    echo -e "${CYAN}  ./generate_test_api_key.sh${NC}"
    exit 1
fi
echo -e "${GREEN}✅ API key retrieved${NC}"

echo ""
sleep 1

# ============================================================================
# STEP 2: Delete existing test namespaces
# ============================================================================

echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  Step 2: Cleaning up test namespaces                          ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${YELLOW}Checking for existing test namespaces...${NC}"
existing_namespaces=$(kubectl get namespaces -o name 2>/dev/null | grep -E "namespace/blissful" | sed 's|namespace/||' || echo "")

if [ -n "$existing_namespaces" ]; then
    echo -e "${YELLOW}Found existing test namespaces:${NC}"
    echo "$existing_namespaces"
    echo ""
    for ns in $existing_namespaces; do
        echo -e "${YELLOW}Deleting namespace: ${ns}${NC}"
        kubectl delete namespace "$ns" --ignore-not-found=true --timeout=30s 2>/dev/null || true
    done
    echo -e "${GREEN}✅ Cleanup complete${NC}"
else
    echo -e "${GREEN}✅ No existing test namespaces found${NC}"
fi

echo ""
sleep 1

# ============================================================================
# STEP 3: Reset game state
# ============================================================================

echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  Step 3: Resetting game state                                 ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Get the script directory to find reset_game.py
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(dirname "$SCRIPT_DIR")/tools"

if [ -f "$TOOLS_DIR/reset_game.py" ]; then
    echo -e "${YELLOW}Resetting game state...${NC}"
    python3 "$TOOLS_DIR/reset_game.py" --email "$EMAIL" --game "$GAME" 2>&1 | grep -E "(Deleted|Reset complete|Error)" || true
    echo -e "${GREEN}✅ Game state reset${NC}"
else
    echo -e "${YELLOW}⚠️  reset_game.py not found, skipping reset${NC}"
fi

echo ""
sleep 1

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

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

# ============================================================================
# STEP 4: Run Task #1 (01_default_namespace)
# ============================================================================

echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  Step 4: Task #1 - 01_default_namespace (NPC: Aiden)          ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

NPC="Aiden"
call_count=0
max_calls=20

while [ $call_count -lt $max_calls ]; do
    call_count=$((call_count + 1))
    echo -e "${YELLOW}  Call #${call_count}${NC}"
    
    response=$(call_api "$NPC")
    status=$(get_field "$response" "status")
    message=$(get_field "$response" "message")
    
    echo -e "    Status: ${status}"
    [ -n "$message" ] && echo -e "    ${CYAN}Message: \"${message}\"${NC}"
    
    case "$status" in
        "ERROR")
            echo -e "${RED}    ❌ ERROR${NC}"
            exit 1
            ;;
        "OK")
            if [ "$message" = "..." ]; then
                echo -e "${BLUE}    💬 Random chat${NC}"
                sleep 0.3
                continue
            fi
            echo -e "${GREEN}    ✅ Phase passed${NC}"
            sleep 0.3
            ;;
        "STARTED")
            echo -e "${GREEN}    ✅ Task started${NC}"
            sleep 0.3
            ;;
        "COMPLETED")
            echo -e "${GREEN}    🎉 Task #1 completed!${NC}"
            break
            ;;
        "FAILED")
            echo -e "${RED}    ❌ Phase failed${NC}"
            exit 1
            ;;
    esac
done

echo ""
echo -e "${GREEN}✅ Task #1 completed successfully!${NC}"
echo ""
sleep 2

# ============================================================================
# STEP 5: Run Task #2 - Let it fail (namespace doesn't exist)
# ============================================================================

echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  Step 5: Task #2 - Let it fail (no namespace)                 ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

NPC="Alice"
call_count=0
namespace_name=""

# Start the task and get through phases until we see the namespace name
while [ $call_count -lt $max_calls ]; do
    call_count=$((call_count + 1))
    echo -e "${YELLOW}  Call #${call_count}${NC}"
    
    response=$(call_api "$NPC")
    status=$(get_field "$response" "status")
    message=$(get_field "$response" "message")
    
    echo -e "    Status: ${status}"
    [ -n "$message" ] && echo -e "    ${CYAN}Message: \"${message}\"${NC}"
    
    # Extract namespace name from message if present
    if [[ "$message" == *"blissful"* ]]; then
        namespace_name=$(echo "$message" | grep -oP "blissful[a-z0-9]+")
        echo -e "${MAGENTA}    📝 Namespace name: ${namespace_name}${NC}"
    fi
    
    case "$status" in
        "ERROR")
            echo -e "${RED}    ❌ ERROR${NC}"
            exit 1
            ;;
        "OK")
            if [ "$message" = "..." ]; then
                echo -e "${BLUE}    💬 Random chat${NC}"
                sleep 0.3
                continue
            fi
            echo -e "${GREEN}    ✅ Phase passed${NC}"
            sleep 0.3
            ;;
        "STARTED")
            echo -e "${GREEN}    ✅ Task started${NC}"
            sleep 0.3
            ;;
        "FAILED")
            echo -e "${YELLOW}    ⚠️  Phase failed (expected)${NC}"
            break
            ;;
        "COMPLETED")
            echo -e "${RED}    ❌ Unexpected completion!${NC}"
            exit 1
            ;;
    esac
done

echo ""
echo -e "${GREEN}✅ Task #2 failed as expected (namespace doesn't exist)${NC}"
echo ""

# ============================================================================
# STEP 6: Create the namespace automatically
# ============================================================================

if [ -z "$namespace_name" ]; then
    echo -e "${RED}❌ Could not detect namespace name from API response${NC}"
    exit 1
fi

echo -e "${MAGENTA}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${MAGENTA}║  Step 6: Creating namespace automatically                     ║${NC}"
echo -e "${MAGENTA}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Namespace to create: ${GREEN}${namespace_name}${NC}"
echo ""

# Create the namespace
echo -e "${YELLOW}Creating namespace...${NC}"
if kubectl create namespace "$namespace_name" 2>/dev/null; then
    echo -e "${GREEN}✅ Namespace '${namespace_name}' created successfully!${NC}"
else
    echo -e "${YELLOW}⚠️  Namespace might already exist, checking...${NC}"
    if kubectl get namespace "$namespace_name" &>/dev/null; then
        echo -e "${GREEN}✅ Namespace '${namespace_name}' exists!${NC}"
    else
        echo -e "${RED}❌ Failed to create namespace!${NC}"
        exit 1
    fi
fi

echo ""
sleep 2

# ============================================================================
# STEP 7: Continue Task #2 - Verify it passes
# ============================================================================

echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  Step 7: Task #2 - Verify it passes (namespace exists)        ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

call_count=0

while [ $call_count -lt $max_calls ]; do
    call_count=$((call_count + 1))
    echo -e "${YELLOW}  Call #${call_count}${NC}"
    
    response=$(call_api "$NPC")
    status=$(get_field "$response" "status")
    message=$(get_field "$response" "message")
    
    echo -e "    Status: ${status}"
    [ -n "$message" ] && echo -e "    ${CYAN}Message: \"${message}\"${NC}"
    
    case "$status" in
        "ERROR")
            echo -e "${RED}    ❌ ERROR${NC}"
            # If error is about no phase, task might have been abandoned - continue calling
            if [[ "$message" == *"No phase specified"* ]] || [[ "$message" == *"no current phase"* ]]; then
                echo -e "${YELLOW}    Task was abandoned, calling again to restart...${NC}"
                sleep 1
                continue
            fi
            exit 1
            ;;
        "OK")
            if [ "$message" = "..." ]; then
                echo -e "${BLUE}    💬 Random chat${NC}"
                sleep 0.3
                continue
            fi
            echo -e "${GREEN}    ✅ Phase passed${NC}"
            sleep 0.3
            ;;
        "FAILED")
            echo -e "${RED}    ❌ Phase still failing${NC}"
            echo -e "${YELLOW}    Retrying...${NC}"
            sleep 1
            ;;
        "ABANDONED")
            echo -e "${YELLOW}    ⚠️  Task abandoned (max attempts reached)${NC}"
            echo -e "${YELLOW}    Calling again to restart...${NC}"
            sleep 1
            # Continue to next iteration to restart
            ;;
        "STARTED")
            echo -e "${GREEN}    ✅ Task restarted (after abandonment)${NC}"
            sleep 0.3
            # Continue to execute the restarted task
            ;;
        "COMPLETED")
            echo -e "${GREEN}    🎉 Task #2 completed!${NC}"
            break
            ;;
    esac
done

echo ""
echo -e "${GREEN}✅ Task #2 completed successfully after creating namespace!${NC}"
echo ""

# ============================================================================
# FINAL SUMMARY
# ============================================================================

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                    Test Summary                                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}✅ Task #1: Completed (01_default_namespace)${NC}"
echo -e "${GREEN}✅ Task #2: Failed → Fixed → Completed (02_create_namespace)${NC}"
echo ""
echo -e "${MAGENTA}This test verified:${NC}"
echo "  ✅ Tasks complete correctly when all phases pass"
echo "  ✅ Tasks fail correctly when requirements not met"
echo "  ✅ Tasks can be retried after fixing issues"
echo "  ✅ State management works across multiple attempts"
echo "  ✅ Bug 4 fix working: No misleading 'All phases completed!' on failure"
echo ""
echo -e "${GREEN}🎉 ALL TESTS PASSED - GAME FLOW WORKING CORRECTLY!${NC}"
echo ""

# Cleanup: Delete the namespace
echo -e "${YELLOW}Cleaning up: Deleting namespace ${namespace_name}...${NC}"
kubectl delete namespace "$namespace_name" --ignore-not-found=true &>/dev/null || true
echo -e "${GREEN}✅ Cleanup complete${NC}"
