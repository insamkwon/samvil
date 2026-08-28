# Claude Code runtime evidence

- Verification level: `runtime_smoke`
- Tested commit: `a513a9bf2b2a9b605f0aa821e288fccc4b0ddc61`
- Tested tree: `a4cd64dd48f22bce7805d28dd4384d62c5408181`
- Claude Code: `2.1.207`
- Plugin load: observed; the actual init payload listed the `samvil` plugin.
- MCP ToolSearch: returned `get_pipeline_status`, `session_status`,
  `complete_stage`, and `resume_session`.

The real non-interactive Claude process ran in a temporary git project, read
`project.state.json` at `current_stage=interview`, made no file changes, and
exited `0`. This proves authenticated plugin/MCP smoke only; it does not yet
prove a full Interview-to-Seed or Build-to-QA transition.
