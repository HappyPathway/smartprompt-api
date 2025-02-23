Create a FastAPI-based REST API service that refines "lazy" prompts into high-quality prompts. The API should include the following features:

- An endpoint POST /refine-prompt that accepts a JSON payload with a field named "lazy_prompt".
- A function to transform the lazy prompt into a refined prompt (for now, you can simulate this transformation by simply prefixing the input with "Refined: " and appending additional text).
- Proper error handling for invalid input (e.g., missing or empty "lazy_prompt").
- Logging of requests and errors.
- OpenAPI (Swagger) documentation automatically generated.
- Include any necessary configuration for running the FastAPI application (for example, instructions to run using Uvicorn).

# output
the output of the API should be a markdown encoded string.

# code style
Your code should be modular and well-documented, so that it can be extended later with a more sophisticated prompt transformation algorithm. Use Python type hints and best practices for structuring a FastAPI application.

# enhance_prompt
the enhance prompt route will need to make a call to OpenAI and send the lazy prompt and have the OpenAI library convert it into a high quality prompt. We'll need to 
add to the initial prompt using this service. We'll want to research industry
wide best practices for whatevers being asked and add to it. The persona of the AI
will need to be that of a systems architect.

# User Management and Authentication

## Overview
The API will implement a comprehensive user management system with API key authentication. This system will support multiple users with different API keys and usage quotas.

## Data Model
### User
- id: UUID (primary key)
- email: String (unique)
- name: String
- organization: String (optional)
- created_at: DateTime
- status: Enum (active, suspended, deleted)

### APIKey
- id: UUID (primary key)
- user_id: UUID (foreign key to User)
- key: String (unique, hashed)
- name: String (for multiple keys per user)
- created_at: DateTime
- last_used_at: DateTime
- expires_at: DateTime (optional)
- status: Enum (active, revoked)
- permissions: Array[String] (for future granular access control)

### UsageQuota
- user_id: UUID (foreign key to User)
- period: String (daily, monthly, yearly)
- requests_limit: Integer
- requests_used: Integer
- reset_at: DateTime

## API Endpoints
1. User Management
   - POST /users - Create new user
   - GET /users/me - Get current user info
   - PUT /users/me - Update user info
   - DELETE /users/me - Delete user account

2. API Key Management
   - POST /api-keys - Generate new API key
   - GET /api-keys - List all API keys
   - DELETE /api-keys/{key_id} - Revoke specific API key
   - GET /api-keys/{key_id}/usage - Get usage statistics

3. Authentication
   - All endpoints except user creation will require API key authentication
   - API keys should be passed in the Authorization header
   - Failed authentication attempts should be rate limited

## Security Considerations
1. API Key Storage
   - Keys should be hashed using a cryptographic hash function
   - Original keys should only be shown once during creation
   - Use secure key generation with sufficient entropy

2. Rate Limiting
   - Implement per-user and per-key rate limiting
   - Consider both short-term (requests per minute) and long-term (daily/monthly) limits
   - Provide clear rate limit headers in responses

3. Access Control
   - Implement role-based access control for future admin features
   - Each API key can have specific permissions
   - Audit logging for security-relevant actions

## Storage
1. Primary Database
   - PostgreSQL for user data, API keys, and quotas
   - Use database migrations for schema management
   - Implement proper indexing for performance

2. Cache Layer
   - Redis for rate limiting and temporary data
   - Cache API key validations to reduce database load
   - Store usage statistics with appropriate TTL

## Implementation Phases
1. Phase 1 - Basic Authentication
   - Implement user model and API key storage
   - Basic API key validation middleware
   - Simple rate limiting

2. Phase 2 - User Management
   - Complete user management endpoints
   - API key management endpoints
   - Usage tracking

3. Phase 3 - Advanced Features
   - Granular permissions system
   - Admin dashboard
   - Usage analytics and reporting
   - Automated quota management

# Integration Testing

## Overview
The API includes integration tests that verify the complete functionality of the service, including Redis integration and endpoint behavior. Tests are run in a Docker environment to ensure consistency and isolation.

## Requirements
- Docker and Docker Compose installed
- Python 3.8 or higher
- Required test dependencies in requirements.test.txt

## Running Integration Tests
1. From the project root directory, run integration tests using:
   ```bash
   ./run-integration-tests.sh
   ```

2. The test script will:
   - Build the test Docker image
   - Start required services (API and Redis) using docker-compose.test.yml
   - Run the test suite
   - Output results to test_results/integration.xml

## Test Environment
- Tests run in an isolated Docker environment
- Redis instance is automatically provisioned for testing
- Environment variables are set via docker-compose.test.yml
- Tests use httpx for async HTTP client testing
- wait-for-it.sh ensures services are ready before testing

## Test Coverage
- API endpoint functionality
- Redis integration
- Error handling
- Rate limiting
- Authentication (when implemented)
- Request/Response validation