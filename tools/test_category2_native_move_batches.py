"""Actual activation, damage, type consumers and persistence across Move families."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
STAGE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(STAGE/'engine'), str(ROOT/'engine')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon
from grid import Grid
import attack_damage_history as HISTORY
import five_strike as FIVE
import move_type_choices as TYPES
import optional_move_modes as OPTIONAL


class NativeMoveBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.r = Rules(str(ROOT), ruleset='core')

    def setUp(self):
        self.e = Engine(self.r, seed=6021)
        self.e.grid = Grid(30, 30)
        self.p = Combatant(self.r, build_pokemon(self.r, '이상해씨', 40,
            moves=getattr(self,'initial_moves',['move/텍스처','move/텍스처2','move/독침천발','move/메탈버스트','move/몸통박치기']),
            abilities=getattr(self,'initial_abilities',['심록'])))
        self.p.pos = (10,10)
        self.e.gm.add_combatant(self.p)
        self.t = Combatant(self.r, build_pokemon(self.r, '꼬부기', 40,
            moves=['move/몸통박치기','move/물대포'], abilities=getattr(self,'initial_target_abilities',['급류']),side='wild'))
        self.t.pos = (11,10)
        self.e.gm.add_combatant(self.t)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.p, initiative_count=20)
        self.e.d20 = lambda: 17

    def turn(self, actor, new_round=False):
        active = self.e._active_turn_actor
        if active is not None: self.e.end_of_turn(active)
        if new_round: self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor, initiative_count=20)

    def restore(self):
        self.e.__dict__.pop('d20',None)
        return Engine.import_state(self.r, json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))

    def test_conversion_requires_current_known_move_and_restores_original_types(self):
        before = deepcopy((self.p.spec,self.p.budget,self.e.rng.getstate()))
        with self.assertRaises(ValueError): self.e.use_move(self.p,self.p,'move/텍스처')
        self.assertEqual(before,(self.p.spec,self.p.budget,self.e.rng.getstate()))
        with self.assertRaises(ValueError):
            self.e.gm.choose_move_type(self.p,'move/텍스처','불꽃',known_move='move/물대포',reason='player')
        self.e.gm.choose_move_type(self.p,'move/텍스처','노말',known_move='move/몸통박치기',reason='player')
        self.e.use_move(self.p,self.p,'move/텍스처')
        self.assertEqual(self.p.types,['노말'])
        self.assertEqual(self.e.type_multiplier('격투',self.p)[0],1.5)
        self.assertEqual(self.p.budget['standard'],0)
        restored=self.restore();p=next(x for x in restored.everyone if x.entity_id==self.p.entity_id)
        self.assertEqual(p.types,['노말'])
        restored.end_of_turn(p);restored.end_encounter()
        self.assertEqual(p.types,['풀','독'])

    def test_conversion_two_uses_actual_latest_damage_and_rejects_stale_choice(self):
        with self.assertRaises(ValueError): self.e.gm.choose_move_type(self.p,'move/텍스처2','바위',reason='player')
        self.turn(self.t)
        self.e.use_move(self.t,self.p,'move/몸통박치기',set_damage=True)
        last=HISTORY.last_damage(self.p)
        self.assertEqual(last['move_type'],'노말')
        self.e.gm.choose_move_type(self.p,'move/텍스처2','바위',reason='player')
        self.turn(self.p,new_round=True)
        self.e.use_move(self.p,self.p,'move/텍스처2')
        self.assertEqual(self.p.types,['바위'])
        self.assertEqual(TYPES.records(self.p)[0]['basis'],{'damage_sequence':last['sequence']})
        self.assertTrue(self.restore().validate_state()['valid'])

    def test_conversion_choice_changes_fail_before_cost(self):
        self.e.gm.choose_move_type(self.p,'move/텍스처','노말',known_move='move/몸통박치기',reason='player')
        self.p.moves.remove('move/몸통박치기')
        before=deepcopy((self.p.budget,TYPES.records(self.p),self.e.rng.getstate()))
        with self.assertRaises(ValueError): self.e.use_move(self.p,self.p,'move/텍스처')
        self.assertEqual(before,(self.p.budget,TYPES.records(self.p),self.e.rng.getstate()))

    def test_conversion_two_stale_observation_can_be_reselected_without_consuming_action(self):
        self.turn(self.t)
        self.e.use_move(self.t,self.p,'move/몸통박치기',set_damage=True)
        self.e.gm.choose_move_type(self.p,'move/텍스처2','바위',reason='first choice')
        self.turn(self.t,new_round=True)
        self.e.use_move(self.t,self.p,'move/물대포',set_damage=True)
        self.turn(self.p)
        before=deepcopy((self.p.budget,self.p.move_uses,self.e.rng.getstate()))
        with self.assertRaises(ValueError): self.e.use_move(self.p,self.p,'move/텍스처2')
        self.assertEqual(before,(self.p.budget,self.p.move_uses,self.e.rng.getstate()))
        self.e.gm.choose_move_type(self.p,'move/텍스처2','풀',reason='updated actual last damage')
        self.e.use_move(self.p,self.p,'move/텍스처2')
        self.assertEqual(self.p.types,['풀'])
        self.assertIsNotNone(TYPES.records(self.p)[0]['cancelled_at'])
        self.assertEqual(TYPES.records(self.p)[1]['basis'],{'damage_sequence':2})
        self.assertTrue(self.restore().validate_state()['valid'])

    def test_conversion_reads_actual_individual_move_type_sync(self):
        self.e.gm.observe_move_type_sync(self.p,application_id='fire-tackle',move_id='move/몸통박치기',
            chosen_type='불꽃',new_name='화염박치기',
            effect_decision={'mode':'preserve','reason':'no extra effect','effects_exec':None},
            feasibility_review='same range and class',power_review='no extra damage',reason='actual GM observation')
        self.e.gm.choose_move_type(self.p,'move/텍스처','불꽃',known_move='move/몸통박치기',reason='synced Move')
        self.e.use_move(self.p,self.p,'move/텍스처')
        self.assertEqual(self.p.types,['불꽃'])
        self.assertTrue(self.restore().validate_state()['valid'])

    def test_five_strike_shared_keyword_consumers_and_technician_after_combining(self):
        names=('바늘미사일','손바닥치기','씨기관총','본러시','고드름침','구슬던지기',
               '연속펀치','연속뺨치기','마구찌르기','마구할퀴기','가시대포','스위프뺨치기')
        for name in names:
            with self.subTest(move=name):
                mid='move/'+name
                self.initial_moves=[mid];self.initial_abilities=['테크니션'];self.setUp()
                move=self.r.move(mid);observed=[];original=self.e.roll_damage
                def capture(a,t,m,*args,**kwargs):
                    observed.append(self.e.damage_base(a,m,target=t))
                    return original(a,t,m,*args,**kwargs)
                with patch.object(self.e,'roll_expr',return_value=(8,[8])),patch.object(self.e,'roll_damage',side_effect=capture):
                    self.e.use_move(self.p,self.t,mid,set_damage=True)
                stab=2 if move['type'] in self.p.types else 0
                self.assertEqual(observed,[move['damage_base']*5+2+stab])
                self.assertEqual(len(HISTORY.records(self.t)),1)
                self.assertEqual(self.p.budget['standard'],0)

    def test_metal_burst_consumes_only_current_round_direct_damage_for_actual_area(self):
        self.turn(self.t,new_round=True)
        self.e.use_move(self.t,self.p,'move/몸통박치기',set_damage=True)
        amount=HISTORY.current_round(self.e,self.p)
        self.assertGreater(amount,0)
        self.e.lose_hp(self.p,3,source='poison-like non-attack loss')
        self.assertEqual(HISTORY.current_round(self.e,self.p),amount)
        self.turn(self.p)
        before=self.t.hp
        self.e.use_move_on(self.p,self.t,'move/메탈버스트',self.e.everyone)
        self.assertEqual(before-self.t.hp,amount)
        self.assertEqual(HISTORY.records(self.t),[])
        self.assertEqual(self.e.effect_stats['held'],0)
        self.assertTrue(self.restore().validate_state()['valid'])
        self.turn(self.t,new_round=True)
        self.assertEqual(HISTORY.current_round(self.e,self.p),0)

    def test_history_rejects_forged_native_producer_and_saved_amount(self):
        self.turn(self.t)
        self.e.use_move(self.t,self.p,'move/몸통박치기',set_damage=True)
        record=HISTORY.records(self.p)[0]
        with self.assertRaises(ValueError):
            HISTORY.record(self.e,self.t,self.p,self.r.move('move/몸통박치기'),record['receipt'],'노말',object())
        record['receipt']['net_hp_loss']+=1
        with self.assertRaises(ValueError): self.e.export_state()

    def test_five_strike_all_faces_multiply_before_stab_and_one_attack(self):
        for face,hit_count in enumerate((1,2,2,3,3,3,4,5),1):
            with self.subTest(face=face):
                self.setUp();observed=[]
                original=self.e.roll_damage
                def capture(a,t,m,*args,**kwargs):
                    observed.append(self.e.damage_base(a,m,target=t))
                    return original(a,t,m,*args,**kwargs)
                with patch.object(self.e,'roll_expr',return_value=(face,[face])),patch.object(self.e,'roll_damage',side_effect=capture):
                    self.e.use_move(self.p,self.t,'move/독침천발',set_damage=True)
                self.assertEqual(observed,[2*hit_count+2])
                self.assertEqual(self.p.spec[FIVE.KEY][0]['hits'],hit_count)
                self.assertEqual(len(HISTORY.records(self.t)),1)
                self.assertIn('독',self.t.conditions)

    def test_optional_five_strike_fixed_eight_and_normal_miss_consumption(self):
        self.e.apply_status(self.t,'마비',source='move/전기자석파',applied_by=self.p)
        self.e.gm.choose_optional_move_effect(self.p,'move/독침천발',reason='player')
        with patch.object(self.e,'roll_expr',side_effect=AssertionError('fixed mode must not roll d8')):
            self.e.use_move(self.p,self.t,'move/독침천발',set_damage=True)
        self.assertEqual(self.p.spec[FIVE.KEY][0]['face'],8)
        self.assertIsNotNone(OPTIONAL.history(self.p)[0]['use'])
        self.assertTrue(self.restore().validate_state()['valid'])
        self.setUp();self.e.d20=lambda:1
        with patch.object(self.e,'roll_expr',return_value=(7,[7])):
            self.e.use_move(self.p,self.t,'move/독침천발',set_damage=True)
        self.assertEqual(self.p.spec[FIVE.KEY][0]['hits'],4)
        self.assertEqual(HISTORY.records(self.t),[])

    def test_five_strike_optional_requires_prior_affliction_and_native_roll(self):
        self.e.gm.choose_optional_move_effect(self.p,'move/독침천발',reason='player')
        before=deepcopy((self.p.budget,self.e.rng.getstate(),OPTIONAL.history(self.p)))
        with self.assertRaises(ValueError): self.e.use_move(self.p,self.t,'move/독침천발',set_damage=True)
        self.assertEqual(before,(self.p.budget,self.e.rng.getstate(),OPTIONAL.history(self.p)))
        with self.assertRaises(ValueError): self.e.damage_base(self.p,self.r.move('move/독침천발'),target=self.t)

    def test_keyword_and_retrospective_source_guards_precede_cost(self):
        import retrospective_moves as RETRO
        for module,mid in ((FIVE,'move/독침천발'),(RETRO,'move/메탈버스트')):
            with self.subTest(move=mid):
                before=deepcopy((self.p.spec,self.p.budget,self.p.move_uses,self.e.rng.getstate()))
                with patch.dict(module.SOURCE_REF,sha256='0'*64):
                    with self.assertRaises(ValueError):self.e.use_move(self.p,self.t,mid,set_damage=True)
                self.assertEqual(before,(self.p.spec,self.p.budget,self.p.move_uses,self.e.rng.getstate()))
        self.e.use_move_on(self.p,self.t,'move/메탈버스트',self.e.everyone)
        self.assertEqual(self.p.budget['standard'],0)


if __name__ == '__main__': unittest.main()
