#!/bin/bash
set -e

# Ensure test results directory exists
mkdir -p test_results

# Build and run the integration tests
docker compose -f docker-compose.test.yml build
docker compose -f docker-compose.test.yml up \
    --abort-on-container-exit \
    --exit-code-from integration-tests

# Clean up
docker compose -f docker-compose.test.yml down