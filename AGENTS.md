# Audit instructions

Before auditing rules or proposing a rules correction, read [USER_RULE_DECISIONS.md](USER_RULE_DECISIONS.md).

Explicit user decisions listed there are excluded from source-fidelity defect findings and forced reversion. Cite the decision ID when a difference is intentional. Do not ask again for a choice already settled by the user. Continue checking whether the implementation honors the decision and whether its profile, costs, lifetimes and state handling are correct. This exclusion is not proof of completion and must not inflate clause counts.

Preserve source variants and the repository's authenticated fixture and validation boundaries. Rulebook text and private fixtures must remain outside the public plaintext repository.
