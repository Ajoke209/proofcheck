ProofCheck 🔍
An AI agent that tells you why a crypto project looks safe or risky
Open Agent Hackathon 2026 · Track 2: The Agent That Can Explain Why
Built by Firdaus Adekeye (@Ajoke209), Lagos, Nigeria
The problem
Millions of new crypto users, especially across Africa, decide what to buy from hype on X and Telegram. Rug pulls, honeypot tokens and abandoned projects cost them real money. Existing "risk scores" give you a number with no reasoning, so you can't tell whether to trust the score itself.
The solution
ProofCheck is an agent that investigates a project the way a careful analyst would, then shows its work:
every piece of evidence it found
how much that evidence moved the score, and in which direction
why that evidence matters, in plain English
the source link so you can verify it yourself
what would change its mind (counterfactuals)
and it refuses to guess: if the data isn't there, it says "Not enough evidence"
How the agent reasons
PLAN: decides which checks fit the project
GATHER: pulls live evidence from 4 public sources (CoinGecko, GoPlus Security, DeFiLlama, GitHub)
REASON: turns each finding into a Signal {check, finding, effect ±, why, source}
VERDICT: score = 50 + sum of effects → LOW / MEDIUM / HIGH RISK
EXPLAIN: top reasons + "what would change my mind" + a summary grounded only in the evidence (Gemini, optional)
Every step is printed live as an agent trace ([PLAN], [GATHER], [REASON], [VERDICT], [EXPLAIN]).
Why it's explainable by design
Transparent rules, not a black box. Each signal has a fixed, readable weight.
Evidence-locked language model. The LLM only writes the summary and may use nothing but the evidence list, so it can't hallucinate facts.
Citations on every claim. Every signal carries its source URL.
Counterfactuals. The agent states what evidence would flip its verdict.
Honest uncertainty. Too little data → "NOT ENOUGH EVIDENCE" instead of a fake score.
Run it (no coding needed)
Click the Open in Colab button above.
Click Runtime → Run all.
Type a project name (e.g. aave, pepe, chainlink) when asked.
Optional: add a free Gemini API key from https://aistudio.google.com/apikey for a natural-language summary.
Or locally: pip install requests && python proofcheck.py aave
Data sources (all free, no keys)
Source
What it tells the agent
CoinGecko API
market rank, liquidity, supply unlocks, age, links
GoPlus Security API
honeypot, hidden mint/owner powers, taxes, whale concentration
DeFiLlama API
total value locked, audit reports
GitHub API
whether developers are still shipping
Google Gemini (optional)
plain-English summary grounded in the evidence
What's next
Telegram/WhatsApp bot so users can check a token before buying
Hausa, Yoruba and Pidgin explanations
Social signal checks (bot followers, paid-promo detection)
ProofCheck is an educational tool and not financial advice.
