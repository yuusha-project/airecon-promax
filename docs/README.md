# AIRecon Documentation

Welcome to the AIRecon documentation.

## Guides

- [Installation & Setup](installation.md) — Docker Compose, local development, LLM provider setup
- [Configuration Reference](configuration.md) — Global config, per-scan config, all settings
- [Features & Capabilities](features.md) — Core feature overview, Docker sandbox, pipeline phases
- [Tools Reference](tools.md) — Complete reference for native tools, Docker sandbox tools, MCP tools
- [Stability & Quality Status](stability.md) — Current validation snapshot and quality metrics

## Architecture

- [API Reference](../README.md#api-reference) — REST API endpoints
- [Per-Scan Configuration](configuration.md#2-per-scan-config) — Override settings per scan
- [LLM Provider Support](configuration.md#3-llm-provider-settings) — OpenAI, Ollama, OpenRouter, etc.

## Extending AIRecon

- [Creating Custom Skills](development/creating_skills.md) — Add Markdown knowledge bases for new attack techniques

## Quick Links

| Task | Where to look |
|------|--------------|
| Install for the first time | [Installation Guide](installation.md) |
| Configure LLM provider | [Configuration → LLM Settings](configuration.md#3-llm-provider-settings) |
| Create a scan | [README → API Reference](../README.md#api-reference) |
| Override scan parameters | [Configuration → Per-Scan Config](configuration.md#2-per-scan-config) |
| Understand the pipeline | [Features → Pipeline Phases](features.md#pipeline-phases) |
| Add your own skill | [Creating Skills](development/creating_skills.md) |
| Troubleshoot issues | [Installation → Troubleshooting](installation.md#7-troubleshooting) |

## Community

Found a bug or want to contribute? [GitHub Issues](https://github.com/yuusha-project/airecon-promax/issues)
