"""Remaining G-Max target-turn and ordinary Disabled boundaries on native actions."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_gmax_moves as F
from builder import build_pokemon,build_trainer
from engine import Combatant,Engine,Rules
from grid import Grid
import combat_timing as CLOCK
import condition_instances as CONDITIONS
import gmax_moves as GMAX
import native_scenario_fixture as NATIVE
import pokemon_party as PARTY
import state_codec as CODEC
import vortex_state as VORTEX
import world_entities as WORLD


class GMaxRemainingQ27Tests(unittest.TestCase):
    setUpClass=classmethod(F.GMaxMoveTests.setUpClass.__func__)

    def scene(self,clause,*,wrap=False):
        declaration=self.declarations[clause]
        e=Engine(self.r,seed=27);e.grid=Grid(20,12)
        owner=Combatant(self.r,build_trainer(self.r,'actual recall owner',30,
            {'hp':200,'atk':30,'def':30,'spa':30,'spd':30,'spe':30},
            extra={'side':'foe','pos':(7,7),'items':{'회복약':2}}))
        source_owner=Combatant(self.r,build_trainer(self.r,'actual G-Max owner',30,
            {'hp':200,'atk':30,'def':30,'spa':30,'spd':30,'spe':30},
            extra={'side':'party','pos':(4,5)}))
        actor=Combatant(self.r,build_pokemon(self.r,declaration['species_eng'],50,
            abilities=[],side='party',extra={'pos':(5,5),'trainer_id':source_owner.entity_id}))
        target=Combatant(self.r,build_pokemon(self.r,'Pikachu',50,abilities=[],
            moves=['move/몸통박치기','move/울음소리','move/도발'],side='foe',
            extra={'trainer_id':owner.entity_id,'pos':(6,5)}))
        for c in (source_owner,owner,actor,target):e.gm.add_combatant(c)
        e.gm.observe_loyalty(actor,6,reason='actual current-owner G-Max command willingness')
        e.gm.set_stat(target,'hp',value=300,reason='actual high-HP target for four residual ticks')
        e.gm.set_hp(target,value=target.max_hp,reason='actual initial full target HP')
        e.gm.observe_loyalty(target,6,reason='actual willing owned target')
        PARTY.configure(e,owner,mode='unlimited',roster=(target,),reason='explicit current fixture party scope')
        e.configure_party_combat(owner,battle_mode='full_contact',reason='actual paid recall and send scope')
        derived=self.r.move(declaration['move_id'])
        base=next(mid for mid in actor.moves if self.r.move(mid)['type']==derived['type']
            and self.r.move(mid)['class'] in ('물리','특수'))
        if wrap:e.gm.set_move(actor,'move/조이기',reason='actual already learned Wrap for the independent Vortex')
        e.start_round(e.everyone);e.start_of_turn(actor,initiative_count=20)
        e.enter_gigantamax(actor,source_id='test/q27-current-source',reason='actual source-bound G-Max entry')
        return e,actor,target,owner,base,declaration['move_id']

    def close(self,e):
        if e._active_turn_actor is not None:e.end_of_turn(e._active_turn_actor)

    def round(self,e):
        self.close(e);e.end_round();e.start_round(e.everyone)

    def use(self,e,actor,target,move):
        with patch.object(Engine,'d20',return_value=20):
            return e.use_move_on(actor,target,move,e.everyone,set_damage=True)

    def activate(self,e,actor,target,base,move):
        with patch.object(Engine,'d20',return_value=20):
            e.use_gmax_move_on(actor,target,base,move,e.everyone,set_damage=True)
        self.assertEqual(actor.budget['standard'],0)
        self.assertEqual(e._gmax_payload_receipts[-1]['target_ids'],
            [c.entity_id for c in e.everyone if c.side=='foe'])

    def blocked_move(self,e,actor,target,move):
        def facts():
            return deepcopy((actor.budget,actor.move_uses,actor.hp,target.hp,
                actor._action_history,actor.spec.get(GMAX.EFFECTS),
                tuple(getattr(e,'_move_completions',{})),e.rng.getstate()))
        before=facts()
        self.assertEqual(self.use(e,actor,target,move),0)
        self.assertEqual(facts(),before)

    def cold(self,e,*actors):
        identities=[c.entity_id for c in actors]
        fresh=Rules(str(e.r.root),ruleset='all')
        loaded=CODEC.load_engine(fresh,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
        index=WORLD.actor_index(loaded)
        return (loaded,*(index[uid] for uid in identities))

    def depletion(self):
        e,a,t,o,base,move=self.scene('C2CSV-MOVE-R1046')
        self.close(e);e.start_of_turn(t,initiative_count=10)
        self.use(e,t,a,'move/몸통박치기')
        self.assertEqual(t.last_move,'move/몸통박치기')
        self.assertEqual(t.budget['standard'],0)
        self.round(e);e.start_of_turn(a,initiative_count=20)
        self.activate(e,a,t,base,move)
        self.assertEqual(CONDITIONS.records(t,'사슬묶기')[0]['effect']['move_id'],'move/몸통박치기')
        self.assertIn('억압',t.conditions)
        return e,a,t,o

    def test_sandblast_four_native_ticks_keep_recall_blocked_through_fourth_target_turn_end(self):
        e,a,t,o,base,move=self.scene('C2CSV-MOVE-R1039')
        self.activate(e,a,t,base,move);self.close(e)
        initial=t.hp;loss=t.base_max_hp//6
        for number in range(1,5):
            if number>1:self.round(e)
            e.start_of_turn(t,initiative_count=10)
            self.assertEqual(t.hp,initial-number*loss)
            row=next(r for r in t.spec[GMAX.EFFECTS] if r['kind']=='sandblast')
            self.assertEqual(row['turns'],4-number)
            self.assertIn('수렁',t.conditions)
            timed=next(r for r in CLOCK.records(t) if r.get('gmax_parent_id')==row['id'])
            self.assertTrue(timed['manual_end'])
            self.assertNotIn('turn_start_deadline',timed)
            self.assertNotIn('count_deadline',timed)
            if number==4:
                self.assertEqual(row['expires_after_target_turn'],t.custom_conditions['combat_turn_serial'])
                NATIVE.assert_rejected_unchanged(e,lambda:e.act_on_party(o,recall=(t,),
                    request_id='still-protected-fourth-turn',reason='actual fourth-turn recall attempt'),
                    reason_pattern='Trapped')
            e.end_of_turn(t)
            self.assertEqual('수렁' in t.conditions,number<4)
        self.assertFalse(t.spec.get(GMAX.EFFECTS))
        self.assertEqual(t.hp,initial-4*loss)
        e.start_of_turn(o,initiative_count=5)
        result=e.act_on_party(o,recall=(t,),request_id='after-fourth-target-end',reason='actual now-permitted recall')
        self.assertEqual(result['recalled'],[t.entity_id]);self.assertFalse(t.on_field)
        self.assertEqual(o.budget['shift'],0)
        self.assertTrue(e.validate_state()['valid'])

    def test_final_target_turn_fresh_rules_and_gm_restore_preserve_later_native_vortex_owner(self):
        e,a,t,o,base,move=self.scene('C2CSV-MOVE-R1039',wrap=True)
        self.activate(e,a,t,base,move);self.close(e)
        for number in range(1,4):
            if number>1:self.round(e)
            e.start_of_turn(t,initiative_count=10);e.end_of_turn(t)
        self.round(e);e.start_of_turn(a,initiative_count=20)
        self.use(e,a,t,'move/조이기')
        self.assertIn('조이기',t.conditions)
        self.assertNotIn('수렁',t.custom_conditions[VORTEX.KEY]['owned'])
        self.close(e);e.start_of_turn(t,initiative_count=10)
        final=deepcopy(next(r for r in t.spec[GMAX.EFFECTS] if r['kind']=='sandblast'))
        self.assertEqual(final['turns'],0);self.assertIn('수렁',t.conditions)
        e.gm.snapshot('actual-fourth-protected-turn')
        loaded,la,lt,lo=self.cold(e,a,t,o)
        self.assertEqual(lt.spec[GMAX.EFFECTS],t.spec[GMAX.EFFECTS])
        with patch.object(loaded,'d20',return_value=1):loaded.end_of_turn(lt)
        self.assertFalse(lt.spec.get(GMAX.EFFECTS))
        self.assertIn('조이기',lt.conditions);self.assertIn('수렁',lt.conditions)
        self.assertIn('수렁',lt.custom_conditions[VORTEX.KEY]['owned'])
        self.assertTrue(loaded.cure_status(lt,'조이기'))
        self.assertNotIn('수렁',lt.conditions)
        e.gm.restore('actual-fourth-protected-turn',reason='restore actual pending fourth-turn end')
        self.assertEqual(t.spec[GMAX.EFFECTS],[final])
        with patch.object(Engine,'d20',return_value=1):e.end_of_turn(t)
        self.assertIn('수렁',t.custom_conditions[VORTEX.KEY]['owned'])
        self.assertTrue(e.validate_state()['valid']);self.assertTrue(loaded.validate_state()['valid'])

    def test_native_disabled_item_cure_restores_at_will_but_encounter_suppressed_keeps_own_scope(self):
        e,a,t,o=self.depletion();history=deepcopy(t.spec[GMAX.EFFECTS])
        self.close(e);e.start_of_turn(t,initiative_count=10)
        self.blocked_move(e,t,a,'move/몸통박치기')
        self.blocked_move(e,t,a,'move/도발')
        e.gm.snapshot('actual-disabled-and-encounter-suppressed')
        e,a,t,o=self.cold(e,a,t,o)
        self.close(e);e.start_of_turn(o,initiative_count=5)
        e.use_item(o,'회복약',t)
        self.assertEqual(o.budget['standard'],0)
        self.assertNotIn('사슬묶기',t.conditions);self.assertFalse(CONDITIONS.records(t,'사슬묶기'))
        self.assertIn('억압',t.conditions);self.assertEqual(t.spec[GMAX.EFFECTS],history)
        self.assertTrue(GMAX.move_allowed(e,t,e.r.move('move/몸통박치기'))[0])
        self.round(e);e.start_of_turn(t,initiative_count=10)
        self.blocked_move(e,t,a,'move/도발')
        self.use(e,t,a,'move/몸통박치기');self.assertEqual(t.budget['standard'],0)
        self.assertEqual(t.spec[GMAX.EFFECTS],history)
        self.close(e);e.end_encounter()
        self.assertNotIn('억압',t.conditions);self.assertNotIn(GMAX.EFFECTS,t.spec)
        e.start_round(e.everyone);e.start_of_turn(t,initiative_count=10)
        self.use(e,t,a,'move/도발');self.assertEqual(t.budget['standard'],0)
        self.assertTrue(e.validate_state()['valid'])

    def test_paid_recall_cures_only_disabled_and_gm_restore_keeps_original_exact_move_fact(self):
        e,a,t,o=self.depletion();captured=deepcopy(t.spec[GMAX.EFFECTS])
        self.close(e);e.start_of_turn(o,initiative_count=5)
        e.gm.snapshot('before-actual-depletion-recall')
        result=e.act_on_party(o,recall=(t,),request_id='depletion-ordinary-recall',reason='actual ordinary paid recall')
        self.assertEqual(result['recalled'],[t.entity_id]);self.assertEqual(o.budget['shift'],0)
        self.assertFalse(t.on_field);self.assertNotIn('사슬묶기',t.conditions)
        self.assertFalse(CONDITIONS.records(t,'사슬묶기'))
        self.assertIn('억압',t.conditions);self.assertEqual(t.spec[GMAX.EFFECTS],captured)
        e.gm.restore('before-actual-depletion-recall',reason='restore actual Disabled source and capture fact')
        self.assertTrue(t.on_field);self.assertIn('사슬묶기',t.conditions)
        self.assertEqual(CONDITIONS.records(t,'사슬묶기')[0]['effect']['move_id'],'move/몸통박치기')
        self.assertEqual(t.spec[GMAX.EFFECTS],captured)
        e,a,t,o=self.cold(e,a,t,o)
        e.act_on_party(o,recall=(t,),request_id='depletion-recall-after-restore',reason='actual restored paid recall')
        self.assertNotIn('사슬묶기',t.conditions);self.assertIn('억압',t.conditions)
        self.round(e);e.start_of_turn(o,initiative_count=5)
        e.act_on_party(o,send=((t,(6,5)),),request_id='depletion-actual-send',reason='actual next-round paid release')
        self.assertTrue(t.on_field);self.assertEqual(o.budget['shift'],0)
        self.round(e);e.start_of_turn(t,initiative_count=10)
        self.blocked_move(e,t,a,'move/도발')
        self.use(e,t,a,'move/몸통박치기');self.assertEqual(t.budget['standard'],0)
        self.assertEqual(t.spec[GMAX.EFFECTS],captured)
        self.assertTrue(e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
