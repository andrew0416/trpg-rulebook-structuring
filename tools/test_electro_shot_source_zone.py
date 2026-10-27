"""Native Electro Shot area creation, timed lifetime and ordinary movement consumers."""
from pathlib import Path
from unittest.mock import patch
import json
from copy import deepcopy
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine')]
from engine import Rules,Engine,Combatant
from grid import Grid
import combat_timing as TIME
import electro_shot as ELECTRO
import movement_actions as MOVEMENT
import effects as FX
import turn as TURN
import effect_contracts as CONTRACTS
import passive_events as PASSIVE
import move_defense_reactions as DEFENSE
import action_resources as RESOURCES


class ElectroShotZoneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')

    def world(self,*,extra=False,weather=None):
        e=Engine(self.rules,seed=8301)
        # A single legal corridor gives the ordinary pathfinder an explicit route.
        e.grid=Grid(14,3,blocking={(x,y) for x in range(14) for y in (0,2)})
        def add(uid,pos,side,speed):
            actor=Combatant(self.rules,dict(id=uid,name=uid,kind='trainer',level=10,size='중형',
                stats=dict(hp=100,atk=10,**{'def':10},spa=10,spd=10,spe=speed),
                types=['노말'],skills={'육상':3,'곡예':3},moves=[],abilities=[],items={},movement={'land':2}))
            e.gm.add_combatant(actor,pos=pos,side=side,reason='actual source-zone fixture participant')
            return actor
        user=add('electro/user',(1,1),'party',20)
        ally=add('electro/ally',(2,1),'party',15)
        enemy=add('electro/enemy',(10,1),'wild',5)
        other=add('electro/other',(4,1),'party',10) if extra else None
        e.gm.set_move(user,ELECTRO.SOURCE,True,reason='actual learned source Move')
        e.gm.set_weather(weather,rounds=None,reason='observed fixture weather')
        e.start_round(e.everyone);e.start_of_turn(user,initiative_count=20)
        return e,user,ally,enemy,other

    def cast(self,e,user,enemy):
        with patch.object(e,'d20',return_value=1):
            e.use_move_on(user,enemy,ELECTRO.SOURCE,e.everyone,aim=(5,1),set_damage=True)
        return [r for r in TIME.records(user) if ELECTRO.KEY in r]

    def ally_turn(self,e,user,ally):
        e.end_of_turn(user);e.start_of_turn(ally,initiative_count=15)

    def test_all_missed_native_recipients_create_one_original_line(self):
        e,user,ally,enemy,other=self.world(extra=True)
        rows=self.cast(e,user,enemy)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][ELECTRO.KEY]['cells'],{(2,1),(3,1),(4,1),(5,1)})
        self.assertEqual(user.move_uses[ELECTRO.SOURCE],1)
        self.assertEqual((user.budget['standard'],user.budget['shift']),(0,0))
        completion=e._move_completions[rows[0][ELECTRO.KEY]['completion']]
        self.assertEqual(set(completion['results']),{ally.entity_id,other.entity_id})
        self.assertTrue(all(not r['hit'] for r in completion['results'].values()))
        self.assertFalse(e.zone_rules)

    def test_empty_actual_area_creates_one_field_without_fake_recipient(self):
        e,user,ally,enemy,_=self.world()
        e.gm.set_position(ally,(12,1),reason='observed ally outside line')
        rows=self.cast(e,user,enemy)
        self.assertEqual(len(rows),1)
        completion=e._move_completions[rows[0][ELECTRO.KEY]['completion']]
        self.assertEqual(completion['targets'],[])
        self.assertEqual(completion['results'],{})
        self.assertEqual(user.move_uses[ELECTRO.SOURCE],1)

    def test_free_exit_keeps_remaining_normal_movement_and_one_shift(self):
        e,user,ally,enemy,_=self.world();self.cast(e,user,enemy)
        self.ally_turn(e,user,ally)
        result=e.approach(ally,enemy)
        self.assertEqual(ally.pos,(8,1))
        self.assertEqual((result['distance'],result['charged_distance']),(6,2))
        self.assertEqual((ally.budget['standard'],ally.budget['shift']),(1,0))

    def test_staying_inside_or_looping_is_not_a_free_exit(self):
        for path in [[(3,1),(4,1)],[(3,1),(2,1),(3,1),(4,1),(5,1),(6,1)]]:
            with self.subTest(path=path):
                e,user,ally,enemy,_=self.world();self.cast(e,user,enemy);self.ally_turn(e,user,ally)
                self.assertTrue(TURN.spend(e,ally,'shift','actual chosen path',movement=True))
                result=MOVEMENT.follow_paid_path(e,ally,path,mode='육상',maximum_distance=1)
                self.assertEqual(result['distance'],1);self.assertEqual(ally.pos,(3,1))

    def test_actual_paid_path_reaches_adjacency_midway_then_resumes_paid_movement(self):
        e,user,ally,enemy,_=self.world()
        e.grid.blocking.difference_update({(2,0),(3,0)})
        e.gm.set_position(ally,(3,0),reason='observed movement starts outside user adjacency')
        e.gm.set_movement_capabilities(ally,{'land':3},basis='current',reason='actual three-metre movement capability')
        self.cast(e,user,enemy);self.ally_turn(e,user,ally)
        self.assertTrue(TURN.spend(e,ally,'shift','actual chosen movement path',movement=True))
        result=MOVEMENT.follow_paid_path(e,ally,[(2,0),(2,1),(3,1),(4,1),(5,1),(6,1),(7,1)],mode='육상',maximum_distance=3)
        self.assertEqual((result['distance'],result['charged_distance']),(7,3));self.assertEqual(ally.pos,(7,1))
        self.assertEqual((ally.budget['standard'],ally.budget['shift']),(1,0))

    def test_enemy_and_nonadjacent_ally_receive_no_free_exit(self):
        for side,pos in [('wild',(2,1)),('party',(3,1))]:
            with self.subTest(side=side,pos=pos):
                e,user,ally,enemy,_=self.world();self.cast(e,user,enemy)
                ally.side=side;e.gm.set_position(ally,pos,reason='observed relation and entry boundary')
                self.ally_turn(e,user,ally)
                e.approach(ally,enemy)
                self.assertEqual(ally.pos,(pos[0]+2,1))

    def test_round_timer_survives_creation_round_and_expires_at_same_next_count(self):
        e,user,ally,enemy,_=self.world();self.cast(e,user,enemy)
        e.end_of_turn(user);e.end_round()
        self.assertEqual(len(TIME.records(user)),1)
        e.start_round(e.everyone);e.at_initiative_count(21)
        self.assertEqual(len(TIME.records(user)),1)
        e.at_initiative_count(20)
        self.assertEqual(TIME.records(user),[])

    def test_json_restore_retains_actual_map_source_area_and_movement_benefit(self):
        e,user,ally,enemy,_=self.world();self.cast(e,user,enemy)
        restored=Engine.import_state(self.rules,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
        by_id={a.entity_id:a for a in restored.everyone}
        ru,ra,rt=(by_id[a.entity_id] for a in (user,ally,enemy))
        row=next(r for r in TIME.records(ru) if ELECTRO.KEY in r)
        self.assertEqual(row[ELECTRO.KEY]['map_id'],restored.grid._tunnel_map_id)
        self.ally_turn(restored,ru,ra);restored.approach(ra,rt)
        self.assertEqual(ra.pos,(8,1));self.assertEqual(ally.pos,(2,1))

    def test_tampered_area_deadline_and_producer_are_rejected_by_world_codec(self):
        for key in ('area','deadline','producer'):
            with self.subTest(key=key):
                e,user,ally,enemy,_=self.world();row=self.cast(e,user,enemy)[0]
                if key=='area':row[ELECTRO.KEY]['cells'].add((9,1))
                elif key=='deadline':row['count_deadline']=(99,20)
                else:row[ELECTRO.KEY]['completion']='move-complete:missing'
                with self.assertRaises(ValueError):e.export_state()

    def test_exit_does_not_bypass_blocked_cells_or_departure_reactions(self):
        for boundary in ('blocked','reaction'):
            with self.subTest(boundary=boundary):
                e,user,ally,enemy,_=self.world();self.cast(e,user,enemy);self.ally_turn(e,user,ally)
                if boundary=='blocked':
                    e.grid.blocking.add((3,1));e.approach(ally,enemy)
                else:
                    with patch.object(MOVEMENT,'departure',return_value=False) as departure:
                        e.approach(ally,enemy)
                    departure.assert_called_once()
                self.assertEqual(ally.pos,(2,1));self.assertEqual(ally.budget['shift'],0)

    def test_interrupted_native_paid_prefix_resumes_same_exit_without_repaying(self):
        e,user,ally,enemy,_=self.world();self.cast(e,user,enemy);self.ally_turn(e,user,ally)
        self.assertTrue(TURN.spend(e,ally,'shift','actual chosen path',movement=True))
        path=[(x,1) for x in range(3,9)];progress={}
        with patch.object(MOVEMENT,'departure',side_effect=[True,False]):
            first=MOVEMENT.follow_paid_path(e,ally,path,mode='육상',maximum_distance=2,progress=progress)
        self.assertEqual((ally.pos,first['distance'],first['charged_distance']),((3,1),1,0))
        self.assertEqual(progress['next'],1)
        result=MOVEMENT.follow_paid_path(e,ally,path,mode='육상',maximum_distance=2,progress=progress)
        self.assertEqual((ally.pos,result['distance'],result['charged_distance']),((8,1),6,2))
        self.assertNotIn('electro_shot_exits',progress)
        self.assertEqual(ally.budget['shift'],0)

    def test_zero_capability_and_replacement_map_do_not_gain_movement(self):
        for boundary in ('zero','map'):
            with self.subTest(boundary=boundary):
                e,user,ally,enemy,_=self.world();self.cast(e,user,enemy);self.ally_turn(e,user,ally)
                if boundary=='zero':
                    e.gm.set_movement_capabilities(ally,{'land':0},basis='current',reason='observed unavailable movement')
                else:e.grid=Grid(14,3,blocking={(x,y) for x in range(14) for y in (0,2)})
                e.approach(ally,enemy)
                self.assertEqual(ally.pos,(2,1) if boundary=='zero' else (4,1))

    def test_missing_mapped_context_rejects_before_action_frequency_or_rng(self):
        e,user,ally,enemy,_=self.world();e.grid=None
        before=(dict(user.budget),dict(user.move_uses),e.rng.getstate())
        with self.assertRaises(ValueError):e.use_move(user,ally,ELECTRO.SOURCE)
        self.assertEqual((user.budget,user.move_uses,e.rng.getstate()),before)

    def test_direct_singleton_far_target_and_omitted_actual_targets_reject_atomically(self):
        for kind in ('inside','outside','omitted'):
            with self.subTest(kind=kind):
                e,user,ally,enemy,_=self.world();before=deepcopy(e.export_state())
                with self.assertRaises(ValueError):
                    if kind=='omitted':e.use_move_on(user,enemy,ELECTRO.SOURCE,[user,enemy],aim=(5,1))
                    else:e.use_move(user,ally if kind=='inside' else enemy,ELECTRO.SOURCE,aim=(5,1))
                self.assertEqual(e.export_state(),before)

    def test_complete_line_never_hits_the_outside_primary(self):
        e,user,ally,enemy,_=self.world();outside_hp=enemy.hp
        with patch.object(Engine,'d20',return_value=10):
            e.use_move_on(user,enemy,ELECTRO.SOURCE,e.everyone,aim=(5,1),set_damage=True)
        self.assertEqual(enemy.hp,outside_hp)
        completion=next(r for r in e._move_completions.values() if r['move_id']==ELECTRO.SOURCE)
        self.assertEqual(completion['targets'],[ally])
        self.assertEqual(set(completion['results']),{ally.entity_id})

    def test_coordinated_saved_cell_copy_extension_rejects_on_import(self):
        e,user,ally,enemy,_=self.world();row=self.cast(e,user,enemy)[0]
        completion_id=row[ELECTRO.KEY]['completion'];state=deepcopy(e.export_state());nodes=state['nodes']
        def fields(node):return {k:v for k,v in node['items'] if type(k)is str}
        completion=next(fields(n) for n in nodes.values() if n['kind']=='dict'
                        and fields(n).get('id')==completion_id and fields(n).get('move_id')==ELECTRO.SOURCE)
        move=fields(nodes[completion['move']['$ref']]);binding=fields(nodes[completion[ELECTRO.KEY]['$ref']])
        zone=next(fields(n) for n in nodes.values() if n['kind']=='dict'
                  and fields(n).get('completion')==completion_id and 'birth_count' in fields(n) and 'effect' in fields(n))
        coordinate='n'+str(len(nodes));nodes[coordinate]={'kind':'tuple','items':[9,1]}
        for reference in (move['_effect_area_cells'],binding['cells'],zone['cells']):
            nodes[reference['$ref']]['items'].append({'$ref':coordinate})
        with self.assertRaises(ValueError):Engine.import_state(self.rules,state)

    def test_interrupted_end_extension_rejects_before_resumed_movement(self):
        e,user,ally,enemy,_=self.world();self.cast(e,user,enemy);self.ally_turn(e,user,ally)
        self.assertTrue(TURN.spend(e,ally,'shift','actual retained path',movement=True))
        path=[(x,1) for x in range(3,9)];progress={}
        with patch.object(MOVEMENT,'departure',side_effect=[True,False]):
            MOVEMENT.follow_paid_path(e,ally,path,mode='육상',maximum_distance=2,progress=progress)
        span=next(iter(progress['electro_shot_exits'].values()));self.assertEqual(span['end'],4)
        span['end']=6;before=(ally.pos,dict(ally.budget),e.rng.getstate())
        with self.assertRaisesRegex(ValueError,'exact first outside cell'):
            MOVEMENT.follow_paid_path(e,ally,path,mode='육상',maximum_distance=2,progress=progress)
        self.assertEqual((ally.pos,ally.budget,e.rng.getstate()),before)

    def test_claimed_discount_or_changed_native_step_cannot_waive_paid_suffix(self):
        for tamper in ('charged','receipt'):
            with self.subTest(tamper=tamper):
                e,user,ally,enemy,_=self.world();self.cast(e,user,enemy);self.ally_turn(e,user,ally)
                self.assertTrue(TURN.spend(e,ally,'shift','actual retained paid suffix',movement=True))
                path=[(x,1) for x in range(3,9)];progress={}
                with patch.object(MOVEMENT,'departure',side_effect=[True]*5+[False]):
                    result=MOVEMENT.follow_paid_path(e,ally,path,mode='육상',maximum_distance=2,progress=progress)
                self.assertEqual((result['distance'],result['charged_distance'],ally.pos),(5,1,(7,1)))
                if tamper=='charged':progress['charged_distance']=0
                else:e._effect_dispatch_receipts[progress['electro_shot_motion']['receipts'][0]]['effect']['distance']=2
                before=(ally.pos,dict(ally.budget),e.rng.getstate())
                with self.assertRaises(ValueError):
                    MOVEMENT.follow_paid_path(e,ally,path,mode='육상',maximum_distance=2,progress=progress)
                self.assertEqual((ally.pos,ally.budget,e.rng.getstate()),before)

    def test_unissued_or_other_actor_trigger_receipt_cannot_grant_an_exit(self):
        e,user,ally,enemy,_=self.world();self.cast(e,user,enemy);self.ally_turn(e,user,ally)
        self.assertTrue(TURN.spend(e,ally,'shift','actual native trigger',movement=True))
        path=[(x,1) for x in range(3,9)];progress={}
        with patch.object(MOVEMENT,'departure',side_effect=[True,False]):
            MOVEMENT.follow_paid_path(e,ally,path,mode='육상',maximum_distance=2,progress=progress)
        copied=deepcopy(progress,{id(k):k for k in e._effect_dispatch_receipts})
        next(iter(copied['electro_shot_exits'].values()))['receipt']=object()
        with self.assertRaises(ValueError):ELECTRO.restore_exits(e,ally,copied)
        copied=deepcopy(progress,{id(k):k for k in e._effect_dispatch_receipts})
        copied['electro_shot_motion']['actor_id']=enemy.entity_id
        with self.assertRaises(ValueError):ELECTRO.restore_exits(e,enemy,copied)
        other,other_user,other_ally,other_enemy,_=self.world();self.cast(other,other_user,other_enemy)
        with self.assertRaises(ValueError):ELECTRO.restore_exits(other,other_ally,progress)

    def test_same_world_same_actor_same_path_cannot_replay_an_old_movement_receipt(self):
        e,user,ally,enemy,_=self.world();self.cast(e,user,enemy);self.ally_turn(e,user,ally)
        self.assertTrue(TURN.spend(e,ally,'shift','original native paid path',movement=True))
        path=[(x,1) for x in range(3,9)];original={}
        MOVEMENT.follow_paid_path(e,ally,path,mode='육상',maximum_distance=2,progress=original)
        self.assertEqual(ally.pos,(8,1));token=original['electro_shot_motion']['receipts'][0]
        self.assertIs(e._effect_dispatch_receipts[token]['native_movement_progress'],original)
        e.gm.set_position(user,(12,1),reason='actual source moved away from later departure')
        e.gm.set_position(ally,(3,1),reason='actual later paid-path prefix position')
        forged=deepcopy(original,{id(k):k for k in e._effect_dispatch_receipts})
        forged.update(next=1,distance=1,charged_distance=0,position=(3,1),phase='ready')
        forged['electro_shot_motion']['receipts']=[token]
        completion=e._effect_dispatch_receipts[token]['effect']['completion']
        forged['electro_shot_exits']={completion:{'next':1,'end':4,'receipt':token}}
        before=(ally.pos,dict(ally.budget),e.rng.getstate())
        with self.assertRaisesRegex(ValueError,'another native paid movement owner'):
            MOVEMENT.follow_paid_path(e,ally,path,mode='육상',maximum_distance=2,progress=forged)
        self.assertEqual((ally.pos,ally.budget,e.rng.getstate()),before)

    def test_fractional_aerial_exit_distance_survives_actual_prefix_restore(self):
        e,user,ally,enemy,_=self.world();self.cast(e,user,enemy);self.ally_turn(e,user,ally)
        e.gm.set_movement_capabilities(ally,{'land':2,'sky':6},basis='current',reason='observed flying capability')
        self.assertTrue(TURN.spend(e,ally,'shift','actual measured aerial path',movement=True))
        path=[{'position':(x,1),'altitude':1,**({'gm_distance':1.5} if x==3 else {})} for x in range(3,7)]
        progress=ally.spec.setdefault('source_exit_progress',{})
        with patch.object(MOVEMENT,'departure',side_effect=[True,False]):
            first=MOVEMENT.follow_paid_path(e,ally,path,mode='sky',maximum_distance=6,progress=progress)
        self.assertEqual((first['distance'],first['charged_distance']),(1.5,0))
        e,user,ally,enemy=self.restore_world(e,user,ally,enemy)
        progress=ally.spec['source_exit_progress']
        result=MOVEMENT.follow_paid_path(e,ally,path,mode='sky',maximum_distance=6,progress=progress)
        self.assertEqual((result['distance'],result['charged_distance']),(4.5,0))
        self.assertEqual(ally.pos,(6,1));self.restore_world(e,user,ally,enemy)

    def perception_wait(self):
        e,user,ally,helper,_=self.world();e.grid.blocking.clear()
        helper.side='party';e.gm.set_position(helper,(1,0),reason='actual allied area attacker')
        self.cast(e,user,helper)
        e.gm.set_ability(ally,'감지',True,reason='actual owned core Perception')
        e.gm.set_movement_capabilities(ally,{'land':6},basis='current',reason='actual full Shift capability')
        e.gm.set_move(helper,'move/지진',True,reason='actual known allied area attack')
        e.watch_move_defense(ally,[{'actor_id':ally.entity_id,'source':DEFENSE.PERCEPTION}],reason='actual owned Perception watch')
        e.end_of_turn(user);e.start_of_turn(helper,initiative_count=5)
        with patch.object(Engine,'d20',return_value=10),self.assertRaises(PASSIVE.PassiveEventPending):
            e.use_move_on(helper,ally,'move/지진',e.everyone,set_damage=True)
        return e,user,ally,helper,e._passive_pending

    def restore_world(self,e,*actors):
        restored=Engine.import_state(self.rules,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
        by_id={a.entity_id:a for a in restored.everyone}
        return (restored,*(by_id[a.entity_id] for a in actors))

    def test_actual_core_perception_retains_physical_distance_charge_and_codec_contract(self):
        e,user,ally,helper,event=self.perception_wait()
        e,user,ally,helper=self.restore_world(e,user,ally,helper)
        path=[(x,1) for x in range(2,8)]
        e.choose_move_defense(event,ally,use=True,options={'path':path,'mode':'land'},reason='actual native exit path')
        attempt=DEFENSE._defense(e,e._passive_events[event])['attempts'][0]
        self.assertEqual((attempt['movement']['distance'],attempt['movement']['charged_distance']),(5,1))
        self.assertEqual(attempt['movement']['distance'],attempt['plan']['distance'])
        for token in attempt['progress']['electro_shot_motion']['receipts']:
            self.assertIs(e._effect_dispatch_receipts[token]['native_movement_progress'],attempt['progress'])
        self.assertEqual(ally.pos,(7,1));self.assertEqual(RESOURCES.pending(ally),{'shift':1})
        e,user,ally,helper=self.restore_world(e,user,ally,helper)
        self.assertTrue(e.validate_state()['valid']);self.assertEqual(ally.pos,(7,1))
        self.assertEqual(RESOURCES.pending(ally),{'shift':1})

    def test_completed_discounted_perception_history_survives_expiry_and_encounter_end(self):
        e,user,ally,helper,event=self.perception_wait()
        e.choose_move_defense(event,ally,use=True,options={'path':[(x,1) for x in range(2,8)],'mode':'land'},reason='actual discounted Perception before expiry')
        e.end_of_turn(helper);e.end_round();e.start_round(e.everyone);e.at_initiative_count(20)
        self.assertFalse(any(ELECTRO.KEY in row for row in TIME.records(user)))
        e,user,ally,helper=self.restore_world(e,user,ally,helper)
        attempt=DEFENSE._defense(e,e._passive_events[event])['attempts'][0]
        self.assertEqual((attempt['movement']['distance'],attempt['movement']['charged_distance']),(5,1))
        for token in attempt['progress']['electro_shot_motion']['receipts']:
            self.assertIs(e._effect_dispatch_receipts[token]['native_movement_progress'],attempt['progress'])
        e.gm.set_position(helper,(2,1),reason='actual later movement begins in the expired line')
        e.start_of_turn(helper,initiative_count=5);later=e.approach(helper,ally)
        self.assertEqual((helper.pos,later['distance']),((4,1),2));self.assertNotIn('charged_distance',later)
        e.end_of_turn(helper);e.end_encounter(e.everyone,round_elapsed_seconds=0)
        e,user,ally,helper=self.restore_world(e,user,ally,helper)
        self.assertFalse(e.encounter_active);self.assertFalse(any(ELECTRO.KEY in row for row in TIME.records(user)))
        attempt=DEFENSE._defense(e,e._passive_events[event])['attempts'][0]
        self.assertEqual((attempt['movement']['distance'],attempt['movement']['charged_distance']),(5,1))
        self.assertTrue(e.validate_state()['valid'])

    def test_actual_perception_prefix_cold_restore_and_span_tamper_rejection(self):
        e,user,ally,helper,event=self.perception_wait();original=MOVEMENT.departure
        def blocked(engine,actor,destination,height,**options):
            result=original(engine,actor,destination,height,**options)
            if actor.entity_id==ally.entity_id and destination==(4,1):engine.grid.blocking.add(destination)
            return result
        with patch.object(MOVEMENT,'departure',side_effect=blocked),self.assertRaises(PASSIVE.PassiveEventPending):
            e.choose_move_defense(event,ally,use=True,options={'path':[(x,1) for x in range(2,8)],'mode':'land'},reason='actual interrupted native exit')
        self.assertEqual(ally.pos,(3,1));state=deepcopy(e.export_state())
        spans=[]
        for node in state['nodes'].values():
            if node['kind']=='dict':
                fields={k:v for k,v in node['items'] if type(k)is str}
                if set(fields)=={'next','end','receipt'} and fields['next']==1 and fields['end']==4:
                    spans.append(node)
        self.assertEqual(len(spans),1)
        for pair in spans[0]['items']:
            if pair[0]=='end':pair[1]=5
        with self.assertRaisesRegex(ValueError,'exact first outside cell'):Engine.import_state(self.rules,state)
        e,user,ally,helper=self.restore_world(e,user,ally,helper);e.grid.blocking.remove((4,1));rng=e.rng.getstate()
        e.deliver_passive_event(event)
        attempt=DEFENSE._defense(e,e._passive_events[event])['attempts'][0]
        self.assertEqual((attempt['movement']['distance'],attempt['movement']['charged_distance']),(5,1))
        self.assertEqual(ally.pos,(7,1));self.assertEqual(e.rng.getstate(),rng)
        self.assertEqual(RESOURCES.pending(ally),{'shift':1});self.restore_world(e,user,ally,helper)

    def test_encounter_end_removes_zone_and_no_generic_zone_waiver_exists(self):
        e,user,ally,enemy,_=self.world();self.cast(e,user,enemy)
        e.end_of_turn(user);e.end_encounter(e.everyone,round_elapsed_seconds=0)
        self.assertFalse(any(ELECTRO.KEY in r for r in TIME.records(user)))
        with self.assertRaises(CONTRACTS.EffectContractError):
            FX.preflight_effects(e,user,ally,[{'type':'zone_rule','allies_adjacent_free_shift':True,'duration':'2라운드'}],ELECTRO.SOURCE)


if __name__=='__main__':unittest.main(verbosity=2)
