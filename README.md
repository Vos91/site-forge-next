# 🏗️ SiteForge Next

**Autonomous website builder** powered by Claude Agent SDK + Playwright MCP.
**Next.js edition** — generates production-ready Next.js sites with App Router + TypeScript + Tailwind CSS.

Geïnspireerd door [Anthropic's harness design blog](https://www.anthropic.com/engineering/harness-design-long-running-apps). Geef een prompt, krijg een volledige website terug — gebouwd door drie gespecialiseerde AI agents.

## Hoe het werkt

```
[Jouw prompt] → Planner → Generator → Evaluator → 🔁 → Website
                  │            │            │
                  │            │            └── Klikt door de site via Playwright
                  │            │                Graded op 4 criteria
                  │            │                Stuurt feedback terug
                  │            └── Bouwt de site feature-by-feature
                  │                Next.js + TypeScript + Tailwind
                  │                Git commits per feature
                  └── Maakt een uitgebreide product spec
                      van jouw korte prompt
```

### De drie agents

1. **Planner** — Neemt je 1-4 zin prompt en maakt er een volledige product spec van
2. **Generator** — Bouwt de site feature-by-feature met Next.js App Router, commit na elke feature
3. **Evaluator** — Test de live site via Playwright MCP, graded op 4 criteria, stuurt feedback

### Grading criteria

- **Design Quality** — Voelt het als een samenhangend geheel?
- **Originality** — Eigen keuzes of AI-template slop?
- **Craft** — Typografie, spacing, kleurharmonie
- **Functionality** — Kan een gebruiker het begrijpen en gebruiken?

## Setup

### Met Claude Max (aanbevolen)

```bash
# 1. Clone
git clone https://github.com/Vos91/site-forge-next.git
cd site-forge-next

# 2. Install dependencies
pip install -r requirements.txt

# 3. Zorg dat je ingelogd bent met Claude Code
claude login

# 4. Run
python forge.py "Een portfolio site voor een fotograaf" --skip-eval
```

## Opties

| Flag | Beschrijving | Default |
|------|-------------|---------|
| `--output-dir` | Output directory | `./output` |
| `--max-iterations` | Max evaluator iteraties | `5` |
| `--model` | Claude model | `claude-sonnet-4-5` |
| `--skip-eval` | Skip evaluator (sneller, minder tokens) | `false` |
| `--planner-only` | Alleen de spec genereren, niet bouwen | `false` |
| `--verbose` | Toon alle agent output | `false` |
| `--live` | Real-time streaming van agent activiteit | `false` |

## Stack

Gegenereerde sites gebruiken:
- **Next.js (latest)** met App Router
- **TypeScript**
- **Tailwind CSS**
- `next/image`, `next/link`, `next/font`

## Vereisten

- Python 3.10+
- Claude Code SDK (`pip install claude-code-sdk`)
- Node.js 18+ (voor de gegenereerde sites)
- Claude Max abo OF Anthropic API key

## Licentie

MIT
