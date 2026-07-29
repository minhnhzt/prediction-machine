"""
kelly_criterion.py — Bankroll management via the Kelly Criterion.

The Kelly Criterion determines the optimal fraction of bankroll to wager,
maximising the expected logarithmic growth rate of wealth.

    f* = (b·p − q) / b

where:
    p = estimated probability of winning
    q = 1 − p  (probability of losing)
    b = net decimal odds  (decimal_odds − 1)

A "Fractional Kelly" multiplier (e.g., 0.5 = Half-Kelly) shrinks the
stake to reduce variance at the cost of slightly lower long-term growth.
"""

from dataclasses import dataclass


@dataclass
class KellyResult:
    """Container for the Kelly Criterion output."""

    full_kelly_fraction: float     # raw Kelly fraction (may be negative = no edge)
    applied_fraction: float        # after fractional multiplier and floor-to-zero
    wager_pct: float               # applied_fraction as a percentage (0–100)
    wager_amount: float            # absolute cash value to bet
    edge: float                    # expected edge  (p · (b+1) − 1)
    expected_value: float          # EV of the bet  (edge × wager_amount)
    fractional_multiplier: float   # the fraction of Kelly used

    def summary(self) -> str:
        if self.applied_fraction <= 0:
            return (
                "❌  No positive edge detected — the Kelly Criterion recommends "
                "NOT placing a wager on this line."
            )
        return (
            f"✅  Kelly Criterion Recommendation\n"
            f"   Full Kelly fraction  : {self.full_kelly_fraction:.4f}  "
            f"({self.full_kelly_fraction * 100:.2f}%)\n"
            f"   Fractional multiplier: {self.fractional_multiplier:.2f}×\n"
            f"   Applied fraction     : {self.applied_fraction:.4f}  "
            f"({self.wager_pct:.2f}%)\n"
            f"   Wager amount         : ${self.wager_amount:,.2f}\n"
            f"   Edge                 : {self.edge:.4f}  "
            f"({self.edge * 100:.2f}%)\n"
            f"   Expected value       : ${self.expected_value:,.2f}"
        )


def kelly_criterion(
    win_probability: float,
    decimal_odds: float,
    bankroll: float,
    fractional: float = 1.0,
    max_bet_pct: float = 0.25,
) -> KellyResult:
    """
    Calculate the optimal wager using the Kelly Criterion.

    Parameters
    ----------
    win_probability : float
        Model's estimated probability of the bet winning (0 < p < 1).
    decimal_odds : float
        Bookmaker's decimal odds (e.g., 1.80 means +80 % return on win).
    bankroll : float
        Current total bankroll in currency units.
    fractional : float, default 1.0
        Kelly fraction multiplier.  Common values:
            1.0  = Full Kelly  (maximum growth, high variance)
            0.5  = Half Kelly  (reduced variance, recommended)
            0.25 = Quarter Kelly  (very conservative)
    max_bet_pct : float, default 0.25
        Hard cap on the wager as a fraction of bankroll (safety rail).

    Returns
    -------
    KellyResult
        Dataclass with the recommended wager and supporting metrics.

    Raises
    ------
    ValueError
        If inputs are outside valid ranges.
    """
    # ── Input validation ──────────────────────────────────────────────────
    if not (0.0 < win_probability < 1.0):
        raise ValueError(
            f"win_probability must be in (0, 1), got {win_probability}"
        )
    if decimal_odds <= 1.0:
        raise ValueError(
            f"decimal_odds must be > 1.0, got {decimal_odds}"
        )
    if bankroll <= 0:
        raise ValueError(f"bankroll must be > 0, got {bankroll}")
    if not (0.0 < fractional <= 1.0):
        raise ValueError(
            f"fractional multiplier must be in (0, 1], got {fractional}"
        )

    # ── Kelly formula ─────────────────────────────────────────────────────
    p = win_probability
    q = 1.0 - p
    b = decimal_odds - 1.0          # net odds (profit per unit staked)

    full_kelly = (b * p - q) / b    # f* = (bp − q) / b

    # Apply fractional multiplier; floor to zero (no shorting)
    applied = max(0.0, full_kelly * fractional)

    # Safety cap
    applied = min(applied, max_bet_pct)

    # ── Derived quantities ────────────────────────────────────────────────
    wager_amount = round(applied * bankroll, 2)
    edge = p * (b + 1.0) - 1.0     # E[return] per unit staked
    ev = round(edge * wager_amount, 2)

    return KellyResult(
        full_kelly_fraction=round(full_kelly, 6),
        applied_fraction=round(applied, 6),
        wager_pct=round(applied * 100, 4),
        wager_amount=wager_amount,
        edge=round(edge, 6),
        expected_value=ev,
        fractional_multiplier=fractional,
    )


# ── Demo / CLI ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  KELLY CRITERION — BETTING STRATEGY DEMO")
    print("=" * 60)

    # Scenario: Model predicts 62 % blue-win, bookie offers 1.85 decimal odds
    scenarios = [
        {"label": "Full Kelly",    "frac": 1.0},
        {"label": "Half Kelly",    "frac": 0.5},
        {"label": "Quarter Kelly", "frac": 0.25},
    ]

    for s in scenarios:
        print(f"\n── {s['label']} {'─' * (45 - len(s['label']))}")
        result = kelly_criterion(
            win_probability=0.62,
            decimal_odds=1.85,
            bankroll=10_000.0,
            fractional=s["frac"],
        )
        print(result.summary())

    # Negative-edge scenario
    print(f"\n── No-Edge Scenario {'─' * 38}")
    result = kelly_criterion(
        win_probability=0.45,
        decimal_odds=1.80,
        bankroll=10_000.0,
        fractional=0.5,
    )
    print(result.summary())
