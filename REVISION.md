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

The preceding integration passed all 550 distinct required checks in Actions run 39901513033 and was published without new clause credit. GitHub Actions captures the original physical inputs, actual reads and module origins in encrypted evidence for independent canonical acceptance. Detailed classification records keep separate obligations attached to the same clause; a shared label alone does not close that clause.

The current source-contract revision contains these separately reviewed repairs:

- Current owner passives reach newly registered, captured and hatched Pokemon through the existing slot, stat, range and class-feature owners. Existing transfer order and permanent paid effects are preserved.
- Actual damage type reaches STAB, ordinary Tera damage, typed Coats, thaw, armor and fire-feature consumers; Weakness Policy receives the final effectiveness after reactions. Ordinary Terastal ends with the scene or fainting. Printed source identity and damage receipts remain distinct.
- Versatile Moves accept an explicit attack-stat choice. Fistful of Force retains its paid shard type and Occult coefficient through inner attacks, pending restoration and later area recipients.
- Successful ordinary maneuvers carry their actual natural face to existing Menace consumers and retain Pummeling tags. Automatic Grapple hits retain the tag without inventing a natural roll or an Iron Fist gain.

The first source-contract execution, Actions run 39909091869 at commit 2314f239b2afa9985b006e6c49ed4084edbae8cc, selected 465 exact checks, started 459 and failed. Its original allocation and raw failure evidence are preserved. The repaired `next_revisions` packet retains all 465 and adds 15 affected or new checks, for 480 total; its runtime result is pending.

The repair registers three exact CSV source identities, separates Flinch-derived timers from Roughneck-owned effects, and preserves immunity through resistance adjustments and actual-type grounding. It also corrects source-profile selection, portable fixture roots and native action setup while retaining source-specific expectations. R253/R624 burn-range reachability, Stellar questions, Coat self-recipient rules, Fearsome/Intercept timing and other audit families remain separately tracked. A passing sub-contract does not close an entire multi-cause clause.
