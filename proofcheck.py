"""
ProofCheck: an AI agent that explains WHY a crypto project looks safe or risky.

Open Agent Hackathon 2026, Track 2: "The Agent That Can Explain Why".

How it works (plain English):
  1. PLAN    - the agent decides which checks to run for the project you name.
  2. GATHER  - it pulls live evidence from free public sources:
                 CoinGecko (market + project links), DeFiLlama (TVL + audits),
                 GoPlus Security (smart-contract red flags), GitHub (dev activity).
  3. REASON  - every piece of evidence becomes a "signal" with a weight,
               a plus or minus effect, the reason it matters, and its source link.
  4. VERDICT - signals add up to a 0-100 trust score and a risk level.
  5. EXPLAIN - the agent shows its full chain of reasoning, the top reasons,
               what would change its mind, and (optionally) a Gemini-written
               summary that is only allowed to use the collected evidence.
"""

import json
import os
import sys
import time
from dataclasses import dataclass, asdict, field

import requests

UA = {"User-Agent": "ProofCheck/1.0 (Open Agent Hackathon 2026)"}
GOPLUS_CHAINS = {"ethereum": "1", "binance-smart-chain": "56", "polygon-pos": "137",
                 "arbitrum-one": "42161", "base": "8453", "optimistic-ethereum": "10",
                 "avalanche": "43114"}


# ---------------------------------------------------------------- data shapes
@dataclass
class Signal:
    check: str          # what was checked
    finding: str        # what the agent found
    effect: int         # points added (+) or removed (-) from the trust score
    why: str            # why this matters, in plain English
    source: str         # where the evidence came from (link)


@dataclass
class Report:
    query: str
    project: str = ""
    symbol: str = ""
    plan: list = field(default_factory=list)
    trace: list = field(default_factory=list)      # step-by-step agent log
    signals: list = field(default_factory=list)
    score: int = 50
    verdict: str = ""
    top_reasons: list = field(default_factory=list)
    would_change_mind: list = field(default_factory=list)
    summary: str = ""


def get(url, params=None, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=25)
            if r.status_code == 429:          # rate-limited: wait and retry
                time.sleep(8 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception:
            time.sleep(1.5)
    return None


# ---------------------------------------------------------------- the agent
class ProofCheckAgent:
    def __init__(self, gemini_key=None):
        self.gemini_key = gemini_key or os.environ.get("GEMINI_API_KEY")

    def log(self, rep, step, msg):
        line = f"[{step}] {msg}"
        rep.trace.append(line)
        print(line)

    def add(self, rep, **kw):
        s = Signal(**kw)
        rep.signals.append(s)
        sign = "+" if s.effect >= 0 else ""
        self.log(rep, "REASON", f"{s.check}: {s.finding} -> {sign}{s.effect} ({s.why})")

    # ---- 1. PLAN
    def run(self, query):
        rep = Report(query=query)
        self.log(rep, "PLAN", f"Investigating '{query}'.")
        found = get("https://api.coingecko.com/api/v3/search", {"query": query})
        coins = (found or {}).get("coins", [])
        if not coins:
            rep.verdict = "UNKNOWN"
            rep.summary = "No listed token matched this name. Unlisted projects deserve extra caution."
            self.log(rep, "VERDICT", rep.summary)
            return rep
        coin_id = coins[0]["id"]
        rep.plan = ["Market & listing data (CoinGecko)", "Smart-contract security (GoPlus)",
                    "TVL & audits (DeFiLlama)", "Developer activity (GitHub)",
                    "Weigh signals -> score", "Explain verdict"]
        self.log(rep, "PLAN", f"Matched CoinGecko id '{coin_id}'. Plan: " + " | ".join(rep.plan))

        # ---- 2. GATHER + 3. REASON
        coin = self.check_market(rep, coin_id)
        if coin:
            self.check_contract(rep, coin)
            self.check_defi(rep, coin_id)
            self.check_github(rep, coin)

        # ---- 4. VERDICT
        if len(rep.signals) < 2:
            rep.verdict = "NOT ENOUGH EVIDENCE"
            rep.summary = ("The data sources didn't return enough evidence to judge this project. "
                           "Wait a minute and run it again. An agent that can't explain why shouldn't guess.")
            self.log(rep, "VERDICT", rep.summary)
            return rep
        rep.score = max(0, min(100, 50 + sum(s.effect for s in rep.signals)))
        rep.verdict = ("LOW RISK" if rep.score >= 70 else
                       "MEDIUM RISK" if rep.score >= 45 else "HIGH RISK")
        self.log(rep, "VERDICT", f"Trust score {rep.score}/100 -> {rep.verdict}")

        # ---- 5. EXPLAIN
        ranked = sorted(rep.signals, key=lambda s: abs(s.effect), reverse=True)
        rep.top_reasons = [f"{'+' if s.effect >= 0 else ''}{s.effect}  {s.check}: {s.finding}"
                           for s in ranked[:4]]
        rep.would_change_mind = self.counterfactuals(rep)
        rep.summary = self.summarise(rep)
        return rep

    # ---- individual checks
    def check_market(self, rep, coin_id):
        url = f"https://www.coingecko.com/en/coins/{coin_id}"
        self.log(rep, "GATHER", "Fetching market & listing data from CoinGecko")
        c = get(f"https://api.coingecko.com/api/v3/coins/{coin_id}",
                {"localization": "false", "tickers": "false", "market_data": "true",
                 "community_data": "false", "developer_data": "false"})
        if not c:
            self.log(rep, "GATHER", "CoinGecko unavailable, skipping market checks")
            return None
        rep.project, rep.symbol = c.get("name", ""), c.get("symbol", "").upper()
        md = c.get("market_data", {}) or {}
        mcap = (md.get("market_cap") or {}).get("usd") or 0
        vol = (md.get("total_volume") or {}).get("usd") or 0
        rank = c.get("market_cap_rank")

        if rank and rank <= 100:
            self.add(rep, check="Market rank", finding=f"#{rank} by market cap", effect=12,
                     why="top-100 projects face heavy public scrutiny and deep liquidity", source=url)
        elif rank and rank <= 500:
            self.add(rep, check="Market rank", finding=f"#{rank} by market cap", effect=5,
                     why="established but less scrutinised than the top 100", source=url)
        else:
            self.add(rep, check="Market rank", finding=f"rank {rank or 'unranked'}", effect=-8,
                     why="small or unranked tokens are easier to manipulate", source=url)

        if mcap:
            ratio = vol / mcap
            if ratio > 1.0:
                self.add(rep, check="Volume vs market cap", finding=f"24h volume is {ratio:.1f}x market cap",
                         effect=-10, why="volume above market cap often signals wash trading or a pump", source=url)
            elif ratio < 0.002:
                self.add(rep, check="Volume vs market cap", finding=f"24h volume only {ratio:.2%} of market cap",
                         effect=-5, why="thin trading means you may not be able to exit", source=url)
            else:
                self.add(rep, check="Volume vs market cap", finding=f"healthy ratio ({ratio:.1%})",
                         effect=4, why="liquidity looks organic", source=url)

        fdv = (md.get("fully_diluted_valuation") or {}).get("usd")
        if fdv and mcap and fdv / mcap > 3:
            self.add(rep, check="Token unlocks", finding=f"FDV is {fdv / mcap:.1f}x circulating market cap",
                     effect=-7, why="most supply is still locked; future unlocks can pressure price", source=url)

        genesis = c.get("genesis_date")
        if genesis and genesis[:4].isdigit() and int(genesis[:4]) <= 2021:
            self.add(rep, check="Project age", finding=f"live since {genesis}", effect=6,
                     why="it has survived at least one full market cycle", source=url)

        links = c.get("links", {}) or {}
        if not [h for h in links.get("homepage", []) if h]:
            self.add(rep, check="Website", finding="no official website listed", effect=-6,
                     why="legitimate projects publish an official site", source=url)
        c["_url"] = url
        return c

    def check_contract(self, rep, coin):
        platforms = {k: v for k, v in (coin.get("platforms") or {}).items() if v}
        target = next(((ch, addr) for ch, addr in platforms.items() if ch in GOPLUS_CHAINS), None)
        if not target:
            self.log(rep, "GATHER", "No EVM contract found (native coin or unsupported chain); skipping contract scan")
            return
        chain, addr = target
        src = f"https://gopluslabs.io/token-security/{GOPLUS_CHAINS[chain]}/{addr}"
        self.log(rep, "GATHER", f"Scanning {chain} contract {addr[:10]}... with GoPlus Security")
        d = get(f"https://api.gopluslabs.io/api/v1/token_security/{GOPLUS_CHAINS[chain]}",
                {"contract_addresses": addr})
        t = ((d or {}).get("result") or {}).get(addr.lower())
        if not t:
            self.log(rep, "GATHER", "GoPlus had no data for this contract")
            return
        flag = lambda k: str(t.get(k, "0")) == "1"
        if flag("is_honeypot"):
            self.add(rep, check="Honeypot test", finding="token can be bought but NOT sold", effect=-40,
                     why="this is a classic scam pattern", source=src)
        if t.get("is_open_source") == "0":
            self.add(rep, check="Source code", finding="contract code is not verified", effect=-12,
                     why="hidden code can contain backdoors", source=src)
        elif t.get("is_open_source") == "1":
            self.add(rep, check="Source code", finding="contract code is verified and public", effect=5,
                     why="anyone can audit what the token does", source=src)
        if flag("is_mintable") and flag("owner_change_balance"):
            self.add(rep, check="Owner powers", finding="owner can mint and change balances", effect=-15,
                     why="the team could inflate supply or drain wallets", source=src)
        elif flag("is_mintable"):
            self.add(rep, check="Owner powers", finding="new tokens can be minted", effect=-4,
                     why="supply can grow, diluting holders", source=src)
        for k, label in (("buy_tax", "Buy tax"), ("sell_tax", "Sell tax")):
            try:
                tax = float(t.get(k) or 0)
            except ValueError:
                tax = 0
            if tax > 0.1:
                self.add(rep, check=label, finding=f"{tax:.0%}", effect=-10,
                         why="high taxes trap or drain traders", source=src)
        holders = t.get("holders") or []
        top10 = sum(float(h.get("percent", 0)) for h in holders[:10]
                    if not h.get("is_contract") and not h.get("tag"))
        if top10 > 0.5:
            self.add(rep, check="Holder concentration", finding=f"top wallets hold {top10:.0%}", effect=-10,
                     why="a few wallets could dump on everyone else", source=src)
        if not any(s.check in ("Honeypot test", "Owner powers") for s in rep.signals):
            self.add(rep, check="Contract red flags", finding="no honeypot or owner backdoor detected",
                     effect=6, why="the most common rug-pull mechanics are absent", source=src)

    def check_defi(self, rep, coin_id):
        self.log(rep, "GATHER", "Looking up TVL and audits on DeFiLlama")
        protos = get("https://api.llama.fi/protocols") or []
        matches = [x for x in protos if x.get("gecko_id") == coin_id]
        p = max(matches, key=lambda x: x.get("tvl") or 0) if matches else None   # biggest version
        if not p:
            self.log(rep, "GATHER", "Not listed as a DeFi protocol on DeFiLlama")
            return
        src = f"https://defillama.com/protocol/{p.get('slug', '')}"
        tvl = p.get("tvl") or 0
        if tvl > 100_000_000:
            self.add(rep, check="Value locked (TVL)", finding=f"${tvl / 1e6:,.0f}M locked", effect=8,
                     why="users trust it with real money", source=src)
        elif tvl > 1_000_000:
            self.add(rep, check="Value locked (TVL)", finding=f"${tvl / 1e6:,.1f}M locked", effect=3,
                     why="some real usage", source=src)
        audits = str(p.get("audits") or "0")
        if audits in ("1", "2", "3") or p.get("audit_links"):
            self.add(rep, check="Security audits", finding=f"{len(p.get('audit_links') or [])} audit report(s) listed",
                     effect=7, why="independent reviewers checked the code", source=src)
        else:
            self.add(rep, check="Security audits", finding="no audit listed", effect=-6,
                     why="unaudited DeFi code is a common source of hacks", source=src)

    def check_github(self, rep, coin):
        repos = ((coin.get("links") or {}).get("repos_url") or {}).get("github") or []
        repos = [r for r in repos if "github.com/" in r]
        if not repos:
            self.add(rep, check="Open-source code", finding="no public GitHub listed", effect=-5,
                     why="you can't see if anyone is actually building", source=coin["_url"])
            return
        self.log(rep, "GATHER", f"Checking GitHub activity across {min(3, len(repos))} repo(s)")
        best = None
        for repo in repos[:3]:                      # take the most recently updated repo
            parts = repo.split("github.com/")[1].strip("/").split("/")
            if len(parts) >= 2:
                d = get(f"https://api.github.com/repos/{parts[0]}/{parts[1]}")
            else:
                rl = get(f"https://api.github.com/orgs/{parts[0]}/repos", {"sort": "pushed", "per_page": 1})
                d = rl[0] if isinstance(rl, list) and rl else None
            if d and "pushed_at" in d and (not best or d["pushed_at"] > best["pushed_at"]):
                best = d
        d = best
        if not d:
            return
        days = (time.time() - time.mktime(time.strptime(d["pushed_at"][:10], "%Y-%m-%d"))) / 86400
        src = d.get("html_url", repos[0])
        if days <= 30:
            self.add(rep, check="Developer activity", finding=f"code pushed {int(days)} days ago",
                     effect=6, why="the team is actively building", source=src)
        elif days > 180:
            self.add(rep, check="Developer activity", finding=f"no code pushed for {int(days)} days",
                     effect=-6, why="the project may be abandoned", source=src)

    # ---- explanation helpers
    def counterfactuals(self, rep):
        out, checks = [], {s.check for s in rep.signals}
        if "Security audits" not in checks or any(s.check == "Security audits" and s.effect < 0 for s in rep.signals):
            out.append("A published audit from a known firm would raise the score by about 13 points.")
        if any(s.check == "Holder concentration" for s in rep.signals):
            out.append("If top wallets held under 50% of supply, the score would rise by 10.")
        if any(s.check == "Developer activity" and s.effect < 0 for s in rep.signals):
            out.append("Fresh code commits in the last 30 days would add 12 points.")
        if rep.verdict == "LOW RISK":
            out.append("A failed honeypot test or hidden owner mint power would drop this to HIGH RISK instantly.")
        return out or ["More on-chain history would make the verdict more confident."]

    def summarise(self, rep):
        evidence = [asdict(s) for s in rep.signals]
        if self.gemini_key:
            prompt = ("You are a crypto due-diligence analyst. Using ONLY the evidence JSON below, "
                      "write 4-5 plain-English sentences for a beginner explaining the verdict "
                      f"'{rep.verdict}' (score {rep.score}/100) for {rep.project}. Name the biggest reasons, "
                      "say what would change the verdict, and do not add facts that are not in the evidence. "
                      "End with: 'Not financial advice.'\n\n" + json.dumps(evidence))
            try:
                r = requests.post(
                    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
                    params={"key": self.gemini_key},
                    json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=40)
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                self.log(rep, "EXPLAIN", "Gemini wrote a summary grounded in the evidence list")
                return text
            except Exception:
                self.log(rep, "EXPLAIN", "Gemini unavailable, using the built-in explainer")
        pos = [s for s in rep.signals if s.effect > 0]
        neg = [s for s in rep.signals if s.effect < 0]
        txt = f"{rep.project} scores {rep.score}/100, which is {rep.verdict}. "
        if pos:
            txt += "In its favour: " + "; ".join(f"{s.finding} ({s.why})" for s in sorted(pos, key=lambda s: -s.effect)[:3]) + ". "
        if neg:
            txt += "Against it: " + "; ".join(f"{s.finding} ({s.why})" for s in sorted(neg, key=lambda s: s.effect)[:3]) + ". "
        return txt + "Not financial advice."


def print_report(rep):
    if not rep.signals:
        print("\n" + rep.verdict + ": " + rep.summary)
        return
    print("\n" + "=" * 64)
    print(f" PROOFCHECK REPORT: {rep.project} ({rep.symbol})")
    print("=" * 64)
    print(f" Trust score: {rep.score}/100   Verdict: {rep.verdict}\n")
    print(" WHY - every signal, its weight and its source:")
    for s in rep.signals:
        print(f"  {'+' if s.effect >= 0 else ''}{s.effect:>3}  {s.check}: {s.finding}")
        print(f"        why: {s.why}\n        source: {s.source}")
    print("\n TOP REASONS:")
    for r in rep.top_reasons:
        print("  " + r)
    print("\n WHAT WOULD CHANGE MY MIND:")
    for r in rep.would_change_mind:
        print("  - " + r)
    print("\n SUMMARY:\n  " + rep.summary)
    print("=" * 64)


if __name__ == "__main__":
    name = " ".join(sys.argv[1:]) or input("Which crypto project should I check? ")
    report = ProofCheckAgent().run(name)
    print_report(report)
    with open("report.json", "w") as f:
        json.dump(asdict(report), f, indent=2, default=lambda o: asdict(o))
