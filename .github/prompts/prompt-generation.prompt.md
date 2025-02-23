# Generating Prompt Files with SmartPrompt API

## Overview
This guide explains how to generate prompt files using the SmartPrompt API integration script and outlines the plan to transform it into a general-purpose client tool.

## Current Integration Script Usage
To generate a prompt file using the current integration script:

```bash
# Set your OpenAI API key
export OPENAI_API_KEY='your-key-here'

# Run the script with prompt generation mode
python scripts/integration prompt "explain terraform modules" \
  --domain infrastructure \
  --expertise-level intermediate \
  --output-format detailed \
  --output-file prompts/terraform-modules.prompt.md
```

## Migration Plan to Client Tool

### Phase 1: Basic Client Tool
1. Create a new `smartprompt-client` script:
   - Move core functionality from integration script
   - Add command-line interface with click/argparse
   - Support basic prompt generation
   - Add output file handling

2. Basic Usage Example:
```bash
smartprompt generate \
  --prompt "explain terraform modules" \
  --domain infrastructure \
  --expertise intermediate \
  --format detailed \
  --output prompts/terraform-modules.prompt.md
```

### Phase 2: Enhanced Features
1. Add template support:
   - Load prompt templates from files
   - Support custom template variables
   - Add template validation

2. Add batch processing:
   - Process multiple prompts from a file
   - Generate multiple variations
   - Support parallel processing

3. Add prompt management:
   - List generated prompts
   - Tag and categorize prompts
   - Search prompt history

### Phase 3: Integration Features
1. Add version control integration:
   - Auto-commit generated prompts
   - Branch management for variations
   - Pull request creation

2. Add CI/CD support:
   - Automated prompt generation
   - Quality checks
   - Deployment integration

## Implementation Details

### Core Components
1. PromptGenerator:
   - Handles communication with API
   - Manages templates and variations
   - Handles output formatting

2. TemplateManager:
   - Loads template files
   - Validates template structure
   - Handles variable substitution

3. OutputManager:
   - Handles file output
   - Manages formatting options
   - Supports different output formats

### Configuration
```yaml
# config.yaml example
api:
  url: http://localhost:8000
  timeout: 60
templates:
  path: ./templates
output:
  format: markdown
  path: ./prompts
```

### Template Format
```yaml
# template.yaml example
name: terraform-module
description: Template for Terraform module documentation
variables:
  module_name:
    type: string
    required: true
  provider:
    type: string
    default: aws
content: |
  # {module_name} Terraform Module
  
  ## Overview
  This module provides {provider} infrastructure components...
```

## Usage Examples

### Basic Prompt Generation
```bash
# Generate a single prompt
smartprompt generate \
  "explain aws vpc module" \
  --template infrastructure-module

# Generate multiple variations
smartprompt generate \
  "explain aws vpc module" \
  --variations 3 \
  --output-dir prompts/vpc-module/
```

### Batch Processing
```bash
# Process prompts from file
smartprompt batch \
  prompts.txt \
  --template infrastructure \
  --output-dir generated/

# Generate with CI/CD
smartprompt ci \
  --source-branch feature/new-modules \
  --commit-message "feat: add new module prompts"
```

## Next Steps
1. Create basic client script structure
2. Implement core PromptGenerator
3. Add template support
4. Add batch processing
5. Add version control integration
6. Create CI/CD workflows

## Notes
- Keep backward compatibility with integration tests
- Add proper error handling and logging
- Implement rate limiting and caching
- Add progress indicators for long operations