# Rule engine revisions

This revision fixes four source-bound behaviors and adds explicitly declared skill ranks through the existing `Rulings` API.

- Move keyword extraction reads the printed Range field. Effect text mentioning another keyword no longer assigns it to the base move. Existing conditional grants and selected optional modes keep their own behavior. The catalog, mechanics, both RuleUnit exports, and three optional-mode source copies are synchronized. Anchors: `ch04:2516-2520`, `ch10:334,371,373`, and the move CSV Range/effect columns.
- Push Buttons preserves accumulated critical-range expansion when lowering the Demoralize threshold. Anchors: `ch03:430-432`, `ch04:2543-2547`.
- Martial Artist uses effective Combat rank for Pummeling Momentum's cap and saved-state validation, and Soft Landing's reduction. Acquisition requirements and ordinary skill dice keep their separate rank. Anchors: `ch03:331-333`, `ch04:2469-2471`; the existing English-authority decision resolves the Pummeling translation.
- Retraining a single Edge removes only that source's current choices, including its declared aliases. Existing GM approval, XP, prerequisites, permanent-effect restrictions, and retry behavior remain in the same transaction. Anchor: `ch02:342-358`.
- Campaign scripts can declare ordinary ranks through `Rulings.set_mech('gameplay/skill-rank-dice', 'by_rank_name.<name>', {rank, dice, eng}, ...)`. Rank and dice count are independent; for example, rank 10 may use 7d6. Saved declarations are attached to the private Rules copy before gameplay validation. See [the example](examples/declared_skill_ranks.py).

Default PTU ordinary ranks remain 1 through 6, and Virtuoso supplies effective rank 8. Extra ordinary ranks require an explicit declaration. Declarations do not create advancement or purchase rights. The existing d6 adapter, helper rules, and extended-check policies retain their scope.

New regression tests cover native actions, source ownership, rollback and restoration, plus composition of declared ranks with Martial Artist. Integrated game verification runs in GitHub Actions; local integration checks syntax, source/preimage identity, and keyword-only data changes without running the game engine.

Further source review separates Pummeling's gain cap from its explicit termination. An earned bonus persists when its rank provider is withdrawn; the current effective rank limits future increases. Native gain observations preserve that history. On restore, valid older tags retain their original bounded validation record without inventing an unobserved past rank. Repeated-rank retraining and generalization of assistance or extended checks retain their existing scope.


The full-revision follow-up separates confirmed defects from extension compatibility and regression-only coverage:

- Realized Potential evolution supplies the Pokemon kind and condition state required by the existing shared capability consumer. This restores evolution and its source-specific recalculation/refund path.
- Rank-dependent Deep Diver, Traceur, Glyph and the accepted defensive-feature adapter consume effective ranks. Potent Venom, Dietician and Mentor preserve the distinction between ordinary prerequisites, declared ordinals and observed effect ranks. Existing source-specific capacities and costs remain.
- Survival belongs to both the Body category and the Education skill set. Education consumers share that set, and Pokemon Survival uses the existing campaign Education permission and individual-exception mechanism.
- Pummeling's historical bonus and valid legacy saves follow the gain/lifetime boundary above.

The `next_revisions` packet declares 550 distinct integration checks, including the accepted first-batch regressions. GitHub Actions captures the original physical inputs, actual reads and module origins in encrypted evidence for independent canonical acceptance. Detailed classification records keep separate obligations attached to the same clause; a shared label alone does not close that clause.
