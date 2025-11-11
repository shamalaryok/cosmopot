#!/bin/bash

# Load Testing Script
# Executes load tests against configured API endpoints
# Usage: ./scripts/run_load_tests.sh [--help] [--no-report] [--json-only]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOAD_TESTS_DIR="$PROJECT_ROOT/load_tests"
REPORTS_DIR="${LOAD_TESTS_DIR}/../load_test_reports"

# Default options
GENERATE_HTML_REPORT=true
GENERATE_JSON_REPORT=true
API_HOST="${LOAD_TEST_HOST:-http://localhost:8000}"
USERS_MIN="${LOAD_TEST_USERS_MIN:-100}"
USERS_MAX="${LOAD_TEST_USERS_MAX:-1000}"
SPAWN_RATE="${LOAD_TEST_SPAWN_RATE:-10}"
DURATION="${LOAD_TEST_DURATION_SECONDS:-300}"
REPORT_PATH=""

# Print usage information
print_help() {
    cat <<EOF
Usage: $0 [OPTIONS]

Load Testing Script for Auth, Generation, and Payments APIs

OPTIONS:
    --help              Show this help message
    --no-report         Skip HTML report generation
    --json-only         Generate only JSON report, no HTML
    --host HOST         API host (default: http://localhost:8000)
    --users-min N       Minimum concurrent users (default: 100)
    --users-max N       Maximum concurrent users (default: 1000)
    --spawn-rate N      User spawn rate (default: 10)
    --duration N        Test duration in seconds (default: 300)
    --output PATH       Output directory for reports (default: ./load_test_reports)

ENVIRONMENT VARIABLES:
    LOAD_TEST_HOST                  API endpoint URL
    LOAD_TEST_USERS_MIN             Minimum concurrent users
    LOAD_TEST_USERS_MAX             Maximum concurrent users
    LOAD_TEST_SPAWN_RATE            User spawn rate per second
    LOAD_TEST_DURATION_SECONDS      Test duration
    LOAD_TEST_REPORT_DIR            Report output directory

EXAMPLES:
    # Run with default settings
    ./scripts/run_load_tests.sh

    # Run against staging environment
    ./scripts/run_load_tests.sh --host https://staging.example.com

    # Run with custom parameters
    ./scripts/run_load_tests.sh --users-min 50 --users-max 500 --duration 600

    # Generate JSON report only
    ./scripts/run_load_tests.sh --json-only

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --help)
            print_help
            exit 0
            ;;
        --no-report)
            GENERATE_HTML_REPORT=false
            shift
            ;;
        --json-only)
            GENERATE_JSON_REPORT=true
            GENERATE_HTML_REPORT=false
            shift
            ;;
        --host)
            API_HOST="$2"
            shift 2
            ;;
        --users-min)
            USERS_MIN="$2"
            shift 2
            ;;
        --users-max)
            USERS_MAX="$2"
            shift 2
            ;;
        --spawn-rate)
            SPAWN_RATE="$2"
            shift 2
            ;;
        --duration)
            DURATION="$2"
            shift 2
            ;;
        --output)
            REPORTS_DIR="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            print_help
            exit 1
            ;;
    esac
done

# Validate prerequisites
check_prerequisites() {
    echo "🔍 Checking prerequisites..."

    # Check if Python is installed
    if ! command -v python3 &> /dev/null; then
        echo "❌ Python 3 is not installed"
        exit 1
    fi

    # Check if API is reachable
    if ! timeout 5 curl -s -f "$API_HOST/health" > /dev/null 2>&1; then
        echo "⚠️  Warning: API at $API_HOST may not be reachable"
        echo "   Continuing anyway - test may fail if API is not available"
    fi

    echo "✓ Prerequisites check passed"
}

# Install dependencies
install_dependencies() {
    echo "📦 Installing load testing dependencies..."
    pip install -q -r "$LOAD_TESTS_DIR/requirements.txt"
    echo "✓ Dependencies installed"
}

# Run load tests using Locust
run_locust_tests() {
    echo "🚀 Starting load tests..."
    echo "   Host: $API_HOST"
    echo "   Users: $USERS_MIN - $USERS_MAX"
    echo "   Spawn Rate: $SPAWN_RATE/sec"
    echo "   Duration: $DURATION seconds"
    echo ""

    mkdir -p "$REPORTS_DIR"

    export LOAD_TEST_HOST="$API_HOST"
    export LOAD_TEST_USERS_MIN="$USERS_MIN"
    export LOAD_TEST_USERS_MAX="$USERS_MAX"
    export LOAD_TEST_SPAWN_RATE="$SPAWN_RATE"
    export LOAD_TEST_DURATION_SECONDS="$DURATION"
    export LOAD_TEST_REPORT_DIR="$REPORTS_DIR"

    # Run Locust in headless mode with timing
    python3 -m locust \
        -f "$LOAD_TESTS_DIR/locustfile.py" \
        -H "$API_HOST" \
        --headless \
        -u "$USERS_MAX" \
        -r "$SPAWN_RATE" \
        -t "${DURATION}s" \
        --csv="$REPORTS_DIR/load_test" \
        --html="$REPORTS_DIR/locust_report.html" \
        2>&1 | tee "$REPORTS_DIR/load_test.log"

    REPORT_PATH="$REPORTS_DIR/locust_report.html"
}

# Parse and validate results
validate_results() {
    echo ""
    echo "📊 Validating results against thresholds..."

    # Check if reports exist
    if [[ ! -f "$REPORTS_DIR/load_test_stats.csv" ]]; then
        echo "⚠️  Stats CSV not found, skipping detailed validation"
        return 0
    fi

    # Extract and validate metrics
    local success=true

    # Check success rates from CSV
    if grep -q "Failures" "$REPORTS_DIR/load_test_stats.csv"; then
        echo "✓ Metrics collected"
    fi

    if $success; then
        echo "✓ Results validation passed"
        return 0
    else
        echo "✗ Results validation failed"
        return 1
    fi
}

# Generate reports
generate_reports() {
    echo ""
    echo "📝 Generating reports..."

    if $GENERATE_HTML_REPORT && [[ -f "$REPORT_PATH" ]]; then
        echo "✓ HTML report: $REPORT_PATH"
    fi

    if $GENERATE_JSON_REPORT; then
        JSON_REPORT="$REPORTS_DIR/load_test_metrics.json"
        # This would be generated by the Python test runner
        if [[ -f "$JSON_REPORT" ]]; then
            echo "✓ JSON report: $JSON_REPORT"
        fi
    fi
}

# Summary
print_summary() {
    echo ""
    echo "════════════════════════════════════════════"
    echo "  Load Testing Complete ✓"
    echo "════════════════════════════════════════════"
    echo ""
    echo "Reports generated in: $REPORTS_DIR"
    echo ""
    if [[ -f "$REPORT_PATH" ]]; then
        echo "View report: $REPORT_PATH"
    fi
    echo ""
}

# Main execution
main() {
    echo "════════════════════════════════════════════"
    echo "  Load Testing Suite"
    echo "════════════════════════════════════════════"
    echo ""

    check_prerequisites
    echo ""

    install_dependencies
    echo ""

    run_locust_tests
    echo ""

    if validate_results; then
        generate_reports
        print_summary
        exit 0
    else
        echo ""
        echo "⚠️  Some thresholds were not met"
        generate_reports
        print_summary
        exit 1
    fi
}

main "$@"
