# SAMVIL Doctor Stage (Codex CLI)

## Prerequisites

No prior pipeline stage required.

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")` to check for resume.
2. If marker exists and `next_skill` is not `samvil-doctor`, report expected stage and stop.
3. Check environment prerequisites:
   - Node.js version (>=18)
   - npm/pnpm version
   - Python version (>=3.10, for MCP server)
   - Git version
4. Check SAMVIL installation:
   - MCP server available and responding
   - Plugin files intact
   - Cache directory exists
5. Run MCP tool `health_check()` to verify MCP server health.
6. Check project state:
   - `.samvil/` directory structure
   - `project.seed.json` validity
   - `state.json` validity
7. Report findings:
   - OK items (green)
   - Warning items (yellow — functional but suboptimal)
   - Error items (red — must fix before proceeding)
8. Provide fix instructions for any errors found.
9. Run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-doctor")` on completion.

## Chain

Standalone stage — no chain continuation.
Present diagnostic results to the user.
