"""A merchant under investigation, and the refunds that must not reach it.

Runs entirely in memory - no database, no payment provider, no API key. The
tenant has frozen one merchant while a fraud case is open. A refund small
enough to go straight through anywhere else is refused for that one, by
policy, before anything is dispatched - and the explanation says so.

    python examples/frozen_merchant.py
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from ledgerloop.adapters.clock import ManualClock
from ledgerloop.adapters.memory import (
    ApproverDirectory,
    InMemoryApprovalGateway,
    InMemoryIdempotencyStore,
    InMemoryLedgerStore,
    InMemoryRunStore,
    RecordingDispatcher,
)
from ledgerloop.core.enums import ActionKind, Currency, PolicyEffect
from ledgerloop.core.errors import PolicyViolationError
from ledgerloop.core.ids import ActionId, IdempotencyKey, TenantId
from ledgerloop.core.models import Action, RunSpec
from ledgerloop.core.money import Money
from ledgerloop.policy import PolicyRule, ThresholdPolicy, ThresholdPolicyEngine
from ledgerloop.runtime import ActionExecutor, RunCoordinator

FROZEN = "mer_4c0de"


def build_refund(order: str, amount: str, counterparty: str) -> Action:
    """A refund action, with its idempotency key derived from its content."""
    money = Money.from_major(amount, Currency.INR)
    return Action(
        id=ActionId.generate(),
        kind=ActionKind.REFUND,
        description=f"Duplicate charge on order {order}",
        amount=money,
        counterparty=counterparty,
        idempotency_key=IdempotencyKey.derive(
            "refund", order, str(money.minor_units), money.currency, counterparty
        ),
    )


async def main() -> None:
    clock = ManualClock(datetime(2026, 5, 1, 9, 0, tzinfo=UTC))

    runs = InMemoryRunStore(clock=clock)
    ledger = InMemoryLedgerStore()
    dispatcher = RecordingDispatcher()

    # The conservative defaults, with one rule placed ahead of them. Rules
    # are ordered and the first match wins, so the freeze outranks the rule
    # that lets small refunds through.
    defaults = ThresholdPolicy.conservative()
    freeze = PolicyRule(
        effect=PolicyEffect.DENY,
        reason="Merchant frozen pending fraud case FC-2207",
        rule_id="freeze-mer_4c0de",
        counterparties=frozenset({FROZEN}),
    )
    policy = ThresholdPolicyEngine(
        default_policy=ThresholdPolicy(
            rules=(freeze, *defaults.rules),
            auto_approve_ceiling=defaults.auto_approve_ceiling,
        )
    )

    coordinator = RunCoordinator(
        runs=runs,
        policy=policy,
        approvals=InMemoryApprovalGateway(directory=ApproverDirectory()),
        executor=ActionExecutor(
            idempotency=InMemoryIdempotencyStore(),
            dispatcher=dispatcher,
            ledger=ledger,
            clock=clock,
        ),
        ledger=ledger,
        clock=clock,
    )

    tenant = TenantId.generate()
    run = await runs.create(
        RunSpec(tenant_id=tenant, objective="Clear today's duplicate-charge queue")
    )
    run = await coordinator.start(run)

    # --- a small refund to anyone else: straight through ------------------
    ordinary = build_refund("ord_1001", "1200", "mer_9f21c")
    result = await coordinator.propose(run, ordinary)
    print(f"mer_9f21c     -> executed={result.executed} by {result.decision.rule_id}")

    # --- the same size of refund to the frozen merchant -------------------
    blocked = build_refund("ord_1002", "1200", FROZEN)
    try:
        await coordinator.propose(result.run, blocked)
    except PolicyViolationError as exc:
        print(f"{FROZEN}     -> refused: {exc.message}")
    print(f"              dispatches: {dispatcher.dispatch_count}")

    # --- and why, rule by rule --------------------------------------------
    explanation = await policy.explain(blocked, result.run, at=clock.now())
    print(f"\n{explanation.render()}")

    explanation = await policy.explain(ordinary, result.run, at=clock.now())
    print(f"\n{explanation.render()}")


if __name__ == "__main__":
    asyncio.run(main())
