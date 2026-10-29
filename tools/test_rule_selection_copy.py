"""Selection errors retain their structured refusal across graph copying."""
from copy import deepcopy
from pathlib import Path
import pickle
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from ruleset import ExcludedRuleSelection, UnresolvedRuleSelection


class RuleSelectionCopyTests(unittest.TestCase):
    def errors(self):
        return (UnresolvedRuleSelection('move/copy-check', ['source/b', 'source/a', 'source/b']),
                ExcludedRuleSelection('move/copy-check', 'excluded by actual source profile'))

    def graph(self, error):
        shared = {'trail': ['original'], 'error': error}
        error.context = shared
        return {'error': error, 'again': error, 'shared': shared}

    def assert_graph(self, original, copied):
        old, new = original['error'], copied['error']
        self.assertIs(type(new), type(old))
        self.assertIsNot(new, old)
        self.assertEqual(new.args, old.args)
        self.assertEqual(str(new), str(old))
        self.assertEqual(new.identity, old.identity)
        if isinstance(old, UnresolvedRuleSelection):
            self.assertEqual(new.candidates, ('source/a', 'source/b'))
        else:
            self.assertEqual(new.reason, old.reason)
        self.assertIs(copied['again'], new)
        self.assertIs(new.context, copied['shared'])
        self.assertIs(copied['shared']['error'], new)
        self.assertIsNot(copied['shared'], original['shared'])
        copied['shared']['trail'].append('copy only')
        self.assertEqual(original['shared']['trail'], ['original'])

    def test_deepcopy_preserves_structured_refusal_and_exact_display_args(self):
        for changed_args in (False, True):
            for error in self.errors():
                with self.subTest(kind=type(error).__name__, changed_args=changed_args):
                    if changed_args:
                        error.args = ('retained application diagnostic', 'detail')
                    original = self.graph(error)
                    self.assert_graph(original, deepcopy(original))

    def test_deepcopy_uses_callers_memo_for_custom_state_aliases(self):
        for error in self.errors():
            with self.subTest(kind=type(error).__name__):
                anchor, staged_anchor = object(), object()
                error.participant = anchor
                original = self.graph(error)
                copied = deepcopy(original, {id(anchor): staged_anchor})
                self.assert_graph(original, copied)
                self.assertIs(copied['error'].participant, staged_anchor)
                self.assertIs(error.participant, anchor)

    def test_pickle_preserves_both_refusals_args_and_cyclic_custom_state(self):
        for protocol in sorted({4, pickle.HIGHEST_PROTOCOL}):
            for error in self.errors():
                with self.subTest(kind=type(error).__name__, protocol=protocol):
                    error.args = ('retained persistence diagnostic',)
                    original = self.graph(error)
                    self.assert_graph(original, pickle.loads(pickle.dumps(original, protocol=protocol)))

    def test_native_failed_selection_receipt_survives_gm_staging_and_rollback(self):
        from builder import build_trainer
        from engine import Combatant
        import effects as FX
        import state_grants as G
        import world_entities as WORLD
        from native_scenario_fixture import prepare_scene
        rows = [dict(key=name, kind='trainer',
                     sheet=dict(name=name, level=20,
                                stats=dict.fromkeys(('hp','atk','def','spa','spd','spe'), 10),
                                moves=[], abilities=[], pos=pos, side='party'),
                     body=dict(size='중형', offsets=[(0,0)], reason='actual copy-boundary participant'))
                for name, pos in (('a', (1,1)), ('b', (2,1)))]
        engine, actors = prepare_scene(ROOT, ruleset='core', seed=31,
                                      grid={'width':8,'height':8}, actors=rows)
        actor, target = actors['a'], actors['b']
        conditions = set(target.conditions)
        choice = FX.run_effects(engine, actor, target,
            [{'type':'apply_status_choice','options':['둔화 (1라운드)','억압'],'target':'target'}],
            {'hit':True}, 'test')
        self.assertEqual((choice[0], choice[1]), (0,1))
        self.assertEqual(target.conditions, conditions)
        source = 'audit/missing-copy-selection-source'
        before_moves = list(actor.moves)
        failed = FX.run_effects(engine, actor, target,
            [{'type':'grant_move','moves':['move/몸통박치기'],'target':'self'}], {'hit':True}, source)
        self.assertEqual((failed[0], failed[1]), (0,1))
        records = [(token, row) for token, row in engine._effect_dispatch_receipts.items()
                   if row['source_id'] == source]
        self.assertEqual(len(records), 1)
        token, row = records[0]
        self.assertEqual(row['status'], 'execution_failed')
        error = row['result']
        self.assertIsInstance(error, UnresolvedRuleSelection)
        self.assertEqual(error.identity, source)
        self.assertEqual(error.candidates, ('missing_source_identity',))
        self.assertEqual(actor.moves, before_moves)
        error.participant = actor
        error.context = {'error':error, 'participant':actor}
        rng, hp = engine.rng.getstate(), actor.hp
        def reject(staged, subject):
            held = staged._effect_dispatch_receipts[token]
            self.assertEqual(held['status'], 'execution_failed')
            copied = held['result']
            self.assertIsNot(copied, error)
            self.assertIs(copied.participant, subject)
            self.assertIs(copied.context['participant'], subject)
            self.assertIs(copied.context['error'], copied)
            subject.hp -= 1
            staged.rng.random()
            raise ValueError('bounded copied-world refusal')
        with self.assertRaisesRegex(ValueError, 'bounded copied-world refusal'):
            G.transition(engine, actor, reject)
        self.assertEqual((actor.hp, engine.rng.getstate()), (hp, rng))
        self.assertIs(engine._effect_dispatch_receipts[token]['result'], error)
        newcomer = Combatant(engine.r, build_trainer(engine.r, 'new registered actor', 20,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'), 10), moves=[], abilities=[],
            pos=(3,1), side='party', extra={'size':'중형'}))
        engine.gm.add_combatant(newcomer, reason='unrelated legal registration after held source refusal')
        self.assertIs(WORLD.actor_index(engine)[newcomer.entity_id], newcomer)
        retained = engine._effect_dispatch_receipts[token]
        self.assertEqual(retained['status'], 'execution_failed')
        self.assertIsInstance(retained['result'], UnresolvedRuleSelection)
        self.assertEqual(retained['result'].candidates, ('missing_source_identity',))
        self.assertIs(retained['result'].participant, actor)
        self.assertEqual(actor.moves, before_moves)
        with self.assertRaises(UnresolvedRuleSelection):
            engine.r._selected_rule(source)


if __name__ == '__main__':
    unittest.main()
