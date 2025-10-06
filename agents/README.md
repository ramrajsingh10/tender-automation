# Agents Directory

This folder hosts background automation agents and workers. Each agent should live in its own subdirectory with dedicated documentation, runtime configuration, and deployment automation.

## Conventions
- Place source code under <agent-name>/src (language-specific).
- Provide a <agent-name>/README.md describing responsibilities and run commands.
- Store environment variable templates as <agent-name>/.env.example.
- Ensure any infrastructure or scheduler definitions reference the new path (gents/<agent-name>).

The existing ingestion placeholder remains available for future implementation.