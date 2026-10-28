"""Pure current-year uniform QNEC planning estimates."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from statistics import mean
from typing import Literal, Sequence

from pydantic import Field

from ..models.base import APIModel

ASSUMPTIONS = [
    "Uniform percentage of capped testing compensation to all eligible NHCEs, including nondeferrers",
    "Current-year testing",
    "Principal only, excludes earnings",
    "Per-participant amounts rounded UP to the cent",
    "Modeled estimate, needs plan administrator review before any operational use",
    "HCE classification is compensation-based only",
]


class ADPQNECEstimate(APIModel):
    status: Literal["estimate", "not_needed", "unsupported", "infeasible"]
    reason: str | None = None
    qnec_rate: float = 0.0
    total_qnec: float = 0.0
    recipient_count: int = 0
    nhce_average_adp_before: float = 0.0
    nhce_average_adp_after: float = 0.0
    applied_threshold_after: float = 0.0
    applied_test_after: str = "basic"
    test_result_after: Literal["pass", "fail"] = "fail"
    limit_breach_count: int = 0
    assumptions: list[str] = Field(default_factory=lambda: list(ASSUMPTIONS))


@dataclass(frozen=True)
class NHCEQNECInput:
    testing_comp: float
    adp: float
    annual_additions: float


@dataclass(frozen=True)
class ADPQNECContext:
    hce_compensations: Sequence[float]
    nhce: Sequence[NHCEQNECInput]
    annual_additions_limit: float | None


def _threshold(nhce_adp: float) -> tuple[float, str]:
    basic = 1.25 * nhce_adp
    alternative = min(2 * nhce_adp, nhce_adp + 0.02)
    return (basic, "basic") if basic >= alternative else (alternative, "alternative")


def _amount(rate: float, comp: float) -> Decimal:
    # Drop float noise in the rate (e.g. 4500.0000000001) before rounding up.
    exact = (Decimal(str(rate)) * Decimal(str(comp))).quantize(Decimal("0.000001"))
    return exact.quantize(Decimal("0.01"), rounding=ROUND_CEILING)


def _breach_count(
    nhce: Sequence[NHCEQNECInput],
    amounts: Sequence[Decimal],
    limit: float | None,
) -> int:
    if limit is None:
        return 0
    return sum(
        Decimal(str(p.annual_additions)) + q > Decimal(str(limit))
        for p, q in zip(nhce, amounts)
    )


def _outcome(
    passing: bool, breaches: int
) -> tuple[Literal["estimate", "not_needed", "infeasible"], str | None]:
    if passing:
        return "not_needed", "ADP test already passes"
    if breaches:
        return (
            "infeasible",
            f"415 annual additions limit would be exceeded for {breaches} NHCEs",
        )
    return "estimate", None


def estimate_uniform_qnec(
    hce_adps: Sequence[float],
    nhce: Sequence[NHCEQNECInput],
    annual_additions_limit: float | None,
) -> ADPQNECEstimate:
    """Estimate principal without clipping amounts to available 415 headroom."""
    if not hce_adps or not nhce:
        return ADPQNECEstimate(
            status="unsupported", reason="Both HCE and NHCE groups are required"
        )
    hce, before = mean(hce_adps), mean(p.adp for p in nhce)
    required = min(hce / 1.25, max(hce / 2, hce - 0.02))
    delta = max(0.0, required - before)
    passing = hce <= _threshold(before)[0] + 1e-12
    amounts = [_amount(0.0 if passing else delta, p.testing_comp) for p in nhce]
    after = mean(p.adp + float(q) / p.testing_comp for p, q in zip(nhce, amounts))
    threshold, test = _threshold(after)
    breaches = _breach_count(nhce, amounts, annual_additions_limit)
    assumptions = list(ASSUMPTIONS)
    if annual_additions_limit is None:
        assumptions.append("415 headroom not checked: limit unavailable")
    status, reason = _outcome(passing, breaches)
    return ADPQNECEstimate(
        status=status,
        reason=reason,
        qnec_rate=0.0 if passing else delta,
        total_qnec=float(sum(amounts)),
        recipient_count=0 if passing else len(nhce),
        nhce_average_adp_before=before,
        nhce_average_adp_after=after,
        applied_threshold_after=threshold,
        applied_test_after=test,
        test_result_after="pass" if hce <= threshold + 1e-12 else "fail",
        limit_breach_count=breaches,
        assumptions=assumptions,
    )
