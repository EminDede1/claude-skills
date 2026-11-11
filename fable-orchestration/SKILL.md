---
name: fable-orchestration
description: "Delegation policy for a multi-model agent stack where the main loop runs on a strong but expensive model (e.g. Claude Fable 5.2). The main loop orchestrates, writes briefs and synthesizes; the work is routed by difficulty. Medium-high difficulty goes to Opus with a fairly loose brief; simple-medium goes to Sonnet with a tighter brief. GPT-side execution goes to gpt-6.1-sol with a detailed step-by-step brief; second opinions and out-of-the-box thinking go to gpt-6-astra. Very large data cleanup goes to Claude Haiku 5.5 or gpt-6-luna. Load whenever spawning sub-agents (Agent tool, Workflow agent() calls, codex fleets) or planning any delegation."
---

# Orchestration & delegation policy (expensive-main-loop stack)

A routing policy for stacks with **one strong, expensive main-loop model** and
**cheaper delegate tiers**. Written against a Claude Fable 5.2 main loop with
Opus, Sonnet and Haiku sub-agents and Codex lanes, but the shape transfers to
any stack with the same economics.

Core law: **the expensive model's tokens buy judgment, not throughput.** It
writes the plan, the briefs, the hard calls and the final synthesis.
Everything else goes to the cheapest tier that can carry it.

## The routing table

| Work | Goes to | How to call it | Brief style |
|---|---|---|---|
| Architecture, specs, hard judgment, integration, final synthesis | **Main loop** (Fable) | itself | n/a |
| Medium-high difficulty: multi-file implementation, real debugging, research that needs judgment, review and verification | **Opus** | `model: 'opus'` | Fairly loose: goal, context, constraints, what done looks like |
| Simple-medium: scoped edits, pattern clones, lookups, templated work, straightforward reading and summarizing | **Sonnet** | `model: 'sonnet'` | A notch tighter: named files, steps, output shape, boundaries |
| GPT-side execution, when the operator asks to send work to GPT | **gpt-6.1-sol** | `codex exec -m gpt-6.1-sol` | Detailed and step by step, nothing left implicit |
| Second opinion, out-of-the-box thinking, an angle the main loop may be missing | **gpt-6-astra** | `codex exec -m gpt-6-astra` | The open question plus the evidence, as to a peer |
| Very large data cleanup: thousands of rows or files, normalizing, deduplicating, classifying, extracting | **Claude Haiku 5.5** or **gpt-6-luna** | `model: 'haiku'` / `codex exec -m gpt-6-luna` | Exact rule set with input and output examples, small batches, spot checks |

## The hard rules

1. **Always pass an explicit `model:`** on every Agent tool call, Workflow
   `agent()` call and `meta.phases` entry. Omitting it inherits the main-loop
   model and silently fans out your most expensive tier.
2. **The main-loop model is not a sub-agent tier.** Spawn it as a sub-agent
   only when the operator names it for that task, or when a rare
   judgment-heavy piece genuinely fails on Opus.
3. **Route by difficulty, then pick the cheapest tier that can carry it.**
   When unsure between two tiers, take the cheaper one and verify the result;
   escalate one tier on failure rather than starting high.
4. **The quota mode decides the Claude/GPT split.** Before planning a
   delegation, run the quota check (see "Quota-aware routing" below) and follow
   the mode it returns. With no Codex login, the mode is `claude-only` and
   Claude tiers carry everything.
5. **The main loop keeps its own context lean.** Wide reading, file dumps and
   raw data go to a delegate that returns the conclusion; the main loop reads
   what it must judge. Small things (a handful of tool calls, one known file)
   it does itself, since a delegation costs more than it saves there.
6. **A delegate's report is a claim.** Check the diff, the output or a sample
   before reporting it as done.

## Brief shape per tier

How tightly to write depends on who reads it.

- **Opus (fairly loose).** State the goal and why it matters, the context it
  cannot discover on its own, the constraints, and what done looks like. Leave
  the route to it. Over-specifying an Opus brief costs tokens and removes the
  judgment you are paying for.
- **Sonnet (a notch tighter).** Name the files or area, list the steps in
  order when order matters, give the output format, and say what not to touch.
  Say when to stop and report instead of improvising. One task per agent.
- **gpt-6.1-sol (detailed, complete).** Sol is a soldier: it does exactly
  what the brief says, step by step, with nothing skipped and nothing added.
  That makes the brief the whole quality ceiling. Write numbered steps,
  exact paths and commands, the acceptance check for each step, the edge cases
  and what to do in each, and the things that are out of scope. Anything left
  unsaid will not happen. Do not ask it to "use judgment" on an open design
  question; decide that first, then hand it the decision.
- **gpt-6-astra (peer question).** Give it the problem, the evidence, the
  options you see and where you are unsure, and ask for what you may be
  missing. Do not hand it your conclusion to confirm. Treat the answer as a
  peer review and disagree on evidence. Medium or high effort; `xhigh` or
  `max` only when the question justifies it.
- **Haiku 5.5 / gpt-6-luna (bulk).** One mechanical rule set, stated exactly,
  with two or three input and output examples. Split the data into batches
  small enough that a bad batch is cheap to redo, have each batch write to its
  own output file, and sample the results before merging. Never ask this tier
  to decide what the rules should be.

Long briefs go in a file; the prompt points at the file.

## Codex lanes

GPT lanes run through `codex exec` (recipe in [`codex-fleet`](../codex-fleet/SKILL.md)).
Execution lanes run on `-m gpt-6.1-sol`, that skill's default; pass
`-m gpt-6-astra` for second opinions and `-m gpt-6-luna` for bulk cleanup. Effort: `medium` for
routine lanes, `high` for precision lanes, `xhigh` or `max` only for an
explicitly heavy lane. When assigning fleet lanes, stamp the model per lane in
the spec so the launch is mechanical and no routing decision happens at spawn
time.

## Quota-aware routing

The operator has a Claude plan and a ChatGPT plan (Codex). Work goes to the
side with more headroom. The main-loop model (Fable or Opus) is chosen by the
operator when the session opens; this section only routes the delegates.

**At session start and before each delegation wave:**

1. Check the Codex login: `codex login status`. In a cloud session the ChatGPT
   login does not survive a new container. If it does not say "Logged in using
   ChatGPT", start `codex login --device-auth` in the background, give the
   operator the link and one-time code, and continue in `claude-only` until it
   completes. Never ask for the email or password.
2. Read the Claude side: call `get_session` (claude-code-remote) with no
   session_id and take `external_metadata.rate_limit_info.status` and
   `isUsingOverage`. If that tool is missing, pass `unknown`.
3. Run the check with those values. The script sits in `scripts/` next to this
   file: `~/.claude/skills/fable-orchestration/` when installed for the user,
   `.claude/skills/fable-orchestration/` inside a project.
   `python3 <skill dir>/scripts/quota_check.py --claude-status <status> [--claude-overage]`
   It reads the ChatGPT plan's 5-hour and weekly usage through
   `codex app-server` and prints a `mode`.

**Modes:**

| Mode | When | Routing |
|---|---|---|
| `balanced` | Both sides healthy | Routing table as written; GPT-suitable execution lanes go to sol without waiting for the operator to ask, bulk to luna, second opinions to astra |
| `gpt-first` | Claude warns or is on overage | Every delegable lane goes to Codex (sol for execution, luna for bulk); Claude sub-agents only for work that needs this session's tools |
| `claude-first` | Codex usage at 70% or more | Claude tiers by default; Codex only for astra second opinions |
| `claude-only` | Codex not logged in, unreachable, or at 90% | No Codex lanes |
| `gpt-only` | Claude limit reached | Codex carries all delegated work; the main loop only writes briefs and checks results |

Re-run the check after a long wave or when either side reports a limit
warning, and tell the operator in one line when the mode changes.

## Exceptions

- If the operator explicitly names a model for a scoped task, honor it for that
  task only, then return to this policy.
- The operator can override any of this per session; absent that, this policy
  stands.
