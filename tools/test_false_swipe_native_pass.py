"""Selected R485 keeps its HP floor on every actual paid Pass recipient."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine,Rules
from native_scenario_fixture import prepare_scene,assert_rejected_unchanged
import physical_object_attacks as OBJECTS
import passive_events as EVENTS
import world_entities as WORLD

MID='move/칼등치기'


class FalseSwipeNativePassTests(unittest.TestCase):
    def fixture(self,*,hp=20,dr=5,creature=True,rope=False):
        actors=[]
        for key,pos,side in (('user',(0,0),'party'),('target',(2,0) if creature else (9,7),'foe')):
            actors.append({'key':key,'kind':'trainer','sheet':{
                'name':'actual False Swipe '+key,'level':20,
                'stats':dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),
                'moves':[MID,'move/풀베기'],'abilities':[],'pos':pos,
                'extra':{'side':side,'size':'중형','movement':{'land':4}}},
                'body':{'size':'중형','offsets':[(0,0)],'reason':'observed complete Pass body'}})
        e,actors=prepare_scene(ROOT,ruleset='core',seed=485347,grid={'width':12,'height':8},actors=actors)
        a,b=actors['user'],actors['target']
        WORLD.register_object(e,'object',location={'kind':'grid','cell':(1,0)},reason='actual Pass object',
            **({'kind':'item_instance','item_rule_id':'item/다용도-밧줄'} if rope else {}))
        if rope:e.configure_rope(a,'object',length_feet=25,reason='actual utility rope')
        else:e.configure_object_durability(a,'object',max_hp=hp,reduction=dr,minimum_damage=0,
            source='gm/observed-object-profile',reason='observed actual object durability')
        e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
        return e,a,b

    def use(self,e,a,*,damage=999,hit=True,event='false-swipe/1',move=MID,objects=True):
        with patch.object(Engine,'d20',return_value=18):
            return e.use_pass_move(a,move,(4,0),event_id=event,
                object_adjudications={'object':{'hit':hit,'damage_before_dr':damage}} if objects else {},
                source='gm/observed-pass-hit',reason='actual hit and pre-DR damage along the complete Pass path')

    def valid(self,e):
        result=e.validate_state();self.assertTrue(result['valid'],result['issues'])

    def next_turn(self,e,a):
        e.end_of_turn(a)
        e.gm.set_position(a,(0,0),reason='observed return before the next independent Pass')
        e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)

    def test_selected_r485_mixed_path_keeps_native_zero_damage_and_object_floor_after_dr(self):
        e,a,b=self.fixture();e.gm.set_hp(b,value=1,reason='actual one-HP native recipient')
        policy=json.loads((ROOT/OBJECTS.POLICY).read_text(encoding='utf-8'))['moves'][MID]
        self.assertEqual(e.r.move(MID),policy['definition'])
        self.assertEqual(e.r.move(MID)['_source']['record_span'],[485,485])
        self.assertEqual(e.r.move_mech(MID)[0],{'effects_exec':[{'type':'damage_floor','min_target_hp_after':1}]})
        row=self.use(e,a);obj=e._physical_objects['object'];receipt=obj[OBJECTS.FIELD]['attacks'][0]
        self.assertEqual(row['targets'],[['object','object'],['creature',b.entity_id]])
        self.assertEqual([r['dealt'] for r in row['results']],[19,0])
        self.assertEqual((receipt['calculation']['total'],receipt['calculation']['after_defense']),(999,994))
        self.assertEqual((receipt['hp_before'],receipt['hp_after'],receipt['applied_damage']),(20,1,19))
        self.assertEqual((b.hp,a.pos,a.move_uses[MID]),(1,(4,0),1))
        self.assertEqual((a.budget['standard'],a.budget['shift']),(0,0))
        self.assertEqual(a._action_history,['standard','shift'])
        self.assertFalse(WORLD.physical_lifecycle(obj)['destroyed']);self.valid(e)

    def test_one_hp_miss_zero_and_dr_reduced_hits_preserve_exact_object_hp(self):
        for hp,dr,damage,hit,after in ((1,0,999,True,1),(5,10,3,True,5),
                (5,0,0,True,5),(5,0,0,False,5),(5,3,5,True,3)):
            with self.subTest(hp=hp,dr=dr,damage=damage,hit=hit):
                e,a,_=self.fixture(hp=hp,dr=dr,creature=False)
                row=self.use(e,a,damage=damage,hit=hit);obj=e._physical_objects['object']
                receipt=obj[OBJECTS.FIELD]['attacks'][0]
                self.assertEqual((receipt['hp_before'],receipt['hp_after'],receipt['applied_damage']),(hp,after,hp-after))
                self.assertEqual(row['results'][0]['dealt'],hp-after)
                self.assertEqual((a.move_uses[MID],a.pos),(1,(4,0)))
                self.assertFalse(WORLD.physical_lifecycle(obj)['destroyed']);self.valid(e)

    def test_source_material_immunity_remains_before_the_nonsharp_move_floor(self):
        e,a,_=self.fixture(rope=True,creature=False);row=self.use(e,a)
        obj=e._physical_objects['object'];receipt=obj[OBJECTS.FIELD]['attacks'][0]
        self.assertFalse(receipt['material_policy']['allowed']);self.assertEqual(receipt['material_policy']['tags'],[])
        self.assertIsNone(receipt['calculation']);self.assertEqual(row['results'][0]['dealt'],0)
        self.assertEqual(obj[OBJECTS.FIELD]['hp'],20);self.assertEqual(a.move_uses[MID],1)
        self.assertFalse(WORLD.physical_lifecycle(obj)['destroyed']);self.valid(e)

    def test_gm_and_cold_restore_replay_the_same_floor_receipt_without_second_payment(self):
        e,a,_=self.fixture(creature=False);row=self.use(e,a);e.gm.snapshot('floor/one-use')
        self.next_turn(e,a);self.use(e,a,event='false-swipe/2')
        self.assertEqual(a.move_uses[MID],2)
        e.gm.restore('floor/one-use',reason='restore actual first paid Pass')
        saved=json.loads(json.dumps(e.export_state(),ensure_ascii=False))
        loaded=Engine.import_state(Rules(ROOT,ruleset='core'),saved)
        actor=WORLD.actor_index(loaded)[a.entity_id];obj=loaded._physical_objects['object']
        self.assertEqual((actor.move_uses[MID],obj[OBJECTS.FIELD]['hp'],len(obj[OBJECTS.FIELD]['attacks'])),(1,1,1))
        before=loaded.export_state();self.assertEqual(self.use(loaded,actor),row)
        self.assertEqual(loaded.export_state(),before);self.valid(loaded)

    def test_rehashed_floor_damage_calculation_and_path_tampering_cannot_restore(self):
        e,a,_=self.fixture(creature=False);self.use(e,a)
        saved=json.loads(json.dumps(e.export_state(),ensure_ascii=False))
        for corruption in ('floor_hp','floor_damage','after_dr','targets','policy'):
            with self.subTest(corruption=corruption):
                bad=Engine.import_state(e.r,deepcopy(saved));obj=bad._physical_objects['object']
                receipt=obj[OBJECTS.FIELD]['attacks'][0];parent=bad._pass_moves['false-swipe/1']
                if corruption=='floor_hp':
                    receipt['hp_after']=0;receipt['applied_damage']=20;obj[OBJECTS.FIELD]['hp']=0
                elif corruption=='floor_damage':receipt['applied_damage']+=1
                elif corruption=='after_dr':receipt['calculation']['after_defense']+=1
                elif corruption=='targets':parent['targets']=[]
                else:parent['definition_hash']='relabelled-policy'
                if corruption in ('floor_hp','floor_damage'):
                    parent['results'][0]['dealt']=receipt['applied_damage']
                # Matching child/parent hashes cannot replace the selected source's HP math.
                receipt['receipt_hash']=OBJECTS._hash({k:v for k,v in receipt.items() if k!='receipt_hash'})
                parent['receipt_hash']=OBJECTS._hash({k:v for k,v in parent.items() if k!='receipt_hash'})
                self.assertFalse(bad.validate_state()['valid'])
                with self.assertRaises(ValueError):bad.export_state()

    def test_actual_learned_policy_and_complete_pass_path_cannot_be_bypassed(self):
        e,a,b=self.fixture();adj={'object':{'hit':True,'damage_before_dr':999}}
        for operation,reason in (
                (lambda:e.use_move(a,b,MID),'Pass Move requires'),
                (lambda:e.attack_physical_object(a,'object',MID,event_id='direct',hit=True,damage_before_dr=999,
                    source='gm/actual-hit',reason='direct call is not a Pass producer'),'Pass Move requires'),
                (lambda:e.use_pass_move(a,'move/베어가르기',(4,0),event_id='unlearned',object_adjudications=adj,
                    source='gm/actual-hit',reason='actual unlearned Move rejection'),'actual learned or granted'),
                (lambda:self.use(e,a,objects=False),'adjudicate every actual traversed object')):
            assert_rejected_unchanged(e,operation,reason_pattern=reason)
        original=Rules.move_mech
        def changed(r,mid):
            mm,conf=original(r,mid)
            if mid==MID:
                mm=deepcopy(mm);mm['effects_exec'][0]['min_target_hp_after']=2
            return mm,conf
        with patch.object(Rules,'move_mech',changed):
            assert_rejected_unchanged(e,lambda:self.use(e,a),reason_pattern='reviewed selected Move effect/range policy')
        self.valid(e)

    def test_destroyed_zero_hp_object_stays_terminal_and_false_swipe_cannot_revive_it(self):
        e,a,_=self.fixture(hp=2,dr=0,creature=False)
        self.use(e,a,move='move/풀베기',event='cut/destroy');obj=e._physical_objects['object']
        self.assertEqual(obj[OBJECTS.FIELD]['hp'],0);self.assertTrue(WORLD.physical_lifecycle(obj)['destroyed'])
        terminal=deepcopy(obj);self.next_turn(e,a)
        row=self.use(e,a,objects=False)
        self.assertEqual(row['targets'],[]);self.assertEqual(e._physical_objects['object'],terminal)
        self.assertEqual((a.move_uses[MID],a.move_uses['move/풀베기']),(1,1))
        assert_rejected_unchanged(e,lambda:e.attack_physical_object(a,'object',MID,event_id='revive',hit=True,
            damage_before_dr=999,source='gm/actual-hit',reason='destroyed object is not a new live target'),
            reason_pattern='destroyed physical object is not usable')
        self.valid(e)

    def test_paid_pending_native_recipient_restores_before_remaining_object_floor(self):
        for codec in ('gm','json'):
            with self.subTest(codec=codec):
                e,a,b=self.fixture();e.gm.set_position(b,(1,0),reason='actual first native recipient')
                WORLD.observe_location(e,e._physical_objects['object'],{'kind':'grid','cell':(3,0)},
                    reason='actual later physical recipient')
                e.gm.set_hp(b,value=1,reason='actual native HP floor before waiting defense')
                e.gm.set_move(b,'move/판별',reason='actual learned optional Detect')
                e.watch_move_defense(b,[{'actor_id':b.entity_id,'source':'move/판별'}],reason='actual native hit defense')
                with self.assertRaises(EVENTS.PassiveEventPending):self.use(e,a)
                event=e._passive_pending;ids=(a.entity_id,b.entity_id)
                self.assertEqual(e._physical_objects['object'][OBJECTS.FIELD]['hp'],20)
                self.assertEqual(a.move_uses[MID],1)
                if codec=='gm':e.gm.snapshot('floor/wait');e.gm.restore('floor/wait')
                else:
                    e=Engine.import_state(Rules(ROOT,ruleset='core'),json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
                    a,b=[WORLD.actor_index(e)[uid] for uid in ids]
                with patch.object(Engine,'d20',side_effect=AssertionError('saved accuracy cannot reroll')):
                    e.choose_move_defense(event,b,use=False,reason='actual recipient declines optional Detect')
                row=e._pass_moves['false-swipe/1']
                self.assertEqual(row['targets'],[['creature',b.entity_id],['object','object']])
                self.assertEqual([r['dealt'] for r in row['results']],[0,19])
                self.assertEqual((a.pos,a.move_uses[MID],b.hp),((4,0),1,1))
                self.assertEqual(a._action_history,['standard','shift']);self.valid(e)


if __name__=='__main__':unittest.main()
