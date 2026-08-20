# Governance charter

This charter defines who controls the ledger and how privileged actions are
taken. It exists because the common failure of manufacturing consortia is not
technical: platforms such as TradeLens and we.trade were built and then failed
because one dominant party controlled the network and competitors would not
join. Governance is therefore a precondition of the tier-A1 claim, not paperwork
that follows it.

## The honesty gate

The system may only be described as **tamper-resistant** when all of the
following hold. Until then the honest description is **tamper-evident**, and the
product says so.

1. At least two organizations with genuinely adverse interests each operate a
   validator. A validator that one party compels another to run does not count.
2. At least four validators exist, so one faulty node can be tolerated.
3. No organization controls one third or more of the validator set.
4. No single key can change roles, upgrade contracts, or move funds.

If a deployment cannot meet these, it should run the single-organization
configuration and make no multi-party claim.

## Roles

| Role | Held by | May do | May never do |
| --- | --- | --- | --- |
| Fleet Admin | Governance multisig | Grant and revoke roles, register printers, set policy | Register or run print jobs, release payment |
| Operator | Print farm staff | Schedule, dispatch, and run jobs; anchor checkpoints | Grant roles, release payment |
| Client | Design owner | Submit jobs, read their own history | Schedule or run jobs |
| Auditor | Regulator, insurer, or customer | Read everything, verify exports | Write anything |
| Verifier | Neutral verification service | Report a verdict to the escrow | Arbitrate a dispute |
| Arbiter | Neutral party, distinct from the verifier | Resolve disputes | Report verdicts |
| Guardian | Security responders | Cancel a queued governance action | Execute one |

Separation of duties is enforced in code, not by convention: roles are discrete
rather than hierarchical, so an administrator is not implicitly an operator, and
the escrow rejects a verifier that is also the arbiter.

## Privileged actions

Every privileged action runs through `MultiSigTimelock`:

1. A signer queues the action, which records it publicly and starts the delay.
2. Other signers approve until the threshold is met. Recommended: three of five.
3. After the delay the action may execute. Recommended delay: 48 hours for
   routine changes, and no less than 24 hours for anything touching upgrades or
   funds.
4. A guardian may cancel a queued action at any point before execution.

The asymmetry is deliberate. Stopping an action is safe and is therefore easy;
starting one is dangerous and is therefore slow and requires several people.

## Validator membership

Adding or removing a validator is a privileged action and follows the process
above. A member may resign at any time. A member may be removed for sustained
unavailability, for refusing to sign valid blocks, or for a security compromise,
subject to the same multisig and delay.

## Disputes

A verdict of failure with low confidence, or the absence of a verdict, moves the
deal to arbitration with funds held. The arbiter must be neutral and must not be
the fleet owner when the fleet owner is a party to the deal, otherwise the
dispute layer reproduces the capture problem the consortium exists to avoid.

Arbitration is bounded. If the arbitration window expires with no decision,
anyone may unwind the deal neutrally: each side receives its own funds back.
Nobody profits from stalling and nothing can be locked forever.

## Upgrades

The verification contract is deliberately not upgradeable. An upgradeable
verifier would let an administrator retroactively change the rules by which past
jobs were judged, which would undermine the audit trail the system exists to
provide. Operational contracts may be upgraded through the process above.

## Amending this charter

Amendments are a privileged action and require the same threshold and delay,
plus written agreement from every member organization.
