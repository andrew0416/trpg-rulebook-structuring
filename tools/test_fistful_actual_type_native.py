"""R624's source-backed trainer producer and Fistful's separate transport repair.

The initial sheet records actual acquired sources. It uses the engine's supported
sheet_import contract; it does not certify category-6 acquisition or invent a
trainer's Judgment permission. hold_shard/fistful_of_force supply that permission.
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import math
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import attack_damage_history as HISTORY
import class_passive_combat as CLASS
import frequency as FREQ
import passive_events as PASSIVE
import researcher_fields as RFS
import state_grants as GRANTS
import world_entities as WORLD

MID='move/심판의뭉치'


class FistfulActualTypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='fantasy')

    def world(self,*,brand=True,fistful=True,target_types=('풀','강철'),spa=4,extra_target=False):
        self.assertEqual(self.rules._selected_rule(CLASS.BURNING_BRAND),CLASS.BURNING_BRAND)
        e=Engine(self.rules,seed=6242087);e.grid=Grid(18,14)
        feats=[RFS.CRYSTAL,'화염인도자']+([RFS.FISTFUL] if fistful else [])+([CLASS.BURNING_BRAND] if brand else [])
        trainer=Combatant(self.rules,{'name':'Acquired Researcher and Firebringer','kind':'trainer','level':30,
            'stats':{'hp':100,'atk':7,'def':15,'spa':spa,'spd':15,'spe':30},'types':[],
            'abilities':[],'classes':['class/연구원'],'feats':feats,
            'edges':['edge/보석-지식','edge/원소-교감'],
            'edge_choices':{'edge/원소-교감':['불꽃']},
            'feature_choices':{'class/연구원':[['artificer','general']]},
            'skills':{'오컬트학':6,'일반 지식':3,'전투':3,'집중':4,'육상':3,'곡예':3},
            'moves':['move/니트로차지','move/도깨비불'],'items':{},'shards':{'빨강':2},
            'movement':{'land':8,'swim':0,'sky':0,'power':4},'size':'중형','weight_kg':30})
        e.gm.add_combatant(trainer,pos=(1,1),side='party',reason='source-faithful supported initial acquired sheet')
        prepare_body(e,trainer,size='중형',offsets=[(0,0)],reason='observed complete trainer body')
        def target(name,pos,types,speed):
            species={('풀','강철'):'너트령',('물',):'꼬부기',('불꽃',):'파이리',('독',):'아보',('노말',):'꼬렛'}[tuple(types)]
            actor=Combatant(self.rules,build_pokemon(self.rules,species,60,name=name,
                moves=['move/몸통박치기'],abilities=[],side='foe'))
            self.assertEqual(actor.types,list(types))
            e.gm.add_combatant(actor,pos=pos,side='foe',reason='ordinary source-faithful target')
            prepare_body(e,actor,size=actor.spec.get('size') or '중형',offsets=[(0,0)],reason='observed complete target body')
            return actor
        foe=target('Original recipient',(6,1),target_types,20)
        other=target('Second area recipient',(7,1),('물',),19) if extra_target else None
        self.assertEqual(trainer._state_origin['kind'],'sheet_import')
        self.assertFalse(trainer._state_origin['creation_legality_certified'])
        self.assertNotIn(MID,trainer.moves)
        if fistful:self.assertEqual(RFS.qualify(e,trainer,RFS.FISTFUL)['move'],MID)
        self.assertEqual(CLASS.owns(trainer,CLASS.BURNING_BRAND),brand)
        e.begin_encounter(e.everyone);e.start_round(e.everyone);e.start_of_turn(trainer,initiative_count=30)
        e.enable_execution_trace()
        return e,trainer,foe,other

    def held(self,e,trainer):
        held=RFS.hold_shard(e,trainer,'빨강','주요손')
        self.assertEqual((held['color'],trainer.spec['shards']['빨강'],trainer.budget['swift']),('빨강',1,0))
        return held

    def cast(self,e,trainer,target,*,move_type='불꽃',face=19):
        with patch.object(Engine,'d20',return_value=face):
            return RFS.fistful_of_force(e,trainer,target,e.everyone,move_type=move_type,aim=target.pos,set_damage=True)

    def calculations(self,e):
        return [(row,calc) for row in e.execution_traces() if row['kind']=='damage_calculation'
                for calc in row['calculations'] if 'damage_type' in calc]

    def expected(self,e,target,actual,attack=18):
        mid=e.r.mech('combat/damage-chart')['by_damage_base']['10']['set']['mid']
        return math.floor(max(1,mid+attack-target.staged('spd'))*e.type_multiplier(actual,target)[0])

    def restored(self,e,*actors):
        ids=[a.entity_id for a in actors];new=Engine.import_state(e.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
        index=WORLD.actor_index(new);return (new,*(index[uid] for uid in ids))

    def assert_paid_once(self,e,trainer):
        self.assertEqual((trainer.spec['shards']['빨강'],trainer.budget['standard'],trainer.budget['swift']),(1,0,0))
        self.assertEqual(trainer.move_uses[MID],1)
        self.assertFalse(FREQ.activation_allowed(trainer,RFS.FISTFUL,RFS.DEFINITIONS[RFS.FISTFUL]['frequency'],engine=e))
        self.assertNotIn(MID,trainer.moves)
        self.assertIsNone(trainer.spec[RFS.KEY]['held_shard']);self.assertIsNone(trainer.spec[RFS.KEY]['fistful'])
        self.assertFalse(any(sid.startswith('researcher-fistful:') for sid in trainer.spec.get(GRANTS.KEY,{}).get('sources',{})))

    def test_core_profile_still_excludes_fantasy_burning_brand(self):
        from ruleset import ExcludedRuleSelection
        core=Rules(ROOT,ruleset="core")
        with self.assertRaisesRegex(ExcludedRuleSelection,"source:fantasy"):
            core._selected_rule(CLASS.BURNING_BRAND)

    def test_source_fistful_fire_18_19_and_absent_brand_use_actual_hit_and_native_costs(self):
        for face,brand,burns in ((18,True,False),(19,True,True),(19,False,False)):
            with self.subTest(face=face,brand=brand):
                e,trainer,target,_=self.world(brand=brand);self.held(e,trainer)
                printed=deepcopy(e.r.move(MID));before=target.hp
                expected=self.expected(e,target,'불꽃');out=self.cast(e,trainer,target,face=face)
                self.assertEqual((out['result'],before-target.hp),(expected,expected))
                self.assertEqual('화상' in target.conditions,burns)
                actual=self.calculations(e)
                self.assertEqual([(c['damage_type'],c['attack_value'],c['damage_base']) for _,c in actual],[('불꽃',18,10)])
                self.assertEqual(HISTORY.last_damage(target)['move_type'],'불꽃')
                self.assertEqual(e.r.move(MID),printed);self.assertEqual(printed['type'],'노말')
                self.assert_paid_once(e,trainer);self.assertTrue(e.validate_state()['valid'])

    def test_declared_shard_type_wins_over_judgment_automatic_best_type_on_other_matchups(self):
        for declared,types in (('불꽃',('불꽃',)),('에스퍼',('풀','강철')),('페어리',('독',))):
            with self.subTest(declared=declared,target=types):
                e,trainer,target,_=self.world(target_types=types);self.held(e,trainer)
                expected=self.expected(e,target,declared);out=self.cast(e,trainer,target,move_type=declared)
                self.assertEqual(out['result'],expected)
                self.assertEqual([c['damage_type'] for _,c in self.calculations(e)],[declared])
                self.assertEqual(HISTORY.last_damage(target)['move_type'],declared)
                self.assertNotIn('화상',target.conditions)
                self.assert_paid_once(e,trainer);self.assertTrue(e.validate_state()['valid'])

    def test_occult_substitution_is_actual_damage_and_independent_of_special_attack(self):
        damages=[]
        for spa in (4,60):
            e,trainer,target,_=self.world(spa=spa,target_types=('노말',));self.held(e,trainer)
            before=trainer.staged('spa');expected=self.expected(e,target,'불꽃')
            out=self.cast(e,trainer,target,face=18);damages.append(out['result'])
            self.assertEqual(out['result'],expected)
            self.assertEqual([c['attack_value'] for _,c in self.calculations(e)],[18])
            self.assertEqual(trainer.staged('spa'),before)
            self.assert_paid_once(e,trainer)
        self.assertEqual(damages[0],damages[1])

    def test_held_and_completed_gm_json_restores_keep_one_native_resource_use(self):
        e,trainer,target,_=self.world();self.held(e,trainer)
        e.gm.snapshot('held');e.gm.restore('held')
        e,trainer,target=self.restored(e,trainer,target)
        self.cast(e,trainer,target);self.assert_paid_once(e,trainer)
        after=(target.hp,deepcopy(trainer.move_uses),deepcopy(trainer.spec['shards']))
        e.gm.snapshot('completed');e.gm.restore('completed')
        e,trainer,target=self.restored(e,trainer,target)
        self.assertEqual((target.hp,trainer.move_uses,trainer.spec['shards']),after)
        self.assertEqual(HISTORY.last_damage(target)['move_type'],'불꽃')
        self.assertTrue(e.validate_state()['valid'])

    def defense(self,e,target):
        from builder import build_trainer
        reactor=Combatant(e.r,build_trainer(e.r,'Remaining area recipient',30,
            {'hp':100,'atk':10,'def':12,'spa':10,'spd':12,'spe':18},abilities=[],
            skills={'육상':3,'곡예':3},extra={'movement':{'land':8},'size':'중형'}))
        e.gm.add_combatant(reactor,pos=(6,2),side='foe',reason='actual same-side recipient inside the declared area')
        prepare_body(e,reactor,size='중형',offsets=[(0,0)],reason='observed actual defender body')
        e.gm.set_move(target,'move/판별',reason='actual learned Detect against the ranged area attack')
        e.watch_move_defense(target,[{'actor_id':target.entity_id,'source':'move/판별'}],reason='actual declared Detect defense')
        return reactor

    def test_real_defense_pending_and_remaining_area_recipient_keep_paid_original_choice_after_restore(self):
        for codec in ('gm','json'):
            with self.subTest(codec=codec):
                e,trainer,target,other=self.world(extra_target=True);reactor=self.defense(e,target);self.held(e,trainer)
                hp=(target.hp,other.hp,reactor.hp)
                with self.assertRaises(PASSIVE.PassiveEventPending):self.cast(e,trainer,target)
                event=e._passive_pending;self.assertIsNotNone(event)
                self.assertEqual((target.hp,other.hp,reactor.hp),hp)
                self.assert_paid_once(e,trainer)
                # Already-paid damage must retain its rank-6 declaration.
                e.gm.set_skill(trainer,'오컬트학',5,reason='actual skill observation after the paid activation')
                if codec=='gm':e.gm.snapshot('waiting');e.gm.restore('waiting')
                else:e,trainer,target,other,reactor=self.restored(e,trainer,target,other,reactor)
                e.enable_execution_trace()
                e.choose_move_defense(event,target,use=True,reason='actual first recipient uses its paid Detect')
                self.assertEqual(target.move_uses['move/판별'],1)
                self.assertIsNone(target.shield)
                self.assertEqual(target.hp,hp[0]);self.assertLess(other.hp,hp[1]);self.assertLess(reactor.hp,hp[2])
                facts=self.calculations(e)
                self.assertEqual(len(facts),2)
                self.assertEqual({row['inputs']['target']['entity_id'] for row,_ in facts},{other.entity_id,reactor.entity_id})
                self.assertTrue(all(c['damage_type']=='불꽃' and c['attack_value']==18 for _,c in facts))
                self.assertEqual(HISTORY.last_damage(other)['move_type'],'불꽃')
                self.assertEqual(HISTORY.last_damage(reactor)['move_type'],'불꽃')
                self.assert_paid_once(e,trainer);self.assertTrue(e.validate_state()['valid'])
                self.assertTrue(self.restored(e,trainer,target,other,reactor)[0].validate_state()['valid'])

    def test_fistful_input_rejections_and_late_ordinary_failure_do_not_pay_or_leak_permission(self):
        for case in ('feature','held','type','rank','late_damage'):
            with self.subTest(case=case):
                e,trainer,target,_=self.world(fistful=case!='feature')
                if case!='held':self.held(e,trainer)
                if case=='rank':e.gm.set_skill(trainer,'오컬트학',5,reason='actual insufficient current rank')
                declared='물' if case=='type' else '불꽃'
                operation=lambda:self.cast(e,trainer,target,move_type=declared)
                if case=='late_damage':
                    original=Engine._take_damage
                    def fail(engine,actor,amount):
                        original(engine,actor,amount);raise ValueError('late actual Fistful damage failure')
                    with patch.object(Engine,'_take_damage',fail):
                        assert_rejected_unchanged(e,operation,reason_pattern='late actual Fistful damage failure')
                else:
                    assert_rejected_unchanged(e,operation,reason_pattern={'feature':'acquired Researcher feature','held':'requires a shard','type':'held shard colour','rank':'printed skill rank'}[case])
                self.assertNotIn(MID,trainer.moves)
                self.assertFalse(any(sid.startswith('researcher-fistful:') for sid in trainer.spec.get(GRANTS.KEY,{}).get('sources',{})))

    def test_fistful_scene_and_judgment_daily_limits_are_still_distinct(self):
        e,trainer,target,_=self.world();self.held(e,trainer);self.cast(e,trainer,target)
        e.end_of_turn(trainer);e.start_round(e.everyone);e.start_of_turn(trainer,initiative_count=30)
        RFS.hold_shard(e,trainer,'빨강','반대손')
        assert_rejected_unchanged(e,lambda:self.cast(e,trainer,target),reason_pattern='already used this scene')
        e.end_of_turn(trainer);e.end_scene(e.everyone,round_elapsed_seconds=0)
        e.begin_encounter(e.everyone);e.start_round(e.everyone);e.start_of_turn(trainer,initiative_count=30)
        assert_rejected_unchanged(e,lambda:self.cast(e,trainer,target),reason_pattern='Judgement frequency refuses')
        self.assertEqual(trainer.spec[RFS.KEY]['held_shard']['hand'],'반대손')
        self.assertNotIn(MID,trainer.moves)

    def test_pending_native_marker_tamper_is_rejected_without_retyping_or_second_payment(self):
        e,trainer,target,other=self.world(extra_target=True);self.defense(e,target);self.held(e,trainer)
        with self.assertRaises(PASSIVE.PassiveEventPending):self.cast(e,trainer,target)
        event=e._passive_events[e._passive_pending]
        args=event['continuation']['args']
        self.assertEqual(args['move']['_researcher_fistful']['attack_value'],18)
        args['move']['_researcher_fistful']['type']='물'
        self.assertFalse(e.validate_state()['valid'])
        with self.assertRaises(ValueError):e.export_state()


    def test_fabricated_pending_exception_is_not_a_committed_native_prefix(self):
        import heavy_injury_adapter as HEAVY
        for kind in (PASSIVE.PassiveEventPending,HEAVY.HeavyPending):
            with self.subTest(exception=kind.__name__):
                e,trainer,target,_=self.world();self.held(e,trainer);before=e.export_state()
                with patch.object(Engine,'use_move_on',side_effect=kind('unissued-event')):
                    with self.assertRaises(kind):self.cast(e,trainer,target)
                self.assertEqual(e.export_state(),before)
                self.assertIsNotNone(trainer.spec[RFS.KEY]['held_shard'])
                self.assertNotIn(MID,trainer.moves)


if __name__=='__main__':unittest.main()
