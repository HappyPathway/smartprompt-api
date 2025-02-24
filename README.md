# tf-smart-prompt

Repository for the gcp-kubernetes project in HappyPathway

## Getting Started

1. Clone this repository:
```bash
git clone git@github.com:HappyPathway/tf-smart-prompt.git
cd tf-smart-prompt
```

2. Set up Python environment and install dependencies:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
pip install -r scripts/requirements.txt
```

3. Run the initialization script:
```bash
python scripts/init.py
```

This will:
- Verify Git SSH access to GitHub
- Create the workspace directory structure
- Clone or update all project repositories
- Set up repository configurations

For debugging, you can run:
```bash
python scripts/init.py --debug
```

## Repository Structure

This project consists of multiple repositories:

- terraform-provider-smartprompt: tf-smart-prompt::terraform-provider-smartprompt
- smartprompt-api: tf-smart-prompt::smartprompt-api
- smartprompt-client: tf-smart-prompt::smartprompt-client
- smartprompt-infra-deployment: tf-smart-prompt::smartprompt-infra-deployment
- smartprompt-website: tf-smart-prompt::smartprompt-website

## Development Environment

This repository includes:
- VS Code workspace configuration
- GitHub Copilot settings
- Project-specific documentation and guidelines
- Python-based initialization tools

## Contributing

Please see the [CONTRIBUTING.md](.github/CONTRIBUTING.md) file for guidelines.

# Smart Prompt API

A FastAPI service that transforms simple "lazy" prompts into refined, high-quality prompts.

## Quick Start

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the service:
```bash
uvicorn main:app --reload
```

The API will be available at http://localhost:8000

## API Documentation

Once running, view the OpenAPI documentation at http://localhost:8000/docs

### Endpoints

- POST /refine-prompt
  - Input: JSON with "lazy_prompt" field
  - Output: JSON with "refined_prompt" field

## Development

> **Note:** Use `docker compose` instead of `docker-compose` as the latter is deprecated. The hyphenated version is a legacy Python-based implementation that will eventually be removed.

The service is structured to be easily extensible. The current implementation adds basic refinements, but you can enhance the transformation logic in the `/refine-prompt` endpoint.