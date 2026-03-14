# OpenClaw Skills — garrettekinsman

Public skill library for [OpenClaw](https://docs.openclaw.ai). Each skill is a self-contained OpenClaw agent extension — drop it in your `~/.openclaw/workspace/skills/` folder and it's ready to use.

All skills are signed with `garrett@garrettekinsman.com` (ED25519). Verify with the `SIGNERS` file inside each skill.

---

## Skills

### 🔬 [pbar](./pbar/) — Population-Based Annealed Research
Autonomous AI-driven experiment loop for ML research. Runs parallel research branches with softmax selection and temperature annealing. Designed for Apple Silicon (MLX) but architecture-agnostic.

- **Use when:** running autonomous research loops, optimizing hyperparameters, iterating ML experiments overnight
- **Requires:** `uv`, Apple Silicon (MLX)
- **Skill file:** [`pbar/pbar.skill`](./pbar/pbar.skill)

### 🔁 [research-loops](./research-loops/) — Multi-Sprint Research Loops
Timed, adversarial, multi-sprint research on local GPU compute. Opus orchestrates; local model (qwen3-coder 80B) researches. Sanitized pipeline — local model output never reaches Claude unverified.

- **Use when:** deep-dive investigations, financial analysis, geopolitical research, any task needing sustained multi-sprint AI research
- **Requires:** Ollama + LiteLLM, capable local model (qwen3-coder recommended), Tailscale or LAN access to compute node
- **Skill file:** [`research-loops/research-loops.skill`](./research-loops/research-loops.skill)

---

## Install a Skill

```bash
# Clone this repo
git clone https://github.com/garrettekinsman/Skills ~/.openclaw/workspace/skills-public

# Symlink the skill you want
ln -s ~/.openclaw/workspace/skills-public/pbar ~/.openclaw/workspace/skills/pbar
```

Or copy the `.skill` file directly into OpenClaw via the skills interface.

## Verify Signatures

```bash
cd pbar
ssh-keygen -Y verify -f SIGNERS -I garrett@garrettekinsman.com \
  -n openclaw-skill -s pbar.skill.sig < pbar.skill
```

## License

MIT — see `LICENSE` in each skill folder.
