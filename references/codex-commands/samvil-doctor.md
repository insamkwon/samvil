# SAMVIL Doctor Stage (Codex CLI)

## Prerequisites

This is a standalone stage — no chain marker required.

## Execution

1. Check environment prerequisites:
   - Node.js version (>=18)
   - npm/pnpm version
   - Python version (>=3.10, for MCP server)
   - Git version
2. Check SAMVIL installation:
   - MCP server available and responding
   - Plugin files intact
   - Cache directory exists
3. Run MCP tool `health_check()` to verify MCP server health.
4. Check project state:
   - `.samvil/` directory structure
   - `project.seed.json` validity
   - `state.json` validity
5. Report findings:
   - OK items (green)
   - Warning items (yellow — functional but suboptimal)
   - Error items (red — must fix before proceeding)
6. Provide fix instructions for any errors found.

## Chain

Standalone stage — no chain continuation.
Present diagnostic results to the user.
