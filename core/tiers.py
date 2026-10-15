"""Easy / medium / heavy work tiers: pay for the big model only where it matters.

Big jobs are split into steps; each step runs on the cheapest tier that can do it:
  easy   - mechanical: create folders, install packages, run a command, open things
  medium - small writing/edits, running tests, fixing simple errors, glue work
  heavy  - writing the substantial content: real code, long essays
Models come from the user's model configuration (Settings > Models: Easy/Medium/Hard).
"""
import re

TIER_ORDER = ("easy", "medium", "heavy")
LABELS = {"easy": "Easy", "medium": "Medium", "heavy": "Heavy"}
_ALIASES = {
    "easy": "easy", "simple": "easy", "simple_task": "easy", "easy_task": "easy",
    "medium": "medium", "moderate": "medium", "moderate_task": "medium", "medium_task": "medium",
    "heavy": "heavy", "hard": "heavy", "heavy_task": "heavy", "hard_task": "heavy",
}
# Per-step limits: tight for cheap tiers, roomy where whole files get written.
BUDGET = {
    "easy": {"max_steps": 6, "max_tokens": 1500},
    "medium": {"max_steps": 14, "max_tokens": 3500},
    "heavy": {"max_steps": 10, "max_tokens": 8000},
}
_CONFIG_KEY = {"easy": "easy", "medium": "medium", "heavy": "hard"}

# USD per 1M tokens (input, output). ESTIMATES for the cost readout only; edit to match
# your provider's real prices. Models not matched here show tokens but no dollar figure.
PRICE_HINTS = (("haiku", 1.0, 5.0), ("sonnet", 3.0, 15.0), ("opus", 15.0, 75.0))


def normalize_tier(value, default="medium"):
    key = re.sub(r"[\[\]()\s]", "", str(value or "")).lower()
    return _ALIASES.get(key, default)


_LONG_FORM = ("essay", "article", "report", "short story", "story about", "blog post", "speech", "cover letter",
              "research paper", "term paper", "lab report", "write-up", "newsletter", "poem", "script for", "chapter")


def looks_like_long_form(text):
    t = (text or "").lower()
    return any(h in t for h in _LONG_FORM) or bool(re.search(r"\b\d{3,}[- ]?words?\b", t))


def tier_model(tier):
    from core.model_config import load_model_config
    return load_model_config()[_CONFIG_KEY[normalize_tier(tier)]]


def price_for(model):
    low = (model or "").lower()
    for needle, p_in, p_out in PRICE_HINTS:
        if needle in low:
            return p_in, p_out
    return None


class CostTracker:
    """Adds up tokens per tier and estimates dollars, including what the same tokens
    would have cost if everything had run on the heavy model."""

    def __init__(self, heavy_model=None):
        self.heavy_model = heavy_model
        self.rows = {}
        self.requests = 0

    def add(self, tier, model, tokens_in, tokens_out):
        row = self.rows.setdefault(tier, {"model": model, "in": 0, "out": 0, "calls": 0})
        row["in"] += tokens_in or 0
        row["out"] += tokens_out or 0
        row["calls"] += 1
        self.requests += 1

    @property
    def tokens_in(self):
        return sum(r["in"] for r in self.rows.values())

    @property
    def tokens_out(self):
        return sum(r["out"] for r in self.rows.values())

    def _cost(self, model, t_in, t_out):
        p = price_for(model)
        return None if p is None else (t_in * p[0] + t_out * p[1]) / 1_000_000

    def estimate(self):
        total, known = 0.0, True
        for r in self.rows.values():
            c = self._cost(r["model"], r["in"], r["out"])
            if c is None:
                known = False
            else:
                total += c
        return total if known and self.rows else None

    def all_heavy_estimate(self):
        if not self.heavy_model or not self.rows:
            return None
        return self._cost(self.heavy_model, self.tokens_in, self.tokens_out)

    def stats(self):
        out = {}
        parts = ["%s×%d" % (LABELS.get(t, t), r["calls"]) for t, r in sorted(self.rows.items(), key=lambda kv: TIER_ORDER.index(kv[0]) if kv[0] in TIER_ORDER else 9)]
        if parts:
            out["Calls by tier"] = ", ".join(parts)
        est, heavy = self.estimate(), self.all_heavy_estimate()
        if est is not None:
            out["Est. cost"] = "$%.3f" % est + (" (all-heavy ≈ $%.3f)" % heavy if heavy is not None else "")
        return out


_STEP_RE = re.compile(
    r"^\s*(?:\d+[.)]|[-*])\s*(?:\[(?P<pre>[a-z_]+)\]\s*)?(?P<text>.*?)\s*(?:[\[(](?P<post>(?:easy|simple|medium|moderate|heavy|hard)_task)[\])])?\s*$",
    re.I)


def parse_tiered_plan(plan_text):
    """Reads numbered plan lines tagged [easy_task]/[medium_task]/[heavy_task] (prefix or
    suffix, brackets or parens). Returns a list of {"tier","title","instruction"} when at
    least two steps carry a tier tag, else None (caller falls back to the normal worker)."""
    steps, tagged = [], 0
    for raw in (plan_text or "").splitlines():
        if not raw.strip():
            continue
        m = _STEP_RE.match(raw)
        starts_numbered = bool(re.match(r"^\s*(?:\d+[.)]|[-*])\s", raw))
        if m and starts_numbered:
            tag = m.group("pre") or m.group("post")
            tier = normalize_tier(tag, default="") if tag and normalize_tier(tag, default="") else ""
            text = m.group("text").strip()
            if tier:
                tagged += 1
            steps.append({"tier": tier or "medium", "title": text.split(". ")[0][:80], "instruction": text})
        elif steps:  # continuation line belongs to the previous step
            steps[-1]["instruction"] += "\n" + raw.strip()
    return steps if tagged >= 2 and len(steps) >= 2 else None
