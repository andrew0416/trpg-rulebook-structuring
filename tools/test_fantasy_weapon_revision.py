"""Actual crafted equipment consumers; all cases await the final Actions run."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE if (STAGE / 'data/core-rules.json').exists() else Path(os.environ.get(
    'PTK_CANONICAL_ROOT', r'D:/trpg-rulebook-structuring/work/public-actions-20261023/repository'))
sys.path[:0] = [str(STAGE / 'engine'), str(ROOT / 'engine'), str(ROOT / 'tools')]
from builder import build_trainer, build_pokemon
from engine import Combatant, Engine, Rules
from grid import Grid
import attack_damage_history as HISTORY
import body_state as BODY
import combat_precision_features as PRECISION
import effects_ext as EXT
import event_trace as TRACE
import frequency as FREQ
import items as ITEMS
import optional_physical_equipment as CRAFTED
import optional_weapon_framework as FRAMEWORK
import passive_events as PASSIVE
import state_grants as GRANTS
import move_activation as ACTIVATION
import weapon_actions as WEAPONS
import world_entities as WORLD


class FantasyWeaponRevisionTests(unittest.TestCase):
    def fixture(self, *, rank=4, occult=4, element='노말', count=3):
        r = Rules(str(ROOT), ruleset='all')
        if max(rank, occult) > 6:
            from examples.declared_skill_ranks import configure
            configure(r)
        e = Engine(r, seed=94552); e.grid = Grid(20, 15)
        a = Combatant(r, build_trainer(r, 'fantasy owner', 30,
            {'hp':100, 'atk':35, 'def':15, 'spa':35, 'spd':15, 'spe':20},
            moves=['move/몸통박치기'], abilities=[], extra={
                'feats':[FRAMEWORK.TRAINING], 'edges':['edge/원소-교감'],
                'edge_choices':{'edge/원소-교감':element},
                'skills':{'전투':rank, '오컬트학':occult, '집중':3},
                'movement':{'land':6}, 'movement_basis':'current'}))
        e.gm.add_combatant(a, side='owner', pos=(2,2), reason='actual wielder')
        BODY.observe(e,a,[(0,0)],reason='observed body')
        targets=[]
        for n in range(count):
            t = Combatant(r, build_pokemon(r, '피카츄', 50, name='fantasy target '+str(n),
                wild=True, moves=['move/몸통박치기'], abilities=[],
                extra={'movement':{'land':6},'movement_basis':'current'}))
            e.gm.add_combatant(t,side='foe',pos=(3+n%3,2+n//3),reason='actual independent target')
            e.gm.set_types(t,['노말'],reason='observed target typing')
            BODY.observe(e,t,[(0,0)],reason='observed body')
            targets.append(t)
        TRACE.enable(e)
        return e,a,targets

    def equip(self,e,a,item,*,profile=None):
        uid='fantasy/'+str(len(getattr(e,'_physical_objects',{})))+item
        WORLD.register_object(e,uid,kind='item_instance',item_rule_id=item,
            owner_id=a.entity_id,location={'kind':'unknown'},reason='actual physical source')
        if profile:
            row=CRAFTED.definition(e.r,item)
            FRAMEWORK.observe_weapon(e,a,uid,name=row['name'],kind=row['weapon_kind'],
                grade=profile.get('grade',row.get('weapon_grade','좋음')),
                arcane=bool(row.get('arcane')),metal=False,moves=profile.get('moves',()),
                reason='actual ordinary base weapon grants')
        ITEMS.register_item(e,a,item,source_instance_id=uid,as_held=a.kind=='pokemon')
        return uid

    def entry(self,a,uid):
        return next(row for row in a.custom_conditions['equipped_weapons'].values() if row['instance_id']==uid)

    def begin(self,e,a):
        if e._active_turn_actor is not None:e.end_of_turn(e._active_turn_actor)
        e.start_round(e.everyone); e.start_of_turn(a,initiative_count=20)

    def restore(self,e,*actors):
        ids=[a.entity_id for a in actors]
        restored=Engine.import_state(e.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
        index=WORLD.actor_index(restored)
        return restored,*(index[uid] for uid in ids)

    def facts(self,e,move):
        return [c for row in TRACE.records(e) for c in row['calculations']
                if c.get('source')==move and 'after_defense' in c]

    def assert_transition_context_cleared(self,e):
        self.assertEqual(GRANTS._TRANSITION_MOVE_ALIASES.get(),())
        self.assertNotIn('_transition_move_aliases',vars(e))
        self.assertNotIn('transition_move_aliases',json.dumps(e.export_state(),ensure_ascii=False))

    def test_native_group_staging_rejects_equal_external_dicts_and_cleans_errors(self):
        e,a,targets=self.fixture(count=1)
        uid=self.equip(e,a,'crafted_item/스프레드-니들');target=targets[0]
        self.begin(e,a)
        before=deepcopy((a.move_uses,a.budget,e.rng.getstate(),target.hp))
        with ACTIVATION.open_scope(e,a,'move/구슬던지기',(target,),shared=True,
                primary=target,options={'weapon_id':uid,'set_damage':True}) as (activation,accuracy):
            for use_activation,use_accuracy in ((dict(activation),accuracy),(activation,dict(accuracy))):
                self.assertEqual(use_activation,activation)
                self.assertEqual(use_accuracy,accuracy)
                with self.assertRaisesRegex(ValueError,'actual native producer authority'):
                    e.use_move(a,target,'move/구슬던지기',weapon_id=uid,set_damage=True,
                        _activation=use_activation,_shared_accuracy=use_accuracy)
                self.assertEqual((a.move_uses,a.budget,e.rng.getstate(),target.hp),before)
                self.assertEqual(GRANTS._TRANSITION_MOVE_ALIASES.get(),())
                self.assertEqual(e._move_activation_scopes[-1]['index'],0)
            # A real graph that fails after permission/payment must also roll back
            # and leave the same producer group usable for the next real attempt.
            with patch.object(Engine,'_continue_move_after_payment',side_effect=RuntimeError('staged suffix probe')):
                with self.assertRaisesRegex(RuntimeError,'staged suffix probe'):
                    e.use_move(a,target,'move/구슬던지기',weapon_id=uid,set_damage=True,
                        _activation=activation,_shared_accuracy=accuracy)
            self.assertEqual((a.move_uses,a.budget,e.rng.getstate(),target.hp),before)
            self.assertEqual(GRANTS._TRANSITION_MOVE_ALIASES.get(),())
            self.assertEqual(e._move_activation_scopes[-1]['index'],0)
            with patch.object(Engine,'d20',return_value=17):
                dealt=e.use_move(a,target,'move/구슬던지기',weapon_id=uid,set_damage=True,
                    _activation=activation,_shared_accuracy=accuracy)
            ACTIVATION.note_result(e,activation,dealt)
            self.assertGreater(dealt,0)
            self.assertEqual(a.move_uses['move/구슬던지기'],1)
            self.assertEqual(e._move_activation_scopes[-1]['index'],1)
            self.assertIs(e._move_activation_scopes[-1]['activation'],activation)
            self.assertIs(e._move_activation_scopes[-1]['accuracy'],accuracy)
        self.assert_transition_context_cleared(e)
        self.assertTrue(self.restore(e,a,target)[0].validate_state()['valid'])

    def test_all_crafted_struggles_add_size_once_and_large_grants_add_ac(self):
        cases=[('crafted_item/스톰-글러브',5),('crafted_item/캔디-해머',6),
               ('crafted_item/뇌수-창',6),('crafted_item/엑스칼리버',5),
               ('crafted_item/여의금고봉',6),('crafted_item/카오스-던커',6)]
        for item,expected in cases:
            with self.subTest(item=item):
                e,a,targets=self.fixture();uid=self.equip(e,a,item);entry=self.entry(a,uid)
                move=WEAPONS.prepare(e,a,e.r.move(entry['struggle_id']),uid)
                self.assertEqual(e.damage_base(a,move),expected)
                self.assertEqual(move['_weapon_attack']['db_bonus'],0)
                if item=='crafted_item/뇌수-창':
                    native=e.r.move('move/번개엄니');prepared=WEAPONS.prepare(e,a,native,uid)
                    self.assertEqual(prepared['ac'],native['ac']+1)
                    self.assertEqual(e.damage_base(a,prepared),native['damage_base']+2)

    def test_crafted_ranges_keep_native_shapes_and_printed_numeric_distance(self):
        for item,mid,shape in [('crafted_item/카오스-던커','move/지진','burst'),
                               ('crafted_item/나인플레임의-스태프','move/불꽃튀기기',None)]:
            e,a,targets=self.fixture();uid=self.equip(e,a,item)
            prepared=WEAPONS.prepare(e,a,e.r.move(mid),uid)
            source=e.r.moves_mech[mid]['header']['range']
            actual=WEAPONS.range_spec(e,prepared,a)
            self.assertEqual(actual.get('shape'),shape)
            self.assertEqual(actual.get('origin'),source.get('origin'))
            self.assertEqual(actual.get('size'),source.get('size'))
            self.begin(e,a)
            with patch.object(Engine,'d20',return_value=17):
                damage=e.use_move_on(a,targets[0],mid,e.everyone,weapon_id=uid,
                    aim=a.pos if shape else None,set_damage=True)
            self.assertGreater(damage,0)

    def test_spread_needle_roll_maps_to_max_distinct_targets_and_one_activation(self):
        e,a,targets=self.fixture(count=6);uid=self.equip(e,a,'crafted_item/스프레드-니들')
        self.begin(e,a)
        for face,count in ((3,3),(8,6)):
            before=deepcopy((a.move_uses,a.budget,e.rng.getstate(),[t.hp for t in targets]))
            with self.assertRaisesRegex(ValueError,'Five Strike hit count'):
                CRAFTED.activate_spread_needle(e,a,targets[:count],fixed_strikes=face)
            self.assertEqual((a.move_uses,a.budget,e.rng.getstate(),[t.hp for t in targets]),before)
        with patch.object(Engine,'d20',return_value=17):
            result=CRAFTED.activate_spread_needle(e,a,targets[:5],fixed_strikes=8,set_damage=True)
        self.assertEqual((result['hits'],a.move_uses['move/구슬던지기'],a.budget['standard']),(5,1,0))
        self.assertTrue(all(HISTORY.last_damage(t) is not None for t in targets[:5]))
        self.assertIsNone(HISTORY.last_damage(targets[5]))
        self.assertEqual(a.spec.get('five_strike_history',[]),[])
        prepared=WEAPONS.prepare(e,a,e.r.move('move/구슬던지기'),uid)
        self.assertNotIn('오단타격',EXT.keywords_for(a,prepared))
        self.assertEqual(WEAPONS.range_spec(e,prepared,a)['origin'],4)
        self.assertEqual(len(self.facts(e,'move/구슬던지기')),5)
        self.assertEqual({c['damage_base'] for c in self.facts(e,'move/구슬던지기')},{2})

    def test_ordinary_spread_barrage_uses_db_two_and_rolls_before_accuracy(self):
        for face in (1,8):
            e,a,targets=self.fixture();uid=self.equip(e,a,'crafted_item/스프레드-니들')
            self.begin(e,a);order=[]
            def die(rng,sides=6,**kw):
                self.assertEqual(sides,8);order.append('strikes');return face
            def accuracy(engine):order.append('accuracy');return 17
            with patch.object(CRAFTED.POOLS,'die',side_effect=die),patch.object(Engine,'d20',accuracy):
                damage=e.use_move(a,targets[0],'move/구슬던지기',weapon_id=uid,set_damage=True)
            self.assertGreater(damage,0);self.assertEqual(order[:2],['strikes','accuracy'])
            self.assertEqual(self.facts(e,'move/구슬던지기')[-1]['damage_base'],2)
            self.assertFalse(a.spec.get('five_strike_history'))

    def test_spread_defense_wait_restores_remaining_targets_without_reroll_or_repayment(self):
        e,a,targets=self.fixture();uid=self.equip(e,a,'crafted_item/스프레드-니들')
        first,last=targets[:2]
        e.gm.set_move(first,'move/판별',reason='actual learned Detect')
        e.watch_move_defense(first,[{'actor_id':first.entity_id,'source':'move/판별'}],reason='actual declared defense')
        self.begin(e,a);hp=[t.hp for t in (first,last)]
        with patch.object(Engine,'d20',return_value=17):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                CRAFTED.activate_spread_needle(e,a,(first,last),fixed_strikes=2,set_damage=True)
        event=e._passive_pending
        self.assert_transition_context_cleared(e)
        self.assertEqual(a.move_uses['move/구슬던지기'],1)
        e,a,first,last=self.restore(e,a,first,last)
        with patch.object(CRAFTED.POOLS,'die',side_effect=AssertionError('no second d8')),\
             patch.object(Engine,'d20',return_value=17):
            e.choose_move_defense(event,first,use=True,reason='actual Detect')
        self.assertEqual(first.hp,hp[0]);self.assertLess(last.hp,hp[1])
        self.assertEqual((a.move_uses['move/구슬던지기'],a.budget['standard']),(1,0))
        self.assertTrue(e.validate_state()['valid'])
        self.assert_transition_context_cleared(e)

    def test_ruyi_struggle_miss_deals_smite_and_records_actual_damage(self):
        e,a,targets=self.fixture();uid=self.equip(e,a,'crafted_item/여의금고봉');mid=self.entry(a,uid)['struggle_id']
        target=targets[0];self.begin(e,a);hp=target.hp
        with patch.object(Engine,'d20',return_value=1):
            result=CRAFTED.activate_ruyi_smite(e,a,target,mid,e.everyone,mode='burst',size=1,set_damage=True)
        self.assertTrue(result['activated']);self.assertLess(target.hp,hp)
        self.assertEqual(HISTORY.amount(HISTORY.last_damage(target)),hp-target.hp)
        row=next(row for row in reversed(list(e._move_completions.values())) if row['actor'] is a and row['move_id']==mid)
        self.assertFalse(row['results'][target.entity_id]['hit'])
        self.assertGreater(row['results'][target.entity_id]['dealt'],0)
        self.assertEqual(FREQ.state(a)['activations']['optional-equipment:ruyi-smite:'+uid]['used'],1)
        e,a,target=self.restore(e,a,target)
        self.assertIsNotNone(HISTORY.last_damage(target));self.assertTrue(e.validate_state()['valid'])

    def test_ruyi_wait_preserves_smite_on_later_miss_and_charges_scene_once(self):
        e,a,targets=self.fixture();uid=self.equip(e,a,'crafted_item/여의금고봉');mid=self.entry(a,uid)['struggle_id']
        first,last=targets[:2]
        e.gm.set_move(first,'move/판별',reason='actual learned Detect')
        e.watch_move_defense(first,[{'actor_id':first.entity_id,'source':'move/판별'}],reason='actual declared defense')
        e.gm.set_stat(first,'def',value=10,reason='actual first recipient defense')
        e.gm.set_stat(first,'spe',value=10,reason='actual first recipient speed')
        e.gm.set_stat(last,'spe',value=100,reason='actual later recipient speed evasion')
        self.begin(e,a);hp=(first.hp,last.hp)
        with patch.object(Engine,'d20',return_value=8):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                CRAFTED.activate_ruyi_smite(e,a,first,mid,e.everyone,mode='burst',size=3,set_damage=True)
        event=e._passive_pending;key='optional-equipment:ruyi-smite:'+uid
        self.assert_transition_context_cleared(e)
        self.assertEqual(FREQ.state(a)['activations'][key]['used'],1)
        e,a,first,last=self.restore(e,a,first,last)
        with patch.object(Engine,'d20',return_value=8):
            e.choose_move_defense(event,first,use=True,reason='actual first recipient prevents attack')
        self.assertEqual(first.hp,hp[0]);self.assertLess(last.hp,hp[1])
        row=next(row for row in reversed(list(e._move_completions.values())) if row['actor'] is a and row['move_id']==mid)
        self.assertFalse(row['results'][last.entity_id]['hit'])
        self.assertGreater(row['results'][last.entity_id]['dealt'],0)
        self.assertEqual(FREQ.state(a)['activations'][key]['used'],1)
        self.assertEqual(a.move_uses[mid],1);self.assertTrue(e.validate_state()['valid'])
        self.assert_transition_context_cleared(e)

    def test_storm_glove_simple_grade_preserves_one_base_grant_at_rank_seven(self):
        e,a,targets=self.fixture(rank=7)
        uid=self.equip(e,a,'crafted_item/스톰-글러브',profile={'moves':['move/꿰뚫기']})
        entry=self.entry(a,uid)
        self.assertEqual(entry['weapon']['grade'],'간단')
        self.assertIn('move/아쿠아제트',entry['available_moves'])
        self.assertEqual(a.spec['skills']['전투'],7)
        e,a,*_=self.restore(e,a)
        self.assertEqual(self.entry(a,uid)['weapon']['grade'],'간단')
        e2,a2,_=self.fixture(rank=7)
        with self.assertRaisesRegex(ValueError,'catalogue identity'):
            self.equip(e2,a2,'crafted_item/스톰-글러브',profile={'grade':'좋음'})

    def test_songbird_light_armor_reduces_native_damage_then_revokes(self):
        e,a,targets=self.fixture();foe=targets[0]
        baseline=e.roll_damage(foe,a,e.r.move('move/몸통박치기'),False,True)
        uid=self.equip(e,a,'crafted_item/명금의-로브')
        self.assertEqual(e.roll_damage(foe,a,e.r.move('move/몸통박치기'),False,True),max(0,baseline-5))
        e,a,foe=self.restore(e,a,foe)
        self.assertEqual(a.damage_reduction,5)
        key=next(key for key,row in a._item_reg.items() if row.get('instance_id')==uid)
        ITEMS.unregister_item(e,a,registration_key=key)
        self.assertEqual(a.damage_reduction,0)
        self.assertEqual(e.roll_damage(foe,a,e.r.move('move/몸통박치기'),False,True),baseline)

    def test_profileless_arcane_uses_occult_and_type_without_retyping_alchemy(self):
        for element in ('물','노말'):
            e,a,targets=self.fixture(rank=2,occult=7,element=element)
            uid=self.equip(e,a,'crafted_item/나인플레임의-스태프');entry=self.entry(a,uid)
            self.assertNotIn(FRAMEWORK.PROFILE,e._physical_objects[uid])
            struggle=WEAPONS.prepare(e,a,e.r.move(entry['struggle_id']),uid)
            self.assertEqual((struggle['type'],struggle['class']), (element,'특수'))
            self.assertEqual(e.damage_base(a,struggle),7)
            flame=WEAPONS.prepare(e,a,e.r.move('move/불꽃튀기기'),uid)
            self.assertEqual(flame['type'],'불꽃')
            self.assertEqual(FRAMEWORK.damage_roll_bonus(e,a,flame),5 if element=='노말' else 0)
            self.assertEqual(PRECISION.effect_natural(e,a,flame,15),17 if element=='노말' else 15)
            self.assertIn('occult education',FRAMEWORK.disarm_skills(e,a))
            e,a=self.restore(e,a)
            self.assertEqual(a.spec['skills']['오컬트학'],7)
            self.assertEqual(WEAPONS.prepare(e,a,e.r.move(entry['struggle_id']),uid)['type'],element)

    def test_chaos_native_area_bypasses_flying_levitate_and_balloon_components(self):
        for defense in ('levitate','balloon'):
            e,a,targets=self.fixture();uid=self.equip(e,a,'crafted_item/카오스-던커');target=targets[0]
            e.gm.set_types(target,['강철','비행'],reason='actual dual type')
            if defense=='levitate':e.gm.set_ability(target,'부유',reason='actual Levitate')
            else:self.equip(e,target,'item/풍선')
            self.begin(e,a);before=target.hp
            with patch.object(Engine,'d20',return_value=17):
                e.use_move_on(a,target,'move/지진',e.everyone,weapon_id=uid,aim=a.pos,set_damage=True)
            self.assertLess(target.hp,before)
            self.assertEqual(self.facts(e,'move/지진')[0]['type_multiplier'],1.5)
            self.assertEqual(HISTORY.last_damage(target)['move_type'],'땅')

    def test_chaos_keeps_selected_ground_resistance_and_final_source_chart(self):
        cases=((True,['비행'],.5,.5),
               (True,['비행','풀'],.25,.25),
               (False,['비행','풀'],0,.5),
               (True,['유리','땅'],1.5,1.5))
        for adopted,types,before_multiplier,expected in cases:
            with self.subTest(adopted=adopted,types=types):
                e,a,targets=self.fixture(count=1);target=targets[0]
                uid=self.equip(e,a,'crafted_item/카오스-던커')
                e.gm.set_types(target,types,reason='actual observed source-selected defensive types')
                e.configure_ground_flight_option(dict(enabled=adopted,gm_id='actual-gm',
                    reason='explicit adoption for this native source interaction'))
                self.assertFalse(getattr(target,'airborne',False))
                self.assertEqual(e.type_multiplier('땅',target)[0],before_multiplier)
                self.begin(e,a);hp=target.hp
                with patch.object(Engine,'d20',return_value=17):
                    e.use_move_on(a,target,'move/지진',e.everyone,weapon_id=uid,aim=a.pos,set_damage=True)
                self.assertLess(target.hp,hp)
                self.assertEqual(self.facts(e,'move/지진')[-1]['type_multiplier'],expected)
                self.assertEqual(HISTORY.last_damage(target)['move_type'],'땅')
                self.assertTrue(e.validate_state()['valid'])

    def test_chaos_uses_actual_damage_type_and_keeps_additional_resistance_steps(self):
        e,a,targets=self.fixture();uid=self.equip(e,a,'crafted_item/카오스-던커');target=targets[0]
        e.gm.set_types(target,['비행','강철'],reason='actual defensive typing')
        e.gm.set_ability(target,'부유',reason='actual Levitate')
        move=WEAPONS.prepare(e,a,e.r.move('move/지진'),uid)
        mechanics=e.r.move_mech('move/지진')[0]
        fire=EXT.effectiveness_hook(e,a,target,move,mechanics,e.type_multiplier('불꽃',target)[0],{'actual_damage_type':'불꽃'})
        self.assertEqual(fire,1.5)
        modified=dict(mechanics,effects_exec=[*mechanics.get('effects_exec',()),{'type':'type_effectiveness_override','steps':-1}])
        self.assertEqual(EXT.effectiveness_hook(e,a,target,move,modified,0,{'actual_damage_type':'땅'}),1.0)


if __name__=='__main__':unittest.main()
