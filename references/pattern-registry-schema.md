# Pattern Registry Schema

Pattern Registry stores reusable framework and domain guidance outside long
skill bodies.

## Pattern Entry

```json
{
  "pattern_id": "vite-react",
  "name": "Vite React Single Page App",
  "category": "framework",
  "solution_types": ["web-app", "dashboard"],
  "frameworks": ["vite-react", "vite"],
  "signals": ["vite.config.ts", "src/App.tsx"],
  "recommended_libraries": ["react", "react-dom"],
  "build_guidance": ["Keep the first version client-side unless backend is required."],
  "qa_focus": ["Main interaction loop", "Responsive layout"],
  "confidence": "high"
}
```

## MCP Tools

- `list_patterns(solution_type?, framework?, category?)`
- `read_pattern(pattern_id)`
- `render_pattern_context(solution_type?, framework?, category?)`

Build and QA skills should prefer pattern IDs and rendered registry context over
copying long framework guidance into active skill bodies.
