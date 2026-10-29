"""Native three-participant suspended-owner regression; source-only proposal.

No event, receipt, grant, active owner, or reaction frame is synthesized.
Checkpoint output distinguishes fixture admission from the target Detect boundary.
"""
from copy import deepcopy
from pathlib import Path
import json
import os
import sys
import unittest
from unittest.mock import patch

ROOT=Path(os.environ.get('PTK_EXPERIMENT_ROOT') or Path(__file__).resolve().parents[1]).resolve()
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_authority_candidate_pending02 as BASE
_saved_paths=list(sys.path)
import test_book_type_ace_actions as ACE_FIX
sys.path[:]=_saved_paths
from engine import Engine
import trainer_feature_acquisition as ACQUIRE
import training_features as TRAINING
import taskmaster as TASK
import frequency as FREQUENCY
import passive_events as PASSIVE
import move_defense_reactions as DEFENSE
import initiative_interrupts as INTERRUPTS
import state_codec as CODEC
import world_entities as WORLD


class GambitNestedOwner06Tests(unittest.TestCase):
    setUpClass=classmethod(BASE.CandidatePending02Tests.setUpClass.__func__)
    private_rules=BASE.CandidatePending02Tests.private_rules
    known_detect=BASE.CandidatePending02Tests.known_detect

    def note(self,checkpoint,**facts):
        print('GAMBIT_NESTED_OWNER06 '+json.dumps(dict(checkpoint=checkpoint,**facts),sort_keys=True))

    def fixture(self):
        f=ACE_FIX.TypeAceActionsTests('runTest');f.rules=self.private_rules('core')
        f.branch('페어리','Fairy Lights','Fey Trance')
        f.e.death_enabled=False
        # Preserve the Type Ace's actual acquisition/owned pair. Add an opposing
        # acquired Taskmaster and its own Pokemon rather than relabel ownership.
        f.e.gm.recall(f.b,reason='original unused fixture opponent is recalled')
        owner=f.add('nested actual Taskmaster','trainer',(10,9),side='foe',
                    classes=[],feats=[TRAINING.BRUTAL,TASK.PRESS_ACTION],exp_bank=100)
        target=f.add('nested actual Gambit Pokemon','pokemon',(5,2),side='foe',
                     trainer_id=owner.entity_id,tutor_points=8,types=['노말'])
        f.e.gm.observe_loyalty(target,6,reason='actual willing opposing partner')
        for feature in (TASK.CLASS,TASK.QUICK,TASK.SAVAGE,TASK.WHIP,TASK.PAIN,
                        TASK.PRESS,TASK.DESPERATE,TASK.GAMBIT):
            ACQUIRE.acquire_static(f.e,owner,feature,
                acquisition_request_id='nested-owner06/'+owner.entity_id+'/'+feature)
        f.e.gm.set_position(f.q,(6,2),reason='actual ally adjacent to the approaching foe')
        self.known_detect(f.e,f.q)
        f.known(f.p,'move/애교부리기')
        f.answer('cruelty',False)
        f.answer('deadly_gambit',{'move':'struggle','roll_effects':False,'options':{'set_damage':True}})
        f.answer('type_ace_fey_approach',{'mode':'land','path':[(4,2)]})
        f.sustain('Fey Trance')
        self.assertIs(f.e._active_turn_actor,f.p)
        f.e.watch_move_defense(f.q,[{'actor_id':f.q.entity_id,'source':DEFENSE.DETECT}],
                              reason='actual ally chooses Detect against the paid counter')
        self.note('fixture_ready',owner=f.p.entity_id,incoming_attacker=f.q.entity_id,
                  counter_actor=target.entity_id)
        return f,owner,target

    def test_fey_approach_aoo_gambit_detect_keeps_third_actor_suspended_turn(self):
        for cold in (False,True):
            with self.subTest(cold=cold):
                f,trainer,target=self.fixture()
                ids=[c.entity_id for c in (f.p,f.q,trainer,target)]
                hp=(f.q.hp,target.hp)
                # Only dice are controlled. All acquisition, movement, AoO,
                # Gambit payment and the optional defense wait are native.
                with patch.object(Engine,'d20',return_value=10):
                    with self.assertRaises(PASSIVE.PassiveEventPending) as caught:
                        f.e.use_move_on(f.p,target,'move/애교부리기',f.e.everyone,set_damage=True)
                event_id=caught.exception.event_id
                event=f.e._passive_events[event_id]
                self.assertIs(event['actor'],target)
                self.assertIs(event['target'],f.q)
                parent=f.e._passive_events[event['taskmaster_gambit_parent']]
                self.assertIs(parent['actor'],f.q)
                self.assertIs(parent['target'],target)
                self.assertEqual(parent['move_id'],'struggle')
                self.assertTrue(f.q.aoo_used)
                self.assertEqual(parent['taskmaster_gambit']['facts']['boundary'][2],f.p.entity_id)
                self.assertIs(f.e._active_turn_actor,f.p)
                self.assertEqual(FREQUENCY.state(trainer)['activations'][TASK.GAMBIT]['used'],1)
                self.note('actual_counter_wait',cold=cold,event_id=event_id,
                          suspended=f.p.entity_id,incoming=f.q.entity_id)
                if cold:
                    f.e=CODEC.load_engine(f.e.r,json.loads(json.dumps(CODEC.dump_engine(f.e),ensure_ascii=False)))
                    index=WORLD.actor_index(f.e)
                    f.p,f.q,trainer,target=[index[uid] for uid in ids]
                paid=deepcopy((f.p.move_uses,f.q.move_uses,target.move_uses,
                               FREQUENCY.state(trainer)['activations'][TASK.GAMBIT]))
                with patch.object(Engine,'d20',side_effect=AssertionError('paid automatic Gambit accuracy cannot reroll')):
                    f.e.choose_move_defense(event_id,f.q,use=True,
                        reason='actual AoO attacker Detects while a third actor owns the turn')
                self.assertIs(f.e._active_turn_actor,f.p)
                self.assertEqual(f.q.hp,hp[0],'Detect avoids only the actual reverse counter')
                self.assertLess(target.hp,hp[1],'the already-paid incoming opportunity hit still resolves')
                self.assertEqual(f.q.move_uses.get(DEFENSE.DETECT,0),1)
                self.assertEqual(f.p.move_uses,paid[0],'outer Fairy Status Move cannot repay')
                self.assertEqual(target.move_uses,paid[2],'actual paid counter cannot repay')
                self.assertEqual(FREQUENCY.state(trainer)['activations'][TASK.GAMBIT],paid[3])
                windows=getattr(f.e,INTERRUPTS.KEY)['windows'].values()
                actual=[w for w in windows if w['trigger'].get('gambit_counter_source',{}).get('event_id')==event_id]
                self.assertEqual(len(actual),1)
                self.assertIs(actual[0]['parent'],f.p)
                self.assertEqual(actual[0]['trigger']['gambit_counter_source']['owner_id'],f.p.entity_id)
                self.note('actual_detect_returned',cold=cold,event_id=event_id)
                # Returned historical windows must remain valid without a live
                # Heavy token or recreating the original paid counter scope.
                restored=CODEC.load_engine(f.e.r,json.loads(json.dumps(CODEC.dump_engine(f.e),ensure_ascii=False)))
                self.assertEqual(restored._active_turn_actor.entity_id,f.p.entity_id)


if __name__=='__main__':
    unittest.main()
