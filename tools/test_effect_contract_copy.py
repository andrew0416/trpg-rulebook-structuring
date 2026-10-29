"""Retained typed effect refusals remain diagnostic across native graph copies."""
from copy import deepcopy
from pathlib import Path
import pickle
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import effect_contracts as CONTRACTS


class EffectContractCopyTests(unittest.TestCase):
    def test_deepcopy_and_pickle_preserve_issue_args_and_shared_custom_state(self):
        for persisted in (False, True):
            for changed_args in (False, True):
                with self.subTest(persisted=persisted, changed_args=changed_args):
                    issue = CONTRACTS.Issue('unresolved_source', 'except', 'actual predicate unresolved')
                    error = CONTRACTS.EffectContractError('move/copy-source', 3, issue)
                    if changed_args:
                        error.args = ('retained application diagnostic', 'detail')
                    shared = {'error':error, 'trail':['original']}
                    error.context = shared
                    original = {'error':error, 'same':error, 'issue':issue, 'shared':shared}
                    copied = (pickle.loads(pickle.dumps(original, protocol=4))
                              if persisted else deepcopy(original))
                    new = copied['error']
                    self.assertIs(type(new), CONTRACTS.EffectContractError)
                    self.assertIsNot(new, error)
                    self.assertEqual((new.source_id,new.effect_index,new.issue),
                                     (error.source_id,error.effect_index,issue))
                    self.assertEqual((new.args,str(new)), (error.args,str(error)))
                    self.assertIs(copied['same'], new)
                    self.assertIs(new.issue, copied['issue'])
                    self.assertIs(new.context, copied['shared'])
                    self.assertIs(new.context['error'], new)
                    new.context['trail'].append('copy only')
                    self.assertEqual(shared['trail'], ['original'])

    def test_actual_attack_refusal_receipt_survives_staging_rollback_and_gm_add(self):
        import test_upper_effect_contracts as BASE
        from builder import build_trainer
        from engine import Combatant, Rules
        import effects as FX
        import state_grants as G
        import world_entities as WORLD
        fixture = BASE.Tests('runTest')
        fixture.r = Rules(ROOT)
        fixture.setUp()
        engine, actor, target = fixture.e, fixture.a, fixture.b
        actor.registry.append({'type':'never_miss','except':'some unknown condition'})
        before = fixture.state()
        with self.assertRaises(CONTRACTS.EffectContractError):
            engine.use_move(actor,target,'move/배리어러시')
        self.assertEqual(fixture.state(), before)
        source = 'move/배리어러시'
        result = FX.run_effects(engine,actor,target,
            [{'type':'attack','_rule_id':source,'ac':2,'class':'변화'}],
            {'hit':True,'attacker':actor,'target':target,'engine':engine},source)
        self.assertEqual((result[0],result[1]), (0,1))
        failed = [(token,row) for token,row in engine._effect_dispatch_receipts.items()
                  if row['source_id']==source and row['effect'].get('type')=='attack']
        self.assertEqual(len(failed), 1)
        token, row = failed[0]
        self.assertEqual(row['status'], 'execution_failed')
        error = row['result']
        self.assertIs(type(error), CONTRACTS.EffectContractError)
        self.assertEqual((error.issue.category,error.issue.field), ('unresolved_source','except'))
        # The raw component already observed accuracy before its typed refusal.
        # Preserve that RNG prefix; only later staged work must roll back.
        self.assertEqual(fixture.state()[1:], before[1:])
        observed = fixture.state()
        self.assertNotEqual(observed[0], before[0])
        error.participant = actor
        error.context = {'error':error,'participant':actor}
        def rejected(staged, subject):
            copied = staged._effect_dispatch_receipts[token]['result']
            self.assertIsNot(copied, error)
            self.assertEqual((copied.args,copied.source_id,copied.effect_index,copied.issue),
                             (error.args,error.source_id,error.effect_index,error.issue))
            self.assertIs(copied.participant, subject)
            self.assertIs(copied.context['participant'], subject)
            self.assertIs(copied.context['error'], copied)
            subject.hp -= 1
            staged.rng.random()
            raise ValueError('bounded typed-refusal rollback')
        with self.assertRaisesRegex(ValueError, 'bounded typed-refusal rollback'):
            G.transition(engine,actor,rejected)
        self.assertEqual(fixture.state(), observed)
        self.assertIs(engine._effect_dispatch_receipts[token]['result'], error)
        newcomer = Combatant(engine.r, build_trainer(engine.r,'new typed-refusal actor',20,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),moves=[],abilities=[],
            pos=(3,0),side='party',extra={'size':'중형'}))
        engine.gm.add_combatant(newcomer,reason='legal registration retains earlier typed refusal')
        self.assertIs(WORLD.actor_index(engine)[newcomer.entity_id],newcomer)
        retained = engine._effect_dispatch_receipts[token]
        self.assertEqual(retained['status'],'execution_failed')
        self.assertIs(type(retained['result']),CONTRACTS.EffectContractError)
        self.assertEqual((retained['result'].source_id,retained['result'].effect_index,retained['result'].issue),
                         (error.source_id,error.effect_index,error.issue))
        self.assertIs(retained['result'].participant,actor)
        with self.assertRaises(CONTRACTS.EffectContractError):
            engine.accuracy_check(actor,target,engine.r.move(source),fixed_roll=2)


if __name__ == '__main__':
    unittest.main()
