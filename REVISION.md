# Rule engine revisions

This revision fixes four source-bound behaviors and adds explicitly declared skill ranks through the existing `Rulings` API.

- Move keyword extraction reads the printed Range field. Effect text mentioning another keyword no longer assigns it to the base move. Existing conditional grants and selected optional modes keep their own behavior. The catalog, mechanics, both RuleUnit exports, and three optional-mode source copies are synchronized. Anchors: `ch04:2516-2520`, `ch10:334,371,373`, and the move CSV Range/effect columns.
- Push Buttons preserves accumulated critical-range expansion when lowering the Demoralize threshold. Anchors: `ch03:430-432`, `ch04:2543-2547`.
- Martial Artist uses effective Combat rank for Pummeling Momentum's cap and saved-state validation, and Soft Landing's reduction. Acquisition requirements and ordinary skill dice keep their separate rank. Anchors: `ch03:331-333`, `ch04:2469-2471`; the existing English-authority decision resolves the Pummeling translation.
- Retraining a single Edge removes only that source's current choices, including its declared aliases. Existing GM approval, XP, prerequisites, permanent-effect restrictions, and retry behavior remain in the same transaction. Anchor: `ch02:342-358`.
- Campaign scripts can declare ordinary ranks through `Rulings.set_mech('gameplay/skill-rank-dice', 'by_rank_name.<name>', {rank, dice, eng}, ...)`. Rank and dice count are independent; for example, rank 10 may use 7d6. Saved declarations are attached to the private Rules copy before gameplay validation. See [the example](examples/declared_skill_ranks.py).

Default PTU ordinary ranks remain 1 through 6, and Virtuoso supplies effective rank 8. Extra ordinary ranks require an explicit declaration. Declarations do not create advancement or purchase rights. The existing d6 adapter, helper rules, and extended-check policies retain their scope.

New regression tests cover native actions, source ownership, rollback and restoration, plus composition of declared ranks with Martial Artist. Integrated game verification runs in GitHub Actions; local integration checks syntax, source/preimage identity, and keyword-only data changes without running the game engine.

The lifetime of a previously accumulated Pummeling bonus after withdrawing its rank provider remains unresolved. This revision introduces no clamp, deletion, or new retraining restriction for that case. Repeated-rank retraining and complete generalization of assistance or extended checks remain outside this revision.
