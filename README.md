# claude-skills

Personal Claude Code skills, installed into `~/.claude/skills/` so they load in every project.

## Skills

- **fable-orchestration**: delegation policy for a main loop (Fable or Opus) that builds a team from Claude sub-agents and Codex (GPT) lanes, routing by difficulty and by which plan has more quota left (`scripts/quota_check.py`).

## Install

On your own computer (macOS / Linux):

```bash
mkdir -p ~/.claude/skills && curl -fsSL https://codeload.github.com/EminDede1/claude-skills/tar.gz/main | tar xz -C /tmp && cp -r /tmp/claude-skills-main/fable-orchestration ~/.claude/skills/ && rm -rf /tmp/claude-skills-main
```

In a Claude Code cloud environment, put the same steps in the environment's setup script and allow the host `codeload.github.com`.

Codex lanes need the Codex CLI (`npm install -g @openai/codex`) and a ChatGPT login (`codex login --device-auth`).
