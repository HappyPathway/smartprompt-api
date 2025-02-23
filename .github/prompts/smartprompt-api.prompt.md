Create a FastAPI-based REST API service that refines “lazy” prompts into high-quality prompts. The API should include the following features:

- An endpoint POST /refine-prompt that accepts a JSON payload with a field named "lazy_prompt".
- A function to transform the lazy prompt into a refined prompt (for now, you can simulate this transformation by simply prefixing the input with "Refined: " and appending additional text).
- Proper error handling for invalid input (e.g., missing or empty "lazy_prompt").
- Logging of requests and errors.
- OpenAPI (Swagger) documentation automatically generated.
- Include any necessary configuration for running the FastAPI application (for example, instructions to run using Uvicorn).

Your code should be modular and well-documented, so that it can be extended later with a more sophisticated prompt transformation algorithm. Use Python type hints and best practices for structuring a FastAPI application.

# enhance_prompt
the enhance prompt route will need to make a call to OpenAI and send the lazy prompt and have the OpenAI library convert it into a high quality prompt. We'll need to 
add to the initial prompt using this service. We'll want to research industry
wide best practices for whatevers being asked and add to it. The persona of the AI
will need to be that of a systems architect. 