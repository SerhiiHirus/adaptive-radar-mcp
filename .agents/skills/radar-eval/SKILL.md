---
name: radar-eval
description: Evaluates AI and automation changelogs/news against local project architecture, verifies APIs via Context7, and estimates token ROI.
---

# Radar Eval Skill

## Purpose
Use this skill when the user provides an AI changelog, daily update, or asks to review the latest technical news for potential adoption across workspace projects (e.g., content engines, algorithmic trading bots, data pipelines).

## Workflow

1. **Ingest Changelog**:
   - If the user provides text in the prompt, pass it to the parser.
   - If the user asks for "latest", inspect the configured drafts directory (e.g., `./drafts/*ai-automation*.md`).

2. **Run Evaluation Engine**:
   - Execute:
     ```bash
     python3 src/main.py --file "<path>" # or --text "..."
     ```

3. **Verify API with Context7**:
   - For all items marked `RECOMMENDED`, check `context7_query`.
   - Call Context7 tools:
     - `resolve-library-id` with the library name.
     - `query-docs` for the specific new feature (e.g., dynamic thinking effort, MCP server schema).
   - Ensure the feature is officially released, stable, and not a deprecated prototype.

4. **Safety & Cost Gate**:
   - Block dynamic code generation (`eval`, unconstrained agents).
   - Require Pydantic validation for structured outputs.
   - Enforce bounded retries and token optimization.

5. **Deliver Actionable Digest**:
   - Present a concise, 1-screen summary to the user:
     - **Ready for Implementation**: Tool, version, target project, token savings, verified API syntax.
     - **Monitor**: Promising tools that don't solve immediate blockers.
     - **Discarded**: Tools rejected due to security or hype.
   - Ask if the user wants to generate a PoC branch in the corresponding project.
