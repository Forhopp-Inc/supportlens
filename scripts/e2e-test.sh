#!/bin/bash
# =============================================================================
# SupportLens End-to-End Test Script
# =============================================================================
# 
# This script verifies the full data flow of the SupportLens application:
# 1. Health endpoint reflects actual system state
# 2. Traces can be created and retrieved
# 3. Analytics correctly aggregate trace data
# 4. Category filtering works correctly
# 5. Pagination works correctly
#
# Exit codes:
#   0 - All tests passed
#   1 - Test failure (with detailed output)
#
# Usage:
#   ./scripts/e2e-test.sh
#
# Environment:
#   API_BASE_URL - Base URL for API (default: http://localhost:8000)
#   FRONTEND_URL - Base URL for frontend (default: http://localhost:3000)
# =============================================================================

set -e  # Exit on first error

# Configuration
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3000}"

# Detect Python command (python3, python, or py on Windows)
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
elif command -v py &> /dev/null; then
    PYTHON_CMD="py"
else
    echo "Error: Python is required but not found. Please install Python 3."
    exit 1
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    # GitHub Actions annotation for visibility
    if [ -n "$GITHUB_ACTIONS" ]; then
        echo "::warning::$1"
    fi
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    # GitHub Actions annotation for visibility
    if [ -n "$GITHUB_ACTIONS" ]; then
        echo "::error::$1"
    fi
}

log_test() {
    echo -e "\n${GREEN}[TEST]${NC} $1"
}

assert_equals() {
    local expected="$1"
    local actual="$2"
    local message="$3"
    
    if [ "$expected" == "$actual" ]; then
        log_info "✓ $message"
        ((TESTS_PASSED++)) || true
        return 0
    else
        log_error "✗ $message"
        log_error "  Expected: $expected"
        log_error "  Actual:   $actual"
        ((TESTS_FAILED++)) || true
        return 1
    fi
}

assert_contains() {
    local haystack="$1"
    local needle="$2"
    local message="$3"
    
    if [[ "$haystack" == *"$needle"* ]]; then
        log_info "✓ $message"
        ((TESTS_PASSED++)) || true
        return 0
    else
        log_error "✗ $message"
        log_error "  Expected to contain: $needle"
        log_error "  Actual: $haystack"
        ((TESTS_FAILED++)) || true
        return 1
    fi
}

assert_greater_than() {
    local actual="$1"
    local threshold="$2"
    local message="$3"
    
    if [ "$actual" -gt "$threshold" ]; then
        log_info "✓ $message (value: $actual)"
        ((TESTS_PASSED++)) || true
        return 0
    else
        log_error "✗ $message"
        log_error "  Expected > $threshold, got $actual"
        ((TESTS_FAILED++)) || true
        return 1
    fi
}

# =============================================================================
# Test: Health Endpoint
# =============================================================================
test_health_endpoint() {
    log_test "Health Endpoint"
    
    # Get health status
    HEALTH_RESPONSE=$(curl -sf "${API_BASE_URL}/health" || echo "FAILED")
    
    if [ "$HEALTH_RESPONSE" == "FAILED" ]; then
        log_error "Health endpoint not reachable"
        ((TESTS_FAILED++)) || true
        return 1
    fi
    
    # Parse response using Python (jq alternative)
    STATUS=$(echo "$HEALTH_RESPONSE" | $PYTHON_CMD -c "import json,sys; print(json.load(sys.stdin).get('status',''))")
    CAN_SERVE=$(echo "$HEALTH_RESPONSE" | $PYTHON_CMD -c "import json,sys; print(str(json.load(sys.stdin).get('can_serve_traffic',False)).lower())")
    DB_STATUS=$(echo "$HEALTH_RESPONSE" | $PYTHON_CMD -c "import json,sys; d=json.load(sys.stdin); print(d.get('dependencies',{}).get('database',{}).get('status',''))")
    LLM_STATUS=$(echo "$HEALTH_RESPONSE" | $PYTHON_CMD -c "import json,sys; d=json.load(sys.stdin); print(d.get('dependencies',{}).get('llm',{}).get('status',''))")
    UPTIME=$(echo "$HEALTH_RESPONSE" | $PYTHON_CMD -c "import json,sys; print(json.load(sys.stdin).get('uptime_seconds',0))")
    
    # Verify health response structure
    if [ "$STATUS" == "healthy" ] || [ "$STATUS" == "degraded" ]; then
        log_info "✓ Health status is valid ($STATUS)"
        ((TESTS_PASSED++)) || true
    else
        log_error "✗ Health status is invalid: $STATUS"
        ((TESTS_FAILED++)) || true
    fi
    assert_equals "true" "$CAN_SERVE" "Application can serve traffic"
    assert_equals "healthy" "$DB_STATUS" "Database is healthy"
    
    # LLM may be degraded in CI (no API key) - that's expected
    if [ "$LLM_STATUS" == "degraded" ]; then
        log_warn "LLM is degraded (expected in CI without API key)"
    fi
    
    # Verify uptime is a positive number (using Python for float comparison)
    UPTIME_POSITIVE=$($PYTHON_CMD -c "print('yes' if float('$UPTIME') > 0 else 'no')" 2>/dev/null || echo "no")
    if [ "$UPTIME_POSITIVE" == "yes" ]; then
        log_info "✓ Uptime is positive: ${UPTIME}s"
        ((TESTS_PASSED++)) || true
    else
        log_error "✗ Invalid uptime: $UPTIME"
        ((TESTS_FAILED++)) || true
    fi
    
    log_info "Health response: $HEALTH_RESPONSE"
}

# =============================================================================
# Test: Seed Data Loaded
# =============================================================================
test_seed_data() {
    log_test "Seed Data"
    
    # Get initial analytics
    ANALYTICS=$(curl -sf "${API_BASE_URL}/analytics")
    INITIAL_COUNT=$(echo "$ANALYTICS" | $PYTHON_CMD -c "import json,sys; print(json.load(sys.stdin).get('total_count',0))")
    
    # Seed data should have loaded 25 traces
    assert_greater_than "$INITIAL_COUNT" 0 "Seed data loaded (count: $INITIAL_COUNT)"
    
    # Verify category breakdown exists
    CATEGORY_COUNT=$(echo "$ANALYTICS" | $PYTHON_CMD -c "import json,sys; print(len(json.load(sys.stdin).get('category_breakdown',{})))")
    assert_greater_than "$CATEGORY_COUNT" 0 "Category breakdown has entries"
}

# =============================================================================
# Test: Create Trace and Verify Data Flow
# =============================================================================
test_create_trace_flow() {
    log_test "Create Trace Data Flow"
    
    # Get initial count
    INITIAL_ANALYTICS=$(curl -sf "${API_BASE_URL}/analytics")
    INITIAL_COUNT=$(echo "$INITIAL_ANALYTICS" | $PYTHON_CMD -c "import json,sys; print(json.load(sys.stdin).get('total_count',0))")
    
    # Create a new trace
    TRACE_RESPONSE=$(curl -sf -X POST "${API_BASE_URL}/traces" \
        -H "Content-Type: application/json" \
        -d '{
            "user_message": "E2E test message - billing inquiry",
            "bot_response": "This is a test response for E2E testing",
            "response_time_ms": 150
        }')
    
    # Verify trace was created
    TRACE_ID=$(echo "$TRACE_RESPONSE" | $PYTHON_CMD -c "import json,sys; print(json.load(sys.stdin).get('id',''))")
    TRACE_CATEGORY=$(echo "$TRACE_RESPONSE" | $PYTHON_CMD -c "import json,sys; print(json.load(sys.stdin).get('category',''))")
    
    if [ -z "$TRACE_ID" ] || [ "$TRACE_ID" == "null" ]; then
        log_error "Failed to create trace"
        ((TESTS_FAILED++)) || true
        return 1
    fi
    
    log_info "Created trace with ID: $TRACE_ID, Category: $TRACE_CATEGORY"
    ((TESTS_PASSED++)) || true
    
    # Verify analytics count incremented
    NEW_ANALYTICS=$(curl -sf "${API_BASE_URL}/analytics")
    NEW_COUNT=$(echo "$NEW_ANALYTICS" | $PYTHON_CMD -c "import json,sys; print(json.load(sys.stdin).get('total_count',0))")
    
    EXPECTED_COUNT=$((INITIAL_COUNT + 1))
    assert_equals "$EXPECTED_COUNT" "$NEW_COUNT" "Analytics count incremented after trace creation"
    
    # Verify trace appears in traces list
    TRACES=$(curl -sf "${API_BASE_URL}/traces?page=1&page_size=100")
    FOUND_TRACE=$(echo "$TRACES" | $PYTHON_CMD -c "import json,sys; d=json.load(sys.stdin); matches=[t['id'] for t in d.get('traces',[]) if t.get('id')=='$TRACE_ID']; print(matches[0] if matches else '')")
    
    assert_equals "$TRACE_ID" "$FOUND_TRACE" "Created trace appears in traces list"
}

# =============================================================================
# Test: Category Filtering
# =============================================================================
test_category_filtering() {
    log_test "Category Filtering"
    
    # Create traces with known categories (using keywords that trigger specific classifications)
    # Note: Without LLM, all will be General_Inquiry (fallback)
    
    # Get all traces first
    ALL_TRACES=$(curl -sf "${API_BASE_URL}/traces?page_size=100")
    TOTAL_ALL=$(echo "$ALL_TRACES" | $PYTHON_CMD -c "import json,sys; print(json.load(sys.stdin).get('total',0))")
    
    # Test filtering by General_Inquiry (should have at least seed data)
    FILTERED=$(curl -sf "${API_BASE_URL}/traces?category=General_Inquiry&page_size=100")
    FILTERED_TOTAL=$(echo "$FILTERED" | $PYTHON_CMD -c "import json,sys; print(json.load(sys.stdin).get('total',0))")
    FILTERED_COUNT=$(echo "$FILTERED" | $PYTHON_CMD -c "import json,sys; print(len(json.load(sys.stdin).get('traces',[])))")
    
    # Verify filter returns subset
    if [ "$FILTERED_TOTAL" -le "$TOTAL_ALL" ]; then
        log_info "✓ Category filter returns subset ($FILTERED_TOTAL <= $TOTAL_ALL)"
        ((TESTS_PASSED++)) || true
    else
        log_error "✗ Category filter returned more than total"
        ((TESTS_FAILED++)) || true
    fi
    
    # Verify all returned traces have correct category
    WRONG_CATEGORY=$(echo "$FILTERED" | $PYTHON_CMD -c "import json,sys; d=json.load(sys.stdin); print(len([t for t in d.get('traces',[]) if t.get('category')!='General_Inquiry']))")
    assert_equals "0" "$WRONG_CATEGORY" "All filtered traces have correct category"
}

# =============================================================================
# Test: Pagination
# =============================================================================
test_pagination() {
    log_test "Pagination"
    
    # Get first page
    PAGE1=$(curl -sf "${API_BASE_URL}/traces?page=1&page_size=5")
    PAGE1_COUNT=$(echo "$PAGE1" | $PYTHON_CMD -c "import json,sys; print(len(json.load(sys.stdin).get('traces',[])))")
    TOTAL=$(echo "$PAGE1" | $PYTHON_CMD -c "import json,sys; print(json.load(sys.stdin).get('total',0))")
    TOTAL_PAGES=$(echo "$PAGE1" | $PYTHON_CMD -c "import json,sys; print(json.load(sys.stdin).get('total_pages',0))")
    
    log_info "Total traces: $TOTAL, Total pages: $TOTAL_PAGES"
    
    # Verify page size is respected
    if [ "$PAGE1_COUNT" -le 5 ]; then
        log_info "✓ Page size respected (got $PAGE1_COUNT, max 5)"
        ((TESTS_PASSED++)) || true
    else
        log_error "✗ Page size not respected"
        ((TESTS_FAILED++)) || true
    fi
    
    # If there are multiple pages, verify page 2 is different
    if [ "$TOTAL_PAGES" -gt 1 ]; then
        PAGE2=$(curl -sf "${API_BASE_URL}/traces?page=2&page_size=5")
        PAGE1_FIRST_ID=$(echo "$PAGE1" | $PYTHON_CMD -c "import json,sys; d=json.load(sys.stdin); t=d.get('traces',[]); print(t[0].get('id','') if t else '')")
        PAGE2_FIRST_ID=$(echo "$PAGE2" | $PYTHON_CMD -c "import json,sys; d=json.load(sys.stdin); t=d.get('traces',[]); print(t[0].get('id','') if t else '')")
        
        if [ "$PAGE1_FIRST_ID" != "$PAGE2_FIRST_ID" ]; then
            log_info "✓ Page 2 has different traces than page 1"
            ((TESTS_PASSED++)) || true
        else
            log_error "✗ Page 2 has same first trace as page 1"
            ((TESTS_FAILED++)) || true
        fi
    else
        log_warn "Only one page of data, skipping page 2 test"
    fi
}

# =============================================================================
# Test: Frontend Accessibility
# =============================================================================
test_frontend() {
    log_test "Frontend"
    
    # Check frontend is serving
    FRONTEND_RESPONSE=$(curl -sf -o /dev/null -w "%{http_code}" "${FRONTEND_URL}/")
    assert_equals "200" "$FRONTEND_RESPONSE" "Frontend returns 200"
    
    # Check it's serving HTML (not a directory listing)
    CONTENT=$(curl -sf "${FRONTEND_URL}/" | head -c 100)
    if [[ "$CONTENT" == *"<!DOCTYPE html>"* ]] || [[ "$CONTENT" == *"<!doctype html>"* ]]; then
        log_info "✓ Frontend serves HTML"
        ((TESTS_PASSED++)) || true
    else
        log_error "✗ Frontend does not serve HTML"
        log_error "  Actual: $CONTENT"
        ((TESTS_FAILED++)) || true
    fi
}

# =============================================================================
# Test: Error Handling
# =============================================================================
test_error_handling() {
    log_test "Error Handling"
    
    # Test invalid category filter (expect 422)
    INVALID_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE_URL}/traces?category=InvalidCategory")
    assert_equals "422" "$INVALID_RESPONSE" "Invalid category returns 422"
    
    # Test invalid page number (expect 422)
    INVALID_PAGE=$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE_URL}/traces?page=0")
    assert_equals "422" "$INVALID_PAGE" "Invalid page number returns 422"
    
    # Test invalid trace creation (empty message, expect 422)
    INVALID_TRACE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${API_BASE_URL}/traces" \
        -H "Content-Type: application/json" \
        -d '{"user_message": "", "bot_response": "test", "response_time_ms": 100}')
    assert_equals "422" "$INVALID_TRACE" "Empty message returns 422"
}

# =============================================================================
# Test: Request Correlation
# =============================================================================
test_request_correlation() {
    log_test "Request Correlation (X-Request-ID)"
    
    # Make request and check for X-Request-ID header
    HEADERS=$(curl -s -I "${API_BASE_URL}/health" 2>&1 || true)
    
    if echo "$HEADERS" | grep -qi "x-request-id"; then
        log_info "✓ X-Request-ID header present"
        ((TESTS_PASSED++)) || true
    else
        log_warn "X-Request-ID header not found (optional feature)"
    fi
}

# =============================================================================
# Main Test Runner
# =============================================================================
main() {
    echo "=============================================="
    echo "SupportLens End-to-End Tests"
    echo "=============================================="
    echo "API URL: ${API_BASE_URL}"
    echo "Frontend URL: ${FRONTEND_URL}"
    echo "=============================================="
    
    # Run all tests
    test_health_endpoint
    test_seed_data
    test_create_trace_flow
    test_category_filtering
    test_pagination
    test_frontend
    test_error_handling
    test_request_correlation
    
    # Summary
    echo ""
    echo "=============================================="
    echo "Test Summary"
    echo "=============================================="
    echo -e "Passed: ${GREEN}${TESTS_PASSED}${NC}"
    echo -e "Failed: ${RED}${TESTS_FAILED}${NC}"
    echo "=============================================="
    
    if [ "$TESTS_FAILED" -gt 0 ]; then
        log_error "Some tests failed!"
        exit 1
    else
        log_info "All tests passed!"
        exit 0
    fi
}

# Run main
main "$@"
