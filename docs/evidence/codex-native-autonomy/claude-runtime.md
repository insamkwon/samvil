# Claude Code runtime evidence

- Verification level: `blocked_auth`
- Tested commit: `46c550c828f0932f48572e516b5589af41be2ed9`
- Tested tree: `062758516ad907a23b371e333cd6e3dc26ca22a1`
- Claude Code: `2.1.207`
- Plugin load: observed; the actual init payload listed the `samvil` plugin.

The real non-interactive Claude process exited `1` before executing the prompt:
`Not logged in · Please run /login` (`authentication_failed`). Therefore this
receipt is not a runtime PASS and does not prove stage execution or chaining.

Re-run after Claude authentication is restored.
