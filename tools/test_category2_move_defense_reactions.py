"""Native defense reactions preserve accuracy targets and resolve actual recipients.

These shared prerequisites claim no completion for Phantom/Shadow Force.
"""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer
from grid import Grid
import passive_events as PASSIVE
import state_grants as G
import action_resources as RESOURCES


class MoveDefenseReactionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(ROOT,ruleset='core')

    def setUp(self):
        self.e=Engine(self.rules,seed=530)
        self.e.grid=Grid(20,20)
        moves=['move/막치기','move/물대포','move/지진','move/스피드스타',
               'move/전광석화','move/파도타기']
        if self._testMethodName == 'test_area_push_outside_saved_cone_routes_damage_and_stage_effect_to_interceptor':
            moves[-1]='move/바크아웃'
        self.a=Combatant(self.rules,build_pokemon(self.rules,'이상해씨',20,
            name='attacker',moves=moves,extra={'abilities':[],'pos':(2,2),
                'side':'opponent','size':'중형'}))
        self.t=self.trainer('original ally',(3,2))
        self.r=self.trainer('interceptor',(3,5))
        for actor in (self.a,self.t,self.r):self.e.gm.add_combatant(actor)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a,initiative_count=20)

    def trainer(self,name,pos):
        return Combatant(self.rules,build_trainer(self.rules,name,20,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),
            skills={'Athletics':'초보','Acrobatics':'초보'},
            extra={'pos':pos,'side':'party','abilities':[],
                   'movement':{'land':8},'size':'중형'}))

    def watch(self,source='maneuver/근접-가로채기',reactor=None):
        self.e.watch_move_defense(self.t,[{'actor_id':(reactor or self.r).entity_id,
            'source':source}],reason='actual owner declares the next native hit reaction')

    def waiting(self,move='move/막치기',*,area=False):
        before=(self.t.hp,self.r.hp)
        with self.assertRaises(PASSIVE.PassiveEventPending):
            if area:self.e.use_move_on(self.a,self.t,move,self.e.everyone)
            else:self.e.use_move(self.a,self.t,move,set_damage=True)
        self.assertEqual((self.t.hp,self.r.hp),before)
        event=self.e._passive_pending
        self.assertIsNotNone(event)
        self.assertEqual(self.a.move_uses[move],1)
        self.assertEqual(self.a._action_history,['standard'])
        return event

    def choose(self,event,*,use=True,options=None,reactor=None):
        return self.e.choose_move_defense(event,reactor or self.r,use=use,
            options=options,reason='actual pending defense choice')

    def melee(self,*,faces=(6,6,6)):
        return {'path':[(3,5),(3,4),(3,3),(3,2)],'skill':'육상','mode':'land',
                'shove_destination':[4,2],'roll_options':{'fixed':list(faces)}}

    def ranged(self,*,faces=(6,6,6)):
        return {'path':[(4,4),(4,3),(4,2)],'skill':'육상','mode':'land',
                'roll_options':{'fixed':list(faces)}}

    def fresh(self):
        state=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False))
        self.e=Engine.import_state(Rules(ROOT,ruleset='core'),state)
        index={actor.entity_id:actor for actor in self.e.everyone}
        self.a,self.t,self.r=(index[actor.entity_id] for actor in (self.a,self.t,self.r))

    def completion(self):
        rows=list(self.e._move_completions.values())
        self.assertEqual(len(rows),1)
        return rows[0]

    def test_melee_success_hits_interceptor_and_preserves_original_accuracy(self):
        self.watch();event=self.waiting()
        hp=(self.t.hp,self.r.hp)
        self.choose(event,options=self.melee())
        self.assertEqual(self.t.hp,hp[0]);self.assertLess(self.r.hp,hp[1])
        self.assertEqual((self.t.pos,self.r.pos),((4,2),(3,2)))
        self.assertEqual(self.e._active_turn_actor,self.a)
        self.assertEqual(self.a.move_uses['move/막치기'],1)
        self.assertEqual(self.r._action_history,['full'])
        self.assertEqual(RESOURCES.pending(self.r),{'standard':1,'shift':1})
        row=self.completion()
        self.assertEqual(row['targets'],[self.t])
        self.assertEqual(set(row['received']),{self.r.entity_id})
        self.assertEqual(self.e._passive_events[event]['target'],self.t)
        import precise_actions as PRECISE
        self.assertTrue(PRECISE.evidence(self.e,self.t)['attacked'])
        self.assertFalse(PRECISE.evidence(self.e,self.t)['damaging_hit'])
        self.assertTrue(PRECISE.evidence(self.e,self.r)['damaging_hit'])

    def test_melee_failure_moves_real_partial_distance_but_ally_takes_hit(self):
        for faces,expected in (((1,1,1),(3,4)),((1,1,3),(3,4)),
                               ((2,2,2),(3,3)),((2,3,3),(3,3))):
            with self.subTest(total=sum(faces)):
                self.setUp()
                self.watch();event=self.waiting();hp=(self.t.hp,self.r.hp)
                self.choose(event,options=self.melee(faces=faces))
                self.assertLess(self.t.hp,hp[0]);self.assertEqual(self.r.hp,hp[1])
                self.assertEqual((self.t.pos,self.r.pos),((3,2),expected))
                self.assertEqual(self.r._action_history,['full'])
                self.assertEqual(RESOURCES.pending(self.r),{'standard':1,'shift':1})
                attempt=self.completion()['defense'][self.t.entity_id]['attempts'][0]
                self.assertEqual((attempt['check_total'],attempt['dc'],attempt['outcome']),
                                 (sum(faces),9,'failed'))

    def test_ranged_success_uses_between_cell_and_preserves_original_target(self):
        self.t.pos=(6,2);self.r.pos=(4,4)
        self.watch('maneuver/원거리-가로채기');event=self.waiting('move/물대포')
        hp=(self.t.hp,self.r.hp)
        self.choose(event,options=self.ranged())
        self.assertEqual(self.r.pos,(4,2));self.assertEqual(self.t.pos,(6,2))
        self.assertEqual(self.t.hp,hp[0]);self.assertLess(self.r.hp,hp[1])
        self.assertEqual(self.completion()['targets'],[self.t])

    def test_ranged_failure_still_moves_roll_divided_by_two(self):
        self.t.pos=(6,2);self.r.pos=(4,4)
        self.watch('maneuver/원거리-가로채기');event=self.waiting('move/물대포')
        hp=(self.t.hp,self.r.hp)
        self.choose(event,options=self.ranged(faces=(1,1,1)))
        self.assertEqual(self.r.pos,(4,3))
        self.assertLess(self.t.hp,hp[0]);self.assertEqual(self.r.hp,hp[1])

    def test_decline_has_no_reaction_cost_movement_or_second_accuracy(self):
        self.watch();event=self.waiting();rng=self.e.rng.getstate()
        before=(self.r.pos,self.r.hp,deepcopy(getattr(self.r,'budget',None)))
        self.choose(event,use=False)
        self.assertEqual((self.r.pos,self.r.hp,getattr(self.r,'budget',None)),before)
        self.assertEqual(self.e.rng.getstate(),rng)
        self.assertEqual(RESOURCES.pending(self.r),{})
        self.assertEqual(self.a._action_history,['standard'])

    def test_invalid_path_is_atomic_and_can_be_declined(self):
        self.watch();event=self.waiting()
        before=self.e.export_state()
        options=self.melee();options['path']=[(3,5),(3,2)]
        with self.assertRaises(ValueError):self.choose(event,options=options)
        self.assertEqual(self.e.export_state(),before)
        self.choose(event,use=False)
        self.assertIsNone(self.e._passive_pending)

    def test_ranged_endpoint_outside_attack_segment_rejects_before_roll_or_payment(self):
        self.t.pos=(6,2);self.r.pos=(4,4)
        self.watch('maneuver/원거리-가로채기');event=self.waiting('move/물대포')
        before=self.e.export_state()
        options=self.ranged();options['path']=[(4,4),(5,4),(5,3)]
        with self.assertRaises(ValueError):self.choose(event,options=options)
        self.assertEqual(self.e.export_state(),before)

    def test_pending_cold_restore_continues_without_repaying_or_rerolling(self):
        self.watch();event=self.waiting();rng=self.e.rng.getstate()
        hp=(self.t.hp,self.r.hp);self.fresh()
        self.choose(event,options=self.melee())
        self.assertEqual(self.t.hp,hp[0]);self.assertLess(self.r.hp,hp[1])
        self.assertEqual(self.e.rng.getstate(),rng)
        self.assertEqual(self.a.move_uses['move/막치기'],1)
        self.assertEqual(self.a._action_history,['standard'])
        before=self.e.export_state()
        with self.assertRaises(ValueError):self.choose(event,options=self.melee())
        self.assertEqual(self.e.export_state(),before)

    def test_dodge_actual_hit_becomes_miss_without_intercept_cost(self):
        G.replace_baseline(self.e,self.t,'abilities',['회피'])
        self.watch('ability/회피',self.t);event=self.waiting()
        hp=self.t.hp;pos=self.t.pos
        self.choose(event,reactor=self.t,options={})
        self.assertEqual((self.t.hp,self.t.pos),(hp,pos))
        self.assertEqual(RESOURCES.pending(self.t),{})
        self.assertFalse(self.completion()['results'][self.t.entity_id]['hit'])

    def test_miss_keeps_watch_and_never_creates_reaction(self):
        self.watch();watch=deepcopy(self.t.spec['move_defense_watch'])
        dealt=self.e.use_move(self.a,self.t,'move/막치기',situational=-100,set_damage=True)
        self.assertEqual(dealt,0);self.assertIsNone(self.e._passive_pending)
        self.assertEqual(self.t.spec['move_defense_watch'],watch)
        self.assertEqual(RESOURCES.pending(self.r),{})
        self.assertEqual(self.r.pos,(3,5))

    def test_interceptor_owns_received_reactive_ability_trigger(self):
        G.replace_baseline(self.e,self.r,'abilities',['변색'])
        self.r.spec['types']=['불꽃'];self.r._types=['불꽃']
        self.e.choose_reactive_ability(self.r,'ability/변색',reason='actual recipient chooses')
        self.watch();event=self.waiting();self.choose(event,options=self.melee())
        self.assertEqual(self.r.types,['노말'])
        self.assertEqual(self.t.types,[])

    def test_recipient_leaf_rejects_missing_or_forged_native_token(self):
        move=deepcopy(self.e.r.moves['move/막치기']);mm,conf=self.e.r.move_mech(move['id'])
        before=self.e.export_state()
        for token in (None,object(),{'intercepted':True}):
            with self.assertRaises(ValueError):
                self.e._resolve_move_recipient(self.a,self.r,move['id'],move,mm,conf,
                    True,12,False,True,None,None,ordinary_single=True,
                    completion_id=None,passive_event=None,defense_token=token)
            self.assertEqual(self.e.export_state(),before)

    def test_interceptor_knockout_reaches_actual_recipient_moxie_listener(self):
        G.replace_baseline(self.e,self.a,'abilities',['자기과신'])
        self.r.hp=1
        self.watch();event=self.waiting();target_hp=self.t.hp
        self.choose(event,options=self.melee())
        self.assertTrue(self.r.fainted)
        self.assertEqual(self.t.hp,target_hp)
        self.assertEqual(self.a.stages['atk'],1)
        children=[row for row in self.e._passive_events.values()
                  if row['id']!=event and row['target'] is self.r]
        self.assertEqual(len(children),1)
        self.assertTrue(children[0]['target_after']['fainted'])

    def test_immobilized_interceptor_rejects_before_cost_movement_or_rng(self):
        self.e.apply_status(self.r,'구속')
        self.watch();event=self.waiting();before=self.e.export_state()
        with self.assertRaises(ValueError):self.choose(event,options=self.melee())
        self.assertEqual(self.e.export_state(),before)
        self.choose(event,use=False)

    def test_never_miss_move_prohibits_intercept_attempt_before_cost(self):
        self.watch();event=self.waiting('move/스피드스타')
        before=self.e.export_state()
        with self.assertRaises(ValueError):self.choose(event,options=self.melee())
        self.assertEqual(self.e.export_state(),before)
        self.choose(event,use=False)

    def test_request_order_rejects_another_reactor_without_consuming_offer(self):
        G.replace_baseline(self.e,self.t,'abilities',['회피'])
        self.e.watch_move_defense(self.t,[
            {'actor_id':self.r.entity_id,'source':'maneuver/근접-가로채기'},
            {'actor_id':self.t.entity_id,'source':'ability/회피'}],
            reason='actual owners choose explicit reaction order')
        event=self.waiting();before=self.e.export_state()
        with self.assertRaises(ValueError):self.choose(event,reactor=self.t,options={})
        self.assertEqual(self.e.export_state(),before)
        with self.assertRaises(PASSIVE.PassiveEventPending):self.choose(event,use=False)
        hp=self.t.hp
        self.choose(event,reactor=self.t,options={})
        self.assertEqual(self.t.hp,hp)

    def test_ranged_intercept_rejects_actual_area_attack_before_roll_or_cost(self):
        self.t.pos=(6,2);self.r.pos=(4,4)
        self.watch('maneuver/원거리-가로채기')
        event=self.waiting('move/파도타기');before=self.e.export_state()
        with self.assertRaises(ValueError):self.choose(event,options=self.ranged())
        self.assertEqual(self.e.export_state(),before)

    def test_priority_intercept_requires_strictly_greater_actual_speed(self):
        self.r.stats['spe']=self.a.staged('spe')
        self.r.spec['stats']['spe']=self.r.stats['spe']
        self.watch();event=self.waiting('move/전광석화');before=self.e.export_state()
        with self.assertRaises(ValueError):self.choose(event,options=self.melee())
        self.assertEqual(self.e.export_state(),before)
        self.choose(event,use=False)

    def test_priority_intercept_succeeds_for_faster_actual_reactor(self):
        self.r.stats['spe']=self.a.staged('spe')+1
        self.r.spec['stats']['spe']=self.r.stats['spe']
        self.watch();event=self.waiting('move/전광석화');hp=self.t.hp
        self.choose(event,options=self.melee())
        self.assertEqual(self.t.hp,hp)
        self.assertEqual(self.r.pos,(3,2))

    def pokemon_reactor(self,loyalty,*,owner=None):
        old=self.r;old.pos=(15,15)
        self.r=Combatant(self.rules,build_pokemon(self.rules,'이상해씨',20,
            name='actual loyal interceptor',extra={'abilities':[],'pos':(3,5),
                'side':'party','size':'중형','trainer_id':(owner or self.t).entity_id,
                'loyalty':loyalty}))
        self.e.gm.add_combatant(self.r)
        return old

    def pokemon_melee(self):
        options=self.melee()
        count=self.e._prepare_skill_roll(self.r,'육상')[-1]['dice_count']
        options['roll_options']['fixed']=[6]*count
        return options

    def test_pokemon_loyalty_below_three_prohibits_own_trainer_intercept(self):
        self.pokemon_reactor(2)
        self.watch();event=self.waiting();before=self.e.export_state()
        with self.assertRaises(ValueError):self.choose(event,options=self.melee())
        self.assertEqual(self.e.export_state(),before)

    def test_pokemon_loyalty_three_permits_actual_own_trainer_only(self):
        self.pokemon_reactor(3)
        options=self.pokemon_melee();self.watch();event=self.waiting();hp=self.t.hp
        self.choose(event,options=options)
        self.assertEqual(self.t.hp,hp);self.assertEqual(self.r.pos,(3,2))

    def test_pokemon_loyalty_three_rejects_another_trainers_ally(self):
        self.pokemon_reactor(3,owner=self.r)
        self.watch();event=self.waiting();before=self.e.export_state()
        with self.assertRaises(ValueError):self.choose(event,options=self.melee())
        self.assertEqual(self.e.export_state(),before)

    def test_pokemon_loyalty_six_permits_pokemon_ally_intercept(self):
        owner=self.t;owner.pos=(15,14)
        self.t=Combatant(self.rules,build_pokemon(self.rules,'이상해씨',20,
            name='actual pokemon ally',extra={'abilities':[],'pos':(3,2),
                'side':'party','size':'중형'}))
        self.e.gm.add_combatant(self.t)
        self.pokemon_reactor(6,owner=owner)
        options=self.pokemon_melee();self.watch();event=self.waiting();hp=self.t.hp
        self.choose(event,options=options)
        self.assertEqual(self.t.hp,hp);self.assertEqual(self.r.pos,(3,2))

    def test_listed_conditions_prohibit_intercept_without_spending_or_rolling(self):
        for status in ('잠듦','혼란','난동','얼음','마비'):
            with self.subTest(status=status):
                self.setUp()
                self.e.apply_status(self.r,status)
                self.watch();event=self.waiting();before=self.e.export_state()
                with self.assertRaises(ValueError):self.choose(event,options=self.melee())
                self.assertEqual(self.e.export_state(),before)

    def test_area_push_keeps_ally_inside_and_hits_interceptor_once_with_later_alias(self):
        self.r.pos=(3,4)
        self.watch();event=self.waiting('move/지진',area=True)
        hp=(self.t.hp,self.r.hp)
        options=self.melee();options['path']=[(3,4),(3,3),(3,2)]
        self.choose(event,options=options)
        self.assertLess(self.t.hp,hp[0]);self.assertLess(self.r.hp,hp[1])
        row=self.completion()
        self.assertEqual(row['targets'],[self.t,self.r])
        self.assertEqual(set(row['received']),{self.t.entity_id,self.r.entity_id})
        self.assertEqual(row['results'][self.r.entity_id]['dealt'],0)
        self.assertEqual(self.a.move_uses['move/지진'],1)
        self.assertIsNone(self.e._passive_pending)

    def test_area_push_outside_saved_cone_routes_damage_and_stage_effect_to_interceptor(self):
        self.watch();event=self.waiting('move/바크아웃',area=True)
        hp=(self.t.hp,self.r.hp)
        options=self.melee();options['shove_destination']=[3,1]
        self.choose(event,options=options)
        self.assertEqual(self.t.hp,hp[0]);self.assertLess(self.r.hp,hp[1])
        self.assertEqual(self.t.stages['spa'],0);self.assertEqual(self.r.stages['spa'],-1)
        row=self.completion()
        self.assertEqual(row['targets'],[self.t])
        self.assertEqual(set(row['received']),{self.r.entity_id})
        self.assertEqual(row['phase'],'complete')

    def test_cold_area_wait_retains_target_order_and_resumes_duplicate_recipient_alias(self):
        self.r.pos=(3,4)
        self.watch();event=self.waiting('move/지진',area=True)
        ids=[actor.entity_id for actor in self.completion()['targets']]
        hp=(self.t.hp,self.r.hp);self.fresh()
        options=self.melee();options['path']=[(3,4),(3,3),(3,2)]
        self.choose(event,options=options)
        row=self.completion()
        self.assertEqual([actor.entity_id for actor in row['targets']],ids)
        self.assertLess(self.t.hp,hp[0]);self.assertLess(self.r.hp,hp[1])
        self.assertEqual(row['results'][self.r.entity_id]['dealt'],0)
        self.assertEqual(row['phase'],'complete')
        self.assertEqual(self.a.move_uses['move/지진'],1)
        self.assertEqual(self.a._action_history,['standard'])


if __name__=='__main__':unittest.main()
