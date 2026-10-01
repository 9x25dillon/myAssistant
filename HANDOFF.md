# HANDOFF: Context Relay, Porter blast radius, harness hardening

_Session window: 2026-09-30 → 2026-10-01. Session: https://claude.ai/code/session_01YGx8BTEjvbbKgRXAmceVn7_
_Written for whoever picks this up next, human or agent. Evidence levels: **L0** verified by running code, **L1** from reading code, **L2** needs measurement, **L3** speculative._

## 1. State at handoff

| Item | Repo / branch | State |
|---|---|---|
| Context Relay model and Porter plugin (`a106c34`, `b419b8f`) | myAssistant [#1](https://github.com/9x25dillon/myAssistant/pull/1) | **merged** (`d2ec0c6`) |
| `merge_models`, `mcp-builder-hardened` skill, `sync-subtree.sh`, this file, and the forge-aware kgirl model (`156b379`, `438d3cb`, `ac57288`, `df86fb0`, `09c0eac`) | myAssistant [#2](https://github.com/9x25dillon/myAssistant/pull/2) | **merged** with this update. `09c0eac` came from a parallel session (`session_01CNxWA1c8cUHpQTsBZfwJwa`) |
| Harness MCP hardening | kgirl [#55](https://github.com/9x25dillon/kgirl/pull/55) | **merged** (`cc92cd5`) |
| `context-relay/` copy (synced to `09c0eac`), kgirl-side Porter guide, skill symlink | kgirl [#58](https://github.com/9x25dillon/kgirl/pull/58) | **merged** (`92e0545`). The parallel session made the second sync; `ae09aac` updated PORTER.md after #55 merged |
| Porter: agent-shell changes wait for the user | patern-coding [#2](https://github.com/9x25dillon/patern-coding/pull/2) | **merged** (`2fc2aee`). The live check in its test plan is still unticked |
| Skill-forge trust boundary (KFM-11) | kgirl [#59](https://github.com/9x25dillon/kgirl/pull/59), from the parallel session | **open, not reviewed by this session** |
| `mcp-builder-hardened.zip` | delivered in chat; not in git (no archives in git) | to install: turn off the original `mcp-builder`, then upload under Settings → Capabilities → Skills |
| Context Relay product (`ctxr`, skill, packs) | none | **not started**. Everything is Phase 0 design input. D-006 to D-017 are all *Proposed, pending Checkpoint A* |

**Tests at handoff (all L0):**

| Suite | Result |
|---|---|
| `context-relay` in myAssistant | 115 pass, 2 skipped (both kgirl contract tests need `KGIRL_SRC`) |
| The same suite on kgirl `main` (`#58` merged onto `cc92cd5`), with `KGIRL_SRC=$PWD/src` | 117 pass, 0 skipped |
| Skill checker | 9 pass; 0 findings on kgirl's harness since #55 |
| kgirl harness on `main` | OK, 1 skipped (Playwright); 49 tests at #55 |
| patern-coding#2 | 55 pass |
| nihiline and evolve, here | numpy tests skipped |
| patern-coding `test_auric` | errors without torch, as it does on `main` |

## 2. What was built

### 2.1 myAssistant: `context-relay/`
- **Executable design model.** `model/relay-model.json` has:
  - 42 components, 118 edges (change, runtime, trust) and 35 threat-scoped controls
  - 13 workflows and 11 anti-workflows
  - 31 failure modes
  - a route matrix of 8 ways in × 9 ways out: 46 compositions direct, 26 needing a human gate, 0 forbidden

  `tools/relay-model.mjs` checks the model with no dependencies. It validates, interprets workflows abstractly, computes blast radius over the exposure lattice (unmitigated > damped > contained), finds persistence loops, and syncs the generated tables in `docs/WORKFLOWS.md` and `docs/BLAST_RADIUS.md`. Decisions D-006 to D-017 and platform notes PN-01 to PN-15 (checked against the docs on 2026-09-30) are logged.
- **`plugins/porter-blast-radius/`** is a Claude Code plugin with a read-only stdio MCP server and no dependencies.
  - **9 tools:** `list_models`, `check_model`, `blast_radius`, `compose`, `emergent_use_cases`, `risk_register`, `atlas_import`, `merge_models`, `porter_discover`.
  - **Analysis:** four views (change, runtime, integrity, confidentiality), and `as_built` evaluation that switches off proposed controls.
  - **Loops:** SCC detection catches loops that pass the same node twice, which cycle enumeration misses (D-016).
  - **Discovery:** reads git facts from `.git` files without running git, plus npm, PyPI, Go, Cargo and `porter.json` manifests.
  - **Atlas bridge:** opens kgirl's `atlas.db` read-only through `node:sqlite`.
  - **Self-model:** `model/connector.model.json`, whose top residual risk is CFM-05.
- **`skills/mcp-builder-hardened/`** is Anthropic's `mcp-builder` (Apache-2.0, changes listed in `NOTICE.md`) plus `reference/blast_radius_review.md` and `scripts/blast_radius_check.py`. The checker covers:
  - BR001: the model chooses a program
  - BR002: child processes inherit secrets
  - BR003: model-written state goes live
  - BR004: protocol-version echo
  - BR005: unconfined writes
- **`tools/sync-subtree.sh`** copies `context-relay/` into another repo and pulls later changes (a squashed commit plus a merge). It exists because `git subtree` fails in repos that track a file named `HEAD`, as kgirl does.
- **Docs:** `docs/KGIRL_HARNESS.md` is the kgirl review and cross-check. Porter's file-level blast radius matched kgirl's own `blast` exactly: 47 dependents in total, 23 direct (L0).

### 2.2 kgirl
- **#55:**
  - `soup_remember` stores notes as `staged` with source `mcp`, and the curator never promotes them; a person runs `soup promote`.
  - `verify` must be on `KGIRL_VERIFY_ALLOWLIST`, and verifiers run without secret-named environment variables.
  - `apply` needs `KGIRL_MCP_APPLY=1` and an indexed repo root.
  - The protocol version is negotiated, and the server sends instructions.
  - The README notes that `skills_forge` (from `main`) also writes to Soup and isn't covered.
- **`claude/porter-blast-radius`:**
  - `context-relay/` copied from myAssistant (two sync commits)
  - `docs/harness/PORTER.md`
  - `.claude/skills/mcp-builder-hardened` as a symlink into `context-relay/` (Claude Code follows symlinked skill folders)

### 2.3 patern-coding (Porter)
**#2:** `steer`, `answer` and `retire` run from an agent's shell become proposals. Only `porter confirm` or `porter reject` resolves them, and both require your terminal, an interactive stdin, and typing `confirm`. The brief keeps the `via` label on user decisions. Messages from a shell are attributed to the shell.

### 2.4 Review of the latest commits (2026-09-27 → 30)

| Repo | Result |
|---|---|
| nonsense-hotline | 4 gaps (see §3) |
| see-n_say_the_techbro_says | clean: the API key is used only in a build script and never reaches the web page |
| KoLd__FEEt | clean: CI is read-only and doesn't pass PR text into shell commands |
| VIbe_coder, The_St, astro_caster | no secrets in recent commits |
| kgirl root clutter | **intentional**: kgirl's HANDOFF §3 says keep it |

## 3. Open findings

| ID | Where | Finding | Level | Proposed fix |
|---|---|---|---|---|
| KFM-11 | kgirl `harness/skills.py` (`80f8b85`, on `main`) | The forge writes goal text, which a model supplies through `jev_swarm_task`, into `SKILL.md` with newlines intact, so it can add sections. It counts **staged** trajectories, and so does `Intuition.from_soup`. MCP `skills_forge` stores `active` skills with thresholds the caller picks | L1 | **Fix open in kgirl#59** (parallel session): `inline()`, active-only, staged skills, MCP floors. Modeled as C-FORGE-* (proposed) in `09c0eac` |
| KFM-12 | kgirl `jev/swarm.py` `_learn` | A `jev_swarm_task` goal persists in an `active` trajectory outside the curator. It is recalled, replayed by intuition, and exportable by the forge. This loop stays open even with #59 | L1 (from `09c0eac`) | C-STAGE-TRAJECTORY: store MCP-started trajectories `staged` with `source="mcp"` |
| KFM-05 / -07 | kgirl | Context packs go to the scout model unredacted. Bare-name import guesses aren't recorded as such | L1 / L0 | `C-REDACT`; a `resolution` column in `imports` |
| NH-1 | nonsense-hotline `web.py` | No inbound SMS webhook: texting STOP to the hotline number does nothing | L1 (legal weight: ask counsel) | Twilio inbound handler that calls the existing opt-out path |
| NH-2 | nonsense-hotline `dispatcher.py show_letters` | Letter text, user agent and IP are printed to the terminal unfiltered (escape-code injection) | L1 | Strip C0/C1 control characters before printing |
| NH-3 / -4 | nonsense-hotline | Rate limits live in process memory. An opt-out is missed if its ElevenLabs webhook is lost | L1 | Shared store; periodic reconciliation |
| DRIFT | `examples/kgirl-harness.model.json` | **Resolved in `09c0eac`:** the model covers `main` and maps all 15 tools; a contract test compares them with `mcp_server._tools()`. **Remaining:** the #55 controls still read `proposed`, and `C-APPLY-CONFIRM` overstates the opt-in | L0 | §7.2(a) |

## 4. User preferences (binding)

1. **Publishing and PRs.** Nothing is published (npm, Chrome Web Store, releases) without Checkpoint C approval. PRs and merges happen when you ask: never open or merge one on your own initiative. kgirl's HANDOFF §3.5 says the same.
2. **Repo hygiene:**
   - Conventional Commits.
   - No secrets or archives in git.
   - Verify platform facts against the docs and log decisions.
   - In kgirl, never delete or clean copies, vendored duplicates or root clutter (HANDOFF §3.1).
3. **Style.** Dense, structured, explicit evidence levels, no marketing. In kgirl, randomness comes from chaos maps, never `random` (§3.2). You value emergent mechanisms and your own vocabulary (Porter, nihil, Meeseeks).
4. **Canonical source.** `context-relay/` is canonical in myAssistant. Other repos carry a synced copy at the same path.

## 5. Critique: three places I could have operated more efficiently

1. **I acted on stale remote state.**
   - In myAssistant, I pushed two commits and planned to update PR #1's description. Only then did I find that #1 had merged at 00:14, before my push. My rebase and force-push was denied, which cost a round trip and left the branch with already-merged history underneath (harmless).
   - In kgirl, I worked from a clone at `26748c4` while `main` had moved on: #54, #56 and #57 merged. I found out only at commit time, which made me merge into #55 and review `80f8b85` late.
   - One `git ls-remote` and one PR-state read at the start of each repo task would have caught both.
2. **I misread the `git subtree` failure.** Its first stderr line said `ambiguous argument`, but I acted on the last line ("working tree has modifications"), refreshed the index, and ran it again. Yet I already knew from the survey that kgirl tracks a root file named `HEAD`. Reading the whole error once would have saved two runs and pointed straight to the plumbing approach.
3. **I wrote checker heuristics before running them on real code.** `blast_radius_check.py` went through several false-positive rounds, each needing a fix and a re-run, and the zip had to be rebuilt after the rules settled. The false positives were:
   - kgirl's CLI `args`
   - `_git(args)`
   - Porter's `inputs` and `payload` parameters
   - `re.findall`

   Running it over the five target codebases first and writing rules from what appeared would have cut the loop. kgirl's own HANDOFF §4.2 records the same lesson.

## 6. Critique: three things I could have improved

1. **The core deliverable stalled without my saying so.** The original task was the Context Relay build, which has phases and Checkpoints A, B and C. It is still Phase 0 design input: D-006 to D-017 are all pending Checkpoint A, and no `ctxr` code exists. Your redirect to Porter was legitimate, but I never put Checkpoint A to you as a decision. Also, `context-relay/README.md` still says the directory "contains no product code", though it now holds the Porter plugin.
2. **Models drift from code because nothing ties them together.**
   - The kgirl model describes a harness that `main` has already outgrown.
   - `C-APPLY-CONFIRM` says the user "confirms outside the model". #55 actually implements a standing opt-in (`KGIRL_MCP_APPLY=1`), which is weaker than confirming each apply. The model overstates the control.

   A contract test, run with `KGIRL_SRC`, that compares `mcp_server._tools()` names with the model's components would catch both.
3. **I chose breadth over closure.**
   - The session ends with four repos, two open PRs, two branches with no PR, and three reported but unfixed issues (KFM-11, NH-1, NH-2).
   - Several conclusions are L1 only:
     - the nonsense-hotline opt-out point, which needs a lawyer
     - patern-coding#2's live check
     - any live-model run of the kgirl harness
     - the checker's JS half, which is regex, not a parser

   An earlier status table, and asking you sooner which loops to close, would have produced fewer, finished pieces.

## 7. Next session: three strategies

1. **Boot sequence (first five minutes).** Check state before you act:
   ```bash
   cd ~/myAssistant && git fetch origin && git log --oneline origin/main..origin/claude/focused-maxwell-ao65tc
   git -C ~/kgirl ls-remote origin refs/heads/main refs/heads/claude/harness-safety-patches refs/heads/claude/porter-blast-radius
   # the kgirl clone fetches only one branch by default, so name refs: git fetch origin +refs/heads/main:refs/remotes/origin/main
   # PR states: myAssistant (new PR?), kgirl#55, kgirl porter branch, patern-coding#2
   cd ~/myAssistant/context-relay && node tools/relay-model.mjs check && node --test tools/*.test.mjs plugins/porter-blast-radius/test/*.test.mjs
   python3 -m unittest discover -s skills/mcp-builder-hardened/scripts -p "test_*.py"
   ```
   If a PR merged, start follow-up work from the latest `main`. Never force-push: auto mode denies it, and merging `main` in keeps other people's checkouts valid.
2. **Close the open loops in this order. Ask before starting each one.**
   - **(a) #55 is merged, so update the model.** In myAssistant:
     - Set `C-STAGE-MCP`, `C-VERIFY-ALLOWLIST` and `C-VERSION-NEGOTIATION` to `implemented`.
     - Reword `C-APPLY-CONFIRM` to the real mechanism, a standing `KGIRL_MCP_APPLY=1` opt-in.
     - Update the pinned expectations in `test/kgirl-model.test.mjs` and re-run `risk_register` with `as_built`.
     - Then run `sh context-relay/tools/sync-subtree.sh` in kgirl. Its default, myAssistant `main`, now has everything.
   - **(b) kgirl#59.** Review it, then decide whether to merge. Once it merges, set its C-FORGE-* controls to `implemented` the same way.
   - **(c) KFM-12.** C-STAGE-TRAJECTORY, as one small kgirl PR.
   - **(d) Checkpoint A** for Context Relay: the name, plus D-006 to D-017 for approval. Phase 1 code starts only after that.
   - **(e) nonsense-hotline:** NH-1 (STOP handler) and NH-2 (strip control characters).
3. **Working rules that would have saved time here:**
   - Edit `context-relay/` only in myAssistant, and sync with the script. Never run `git subtree` in kgirl, and never touch its root `HEAD`, `FETCH_HEAD`, `config`, `index` or venv shims. Those files make bare `HEAD` and `FETCH_HEAD` ambiguous, so use full refs (`refs/remotes/origin/main`) or `--`.
   - **Other sessions push to the same branches.** On 2026-10-01 a parallel session duplicated a sync and a doc edit within minutes. Run `git ls-remote` immediately before each push, merge with `expectedHeadSha`, and pull in what's new instead of redoing it.
   - Run a tool on real data before writing its rules or tests.
   - Read the whole stderr once before retrying.
   - Label every claim L0 to L3, and say "not verified" out loud.
   - After merging or syncing, re-run the suites in the receiving repo. In kgirl, set `KGIRL_SRC=$PWD/src` so the Atlas contract test actually runs.

## 8. Map

```
myAssistant/
  HANDOFF.md                                   this file
  context-relay/
    model/relay-model.json  tools/relay-model.mjs(+test)  tools/sync-subtree.sh(+test)
    docs/  WORKFLOWS  BLAST_RADIUS  DECISIONS (D-006..017)  PLATFORM_NOTES_ADDENDUM (PN-01..15)  KGIRL_HARNESS
    .claude-plugin/marketplace.json            marketplace "porter"
    plugins/porter-blast-radius/               lib/ engine discover atlas fsguard · server/ index tools · model/ · examples/ · test/
    skills/mcp-builder-hardened/               SKILL.md  reference/blast_radius_review.md  scripts/blast_radius_check.py(+test)  NOTICE.md
kgirl/      main has #55 and #58: context-relay/, docs/harness/PORTER.md, .claude/skills/mcp-builder-hardened → symlink · #59 open
patern-coding/  main has #2
```

**Environment notes:**
- Only the pushed branches and the delivered zip outlive this container. Everything else here is temporary:
  - the scratchpad worktree of kgirl
  - the local branch `porter-context-relay-split` in myAssistant (safe to delete)
  - the `/home/user/9x25dillon/` survey clones
- The Gmail connector needs authorizing in claude.ai's connector settings before any session can use it.
