# Decisions: Addendum

Entries continue the Phase 0 log, whose D-001 to D-005 live in the Phase 0 `docs/DECISIONS.md` and are not in this repository.
All entries below are **Proposed, pending Checkpoint A**.

---

## D-006: Keep the design model in a self-contained `context-relay/` directory

- **Context.** This repository's root holds the unrelated `myAssistant` RAG demo. The Phase 0 artifacts (PLAN.md, PLATFORM_NOTES.md,
  DECISIONS.md D-001–D-005) were produced elsewhere.
- **Decision.** Put the workflow and blast-radius work under `context-relay/`, touching nothing at the repository root.
- **Consequences.** Moving it later is a single `git mv`. At Checkpoint A: choose the product repository, then merge these docs with the
  Phase 0 files, renumbering `PN-*` into `F-*` where they overlap.

## D-007: Store packs outside `CLAUDE_PLUGIN_DATA` and outside the project

- **Context.**
  - Claude Code deletes `CLAUDE_PLUGIN_DATA` on uninstall from the last location (PN-05).
  - That directory isn't exported to the Bash tool, and the native host and a globally installed `ctxr` can't discover it.
  - A store inside the project would be writable by the model without a prompt in `acceptEdits` mode.
- **Decision.** Use one tool-owned store shared by hooks, CLI, MCP and the native host:
  - Linux: `$XDG_DATA_HOME/context-relay` (default `~/.local/share/context-relay`)
  - macOS: `~/Library/Application Support/context-relay`
  - Windows: `%LOCALAPPDATA%\context-relay`
  - Override: `CTXR_HOME`
- **Consequences.**
  - Uninstalling the plugin keeps the user's packs; a documented `ctxr purge` deletes them.
  - `CLAUDE_PLUGIN_DATA` is used only for caches.
  - This closes FM-06 and supports C-PERMISSION-BOUNDARY.

## D-008: Accept the continuity loop as a measured residual risk

- **Context.** Automatic continuity (W1) is a trust loop: inject → session → capture → store → inject. No full control can cut it without
  removing the feature. The model lists it as the only uncontained persistent loop the relay adds (BLAST_RADIUS §8).
- **Decision.** Accept the loop under both of these conditions, measured before Checkpoint C on held-out seeds with Wilson 95% bounds:
  1. θ_wrap ≥ 0.95: the share of planted injections not acted on, per surface.
  2. θ_echo ≥ 0.95 per hop: the share of planted markers absent from the next pack, so that g ≤ 0.05.

  If either fails, SessionStart auto-inject ships **off by default** (opt-in), and W1 becomes user-initiated through X2.
- **Consequences.** The injection and echo harnesses become part of the hooks phase's Definition of Done. `acceptedCycles` in the model
  references this decision, and removing it fails CI.

## D-009: Threat-model boundary is the delta over host capabilities

- **Context.** Inside Claude Code the model may already hold Bash and Write. Anything the relay protects on disk, such as approval stamps,
  can be forged by an agent with those permissions (FM-30).
- **Decision.** The relay must not **add** blast radius. It does not claim to defend against an agent that already has unrestricted
  write or exec (for example `bypassPermissions`). Blast radius is reported as a delta; host-granted capabilities are `baseline` edges.
- **Consequences.**
  - `--via` stays CLI-only. It adds nothing inside Claude Code but would add execution to MCP and the native host.
  - The docs state the boundary plainly (SECURITY.md).

## D-010: Trust = origin plus a hash-bound approval stamp; integrity ≠ provenance

- **Context.** A content hash proves the bytes are unchanged, not where they came from. Composability lets every entry reach every exit.
- **Decision.**
  - Packs carry an `origin` ∈ `session`, `foreign`, `model`.
  - A human `ctxr approve <id>` writes a **local** stamp keyed by the content hash. It requires an interactive TTY and the typed short hash.
  - Effective trust is `user` while a stamp matches the current hash.
  - Stamps are never serialized into shared packs.
  - UI wording is "unchanged since sealed", never "verified" or "trusted".
- **Consequences.**
  - Editing revokes approval automatically.
  - A teammate's approval never approves for you.
  - Gates: auto-inject, MCP and native-host serving, and instruction export (INV-AUTO-TRUST, INV-SERVE, INV-INSTR-TRUST).
  - Open question: does the Bash tool allocate a TTY? (WORKFLOWS §9)

## D-011: The design model is executable, with no dependencies

- **Context.** Blast-radius claims in prose drift from the design. One claim in an early draft here was already wrong, and the model caught it.
- **Decision.** `model/relay-model.json` plus `tools/relay-model.mjs`, in Node ESM with no dependencies, tested with `node --test`.
  Generated doc sections sit between markers, and `check` fails on drift.
- **Consequences.** After Checkpoint B the tool moves into the monorepo's CI (`scripts/`), and SPEC.md becomes the source for primitive
  types and labels.

## D-012: MCP server is read-only in v1

- **Context.** An MCP write tool (E8) creates a model-to-model persistence channel, even when its output is drafts (WORKFLOWS §7).
- **Decision.** v1 exposes list and fetch only, of sealed session packs and approved packs (C-DRAFT-ISOLATION). If a write tool is added
  later, it creates drafts that stay invisible to MCP until a human approves them.
- **Consequences.** E8 stays in the model as the specification of what a future write tool must satisfy (anti-workflow A1).

## D-013: Decisions inside packs are keyed entries

- **Context.** When several packs are injected together, contradictions between them go undetected. The uploaded OmegaClaw
  `memory_audit` benchmark (synthetic, L2) shows:
  - A deterministic audit exposes all planted contradictions when beliefs are structured and consistently named.
  - Its catch rate falls roughly as p² (direct) and p³ (two-step) with the structured share p, and falls quickly with aliasing.
  - v1 forbids LLM calls, so similarity-based checks are out anyway.
- **Decision.** `decisions[]` entries carry `key` (a stable, normalized identifier), `value`, `rationale` and optional `supersedes`.
  `ctxr audit` flags equal keys with different values across the packs selected for one injection.
- **Consequences.** Adds a Phase 1 spec field and a planted-contradiction harness. Free-text decisions stay allowed but are unauditable,
  and the audit reports what share of decisions it could check.
