# Jurisdiction boundary cases (⑦)

Per HANDOFF-v3.2-DECISIONS.md §3.⑦, some actions sit on the edge
between AI-autonomous, External-consult, and User-confirm. Document the
decisions here so the harness (and its maintainers) stay consistent.

Rule of thumb: strictest wins. AI < External < User.

## Reference cases

### 1. Login form implementation

* **Action**: Build a login form that POSTs to `/auth/login`.
* **Detected keywords**: `auth`, `password`.
* **Jurisdiction**: **User**.
* **Why**: the `auth` keyword is explicitly user-gated. Even on a toy
  project, shipping auth without a human in the loop is the exact
  failure mode ⑦ exists to catch.
* **Workflow**: build-worker writes the code; `check_jurisdiction`
  returns `user`; the skill blocks the commit until the user approves.
  One-session grants (see `GrantLedger`) can reduce friction during
  iterative dev.

### 2. DB migration

* **Action**: `ALTER TABLE sessions RENAME COLUMN …` or an Alembic-style
  upgrade.
* **Detected keywords**: `migration`, irreversible command regex.
* **Jurisdiction**: **User**.
* **Why**: `migration` and `ALTER TABLE` / `DROP TABLE` are both
  irreversible against a live dataset, and wrong migrations are one of
  the most common "it worked in dev" failures. The user confirms
  before the MCP can even post the `migration_applied` claim.

### 3. API key code

* **Action**: Add `const API_KEY = process.env.API_KEY`.
* **Detected keywords**: `api_key`, `secret`.
* **Jurisdiction**: **User**.
* **Why**: even reading a secret implies production coupling.
  `check_jurisdiction` reports `user_keyword:api_key`; the skill should
  pause and confirm whether it's populating `.env.example` (OK) vs.
  pasting a real value (never OK).

### 4. Package install

* **Action**: `npm install some-package` or `uv add some-lib`.
* **Detected keywords**: `npm install`, `uv add`.
* **Jurisdiction**: **External**.
* **Why**: a new package is a supply-chain change. The harness should
  (a) look up the package's license + vulnerability record, (b) record
  the result as an `evidence_posted` claim, then proceed. User
  confirmation is *not* needed unless a `User`-gated keyword also
  matches (e.g., the diff itself mentions `secret`).

### 5. `.env` file edit

* **Action**: Edit `.env` or create `.env.example`.
* **Detected keywords**: `.env` doesn't hit the regex directly, but
  typical content (`API_KEY=`, `SECRET=`) does.
* **Jurisdiction**: **User** (when real values) or **External** (when
  documenting placeholders).
* **Why**: `.env.example` with placeholders is safe; `.env` with real
  values is a production secret. The detector relies on the **content**
  scan, not the filename.

### 6. Running tests

* **Action**: `pytest tests/` or `npm test`.
* **Detected keywords**: none.
* **Jurisdiction**: **AI**.
* **Why**: tests are idempotent and local. Nothing leaves the box.

### 7. Creating a new branch

* **Action**: `git checkout -b feature/x`.
* **Detected keywords**: none.
* **Jurisdiction**: **AI**.
* **Why**: branch creation is reversible (`git branch -D feature/x`).

### 8. `git push`

* **Action**: `git push origin feature/x`.
* **Detected regex**: `git push`.
* **Jurisdiction**: **User**.
* **Why**: push is visible to others. Even non-forced pushes can
  surprise collaborators. Grant-memory allows one session to approve
  "push this branch".

### 9. Deploying to Vercel preview vs production

* **Action**: `vercel` (preview) vs `vercel --prod`.
* **Detected regex**: `vercel --prod` matches irreversible.
* **Jurisdiction**: Preview = **AI**. Production = **User**.
* **Why**: previews are throwaway; production is visible to end-users.

### 10. Pricing research

* **Action**: Fetch a third-party service's pricing page.
* **Detected keyword**: `pricing`.
* **Jurisdiction**: **External**.
* **Why**: the harness has no authoritative data. It must consult a
  current source and record an `evidence_posted` claim with the URL +
  retrieval date.

## Edge cases that don't resolve cleanly

- **Partial keyword matches**: `authority_file` contains "auth" but the
  action is about the SAMVIL authority-file concept, not authentication.
  The detector flags it; the skill is free to override with a
  `# glossary-allow` style hint in the action description, but only
  when the author can demonstrate no sensitive-data involvement. Log a
  retro observation every time an override is used so drift is visible.
- **Renaming a file that happens to contain "password" in the name**:
  the detector flags user; if the content is a no-op rename (no secret
  change), the skill can record an External verdict with an
  `evidence_posted` claim referencing the diff and let the retro layer
  decide whether the detector needs refinement.

## Updating these rules

Add new entries here in the same PR as any regex changes to
`mcp/samvil_mcp/jurisdiction.py`. The retro `observations[]` schema
includes a `category` field; use `category: jurisdiction_boundary` for
edge-case filings.
