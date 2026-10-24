"""C10-071/075/076: actual holders, source choices and retained native grants."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import unittest

from engine import Engine
import living_weapon as L
import native_scenario_fixture as NATIVE
import optional_weapon_framework as FW
import state_codec as CODEC
import state_grants as G
import weapon_actions as WEAPONS
import world_entities as W

ROOT=Path(__file__).resolve().parents[1]
WOUND='move/상처내기'
BLEED='move/출혈'
OTHER='move/강타'


class LivingWeaponCapsShieldSourceRevisionTests(unittest.TestCase):
    def world(self,*,species='킬가르도',holder='pokemon',rank=6,ruleset='core'):
        def actor(key,kind,name,pos,side):
            sheet={'name':key,'level':40,'moves':['move/몸통박치기'],'abilities':[],
                   'pos':pos,'side':side,'extra':{'skills':{'전투':6,'집중':6},
                       'movement':{'land':6,'power':3},'movement_basis':'current'}}
            if kind=='pokemon':sheet.update(species=name,wild=True)
            else:sheet['stats']=dict.fromkeys(('hp','atk','def','spa','spd','spe'),30)
            size='소형' if kind=='pokemon' else '중형'
            return {'key':key,'kind':kind,'sheet':sheet,
                    'body':{'size':size,'offsets':[(0,0)],'reason':'actual observed native participant body'}}
        self.e,actors=NATIVE.prepare_scene(ROOT,ruleset=ruleset,seed=710760,
            grid={'width':12,'height':10},actors=[
                actor('holder',holder,'파오리',(2,2),'party'),
                actor('weapon','pokemon',species,(3,2),'party'),
                actor('target','pokemon','파오리',(4,2),'opponent')])
        self.a,self.p,self.t=(actors[k] for k in ('holder','weapon','target'))
        if rank>6:
            self.e.r.rulings.set_mech('gameplay/skill-rank-dice','by_rank_name.ordinary'+str(rank),
                {'rank':rank,'dice':f'{rank}d6','eng':'Ordinary'+str(rank)},
                reason='campaign declares this ordinary rank without Virtuoso',scope='campaign',rules=self.e.r)
        self.e.gm.set_skill(self.a,'전투',rank,reason='actual current ordinary Combat rank')

    def choice(self,variant):
        pending=L.borrowing_choices(self.e)
        self.assertEqual(pending['status'],'PolicyInputsRequired')
        self.assertEqual(pending['obligations'][0]['decision_kind'],'source_conflict')
        return {'value':variant,'reason':'campaign explicitly selects this complete source rule',
                'scope':pending['decision_scope']}

    def equip(self,variant=None):
        choice=None if variant is None else self.choice(variant)
        self.key=self.e.equip_living_weapon(self.a,self.p,consent=True,source_choice=choice)['weapon_keys'][0]
        self.t.pos=(3,2)
        return choice

    def turn(self,actor):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        if not self.e.encounter_active:self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor,initiative_count=20)

    def restore(self):
        identities=[c.entity_id for c in (self.a,self.p,self.t)]
        self.e=CODEC.load_engine(self.e.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        index=W.actor_index(self.e)
        self.a,self.p,self.t=(index[key] for key in identities)

    def external(self,mid=OTHER):
        uid='external/source-choice-weapon'
        W.register_object(self.e,uid,location={'kind':'unknown'},owner_id=self.a.entity_id,
                          weight_kg=1,reason='actual other weapon owned by the holder')
        FW.observe_weapon(self.e,self.a,uid,name='actual other weapon',kind='소형 근접무기',
            grade='간단',arcane=False,metal=False,moves=[mid],reason='actual complete ordinary weapon profile')
        self.e.gm.set_carried_objects(self.a,[{'id':uid,'weight_kg':1}],'actual possession of the other weapon')
        if self.a.kind=='pokemon':self.a.spec['capabilities']=['장착자']
        key=FW.equip(self.e,self.a,uid,slot='반대손')
        L.refresh(self.e,self.p)
        return key

    def test_pokemon_holder_cap_survives_ordinary_high_ranks_and_rejects_native_master_use(self):
        for rank in (3,4,6,7,10):
            with self.subTest(rank=rank):
                self.world(rank=rank);self.equip()
                available=self.a.custom_conditions['equipped_weapons'][self.key]['available_moves']
                self.assertEqual(available,[self.key] if rank<4 else [self.key,WOUND])
                self.assertNotIn(BLEED,self.p.moves)
                self.assertNotIn('edge/거장',self.a.spec.get('edges',[]))
                weapon=self.a.custom_conditions['equipped_weapons'][self.key]['weapon']
                NATIVE.assert_rejected_unchanged(self.e,
                    lambda:WEAPONS.validate_grant(self.e,self.a,weapon,BLEED),reason_pattern='above Adept')
                self.turn(self.a)
                NATIVE.assert_rejected_unchanged(self.e,
                    lambda:self.e.use_move(self.a,self.t,BLEED,weapon_id=self.key,set_damage=True),
                    reason_pattern='selected physical weapon does not grant')
                if rank>=4:
                    with patch.object(Engine,'d20',return_value=20):
                        self.assertGreater(self.e.use_move(self.a,self.t,WOUND,weapon_id=self.key,set_damage=True),0)

    def test_trainer_master_and_weapon_borrowing_remain_legal_at_six_seven_and_ten(self):
        for rank in (6,7,10):
            with self.subTest(rank=rank):
                self.world(holder='trainer',rank=rank);self.equip('english_own_living_weapon')
                self.assertIn(BLEED,self.a.moves);self.assertIn(BLEED,self.p.moves)
                self.assertEqual(self.a.custom_conditions['equipped_weapons'][self.key]['available_moves'],
                                 [self.key,WOUND,BLEED])
                self.restore()
                for actor in (self.a,self.p):
                    self.turn(actor)
                    with patch.object(Engine,'d20',return_value=20):
                        self.assertGreater(self.e.use_move(actor,self.t,BLEED,weapon_id=self.key,set_damage=True),0)
                    self.assertEqual((actor.move_uses[BLEED],actor.budget['standard']),(1,0))
                self.assertTrue(self.e.validate_state()['valid'])

    def test_complete_borrowing_variants_restore_and_feed_actual_other_weapon_attacks(self):
        for variant,borrows in ((None,True),('korean_all_equipped',True),('english_own_living_weapon',False)):
            with self.subTest(variant=variant):
                self.world(species='단칼빙');choice=self.equip(variant);other=self.external()
                self.assertEqual(OTHER in self.p.moves,borrows)
                self.e.gm.snapshot('explicit-borrowing');self.e.gm.restore('explicit-borrowing')
                self.restore();self.assertEqual(self.p.spec[L.KEY].get('source_choice'),choice)
                self.turn(self.p)
                if borrows:
                    with patch.object(Engine,'d20',return_value=20):
                        self.assertGreater(self.e.use_move(self.p,self.t,OTHER,weapon_id=other,set_damage=True),0)
                    self.assertEqual((self.p.move_uses[OTHER],self.p.budget['standard']),(1,0))
                    self.assertNotIn(OTHER,self.a.move_uses)
                else:
                    NATIVE.assert_rejected_unchanged(self.e,
                        lambda:self.e.use_move(self.p,self.t,OTHER,weapon_id=other,set_damage=True),
                        reason_pattern='selected physical weapon does not grant')
                self.turn(self.a)
                with patch.object(Engine,'d20',return_value=20):
                    self.assertGreater(self.e.use_move(self.a,self.t,OTHER,weapon_id=other,set_damage=True),0)
                self.assertTrue(self.e.validate_state()['valid'])

    def test_same_move_other_source_cannot_bypass_english_choice_and_rank_permissions_remain_live(self):
        for variant,own_only in (('korean_all_equipped',False),('english_own_living_weapon',True)):
            with self.subTest(variant=variant):
                self.world(species='단칼빙');self.equip(variant);other=self.external(WOUND)
                self.assertIn(WOUND,self.p.moves)
                if own_only:
                    prepared=WEAPONS.prepare(self.e,self.p,self.e.r.move(WOUND))
                    self.assertEqual(prepared['_living_borrow']['weapon_key'],self.key)
                    NATIVE.assert_rejected_unchanged(self.e,
                        lambda:WEAPONS.prepare(self.e,self.p,self.e.r.move(WOUND),other),
                        reason_pattern='selected donor weapon no longer grants')
                else:
                    NATIVE.assert_rejected_unchanged(self.e,
                        lambda:WEAPONS.prepare(self.e,self.p,self.e.r.move(WOUND)),
                        reason_pattern='explicit weapon_id')
                    self.assertEqual(WEAPONS.prepare(self.e,self.p,self.e.r.move(WOUND),other)
                                     ['_living_borrow']['weapon_key'],other)
                self.e.gm.set_skill(self.a,'전투',3,reason='actual donor no longer qualifies')
                L.refresh(self.e,self.p);self.assertNotIn(WOUND,self.p.moves)
                self.turn(self.p)
                NATIVE.assert_rejected_unchanged(self.e,
                    lambda:self.e.use_move(self.p,self.t,WOUND,weapon_id=self.key,set_damage=True),
                    reason_pattern='selected physical weapon does not grant')
                self.e.gm.set_skill(self.a,'전투',4,reason='actual donor recovers Adept Combat')
                L.refresh(self.e,self.p);self.assertIn(WOUND,self.p.moves)
                self.e.gm.set_move(self.p,WOUND,True,reason='independent learning overlaps borrowed permission')
                self.e.separate_living_weapon(self.p,destination=(2,3))
                self.assertIn(WOUND,self.p.moves);self.assertNotIn(L.KEY,self.p.spec)

    def test_core_and_adopted_errata_shield_replace_only_their_contribution_through_restore_and_detach(self):
        for profile,bonus in (('core',2),('core+errata',1)):
            with self.subTest(profile=profile):
                self.world(ruleset=profile)
                G._source(self.a,'fixture:independent','fixture')
                G.numeric(self.a,'evasion_mod',1,'fixture:independent',bounds=(-6,6))
                ordinary=self.a.evasion('물리',engine=self.e)
                self.equip();self.assertEqual(self.a.evasion_mod,bonus+1)
                self.assertEqual(self.a.evasion('물리',engine=self.e),ordinary+bonus)
                self.e.gm.snapshot('sourced-shield');self.e.gm.restore('sourced-shield');self.restore()
                self.assertEqual(self.a.evasion_mod,bonus+1)
                sid=self.p.spec[L.KEY]['grant_source']
                self.assertEqual(self.a.spec[G.KEY]['numbers']['evasion_mod']['sources'],
                                 {'fixture:independent':1,sid:bonus})
                self.turn(self.p);self.e.separate_living_weapon(self.p,destination=(2,3))
                self.assertEqual(self.a.evasion_mod,1)
                self.assertEqual(self.a.spec[G.KEY]['numbers']['evasion_mod']['sources'],{'fixture:independent':1})
                self.assertTrue(self.e.validate_state()['valid'])

    def test_source_scope_and_stale_core_shield_reject_without_silent_conversion(self):
        self.world();choice=self.choice('english_own_living_weapon');bad=deepcopy(choice)
        bad['scope']['definition_hash']='changed'
        NATIVE.assert_rejected_unchanged(self.e,
            lambda:self.e.equip_living_weapon(self.a,self.p,consent=True,source_choice=bad),
            reason_pattern='GM decision scope changed')
        self.equip('english_own_living_weapon');sid=self.p.spec[L.KEY]['grant_source']
        before=deepcopy(self.p.spec[L.KEY]);self.p.spec[L.KEY]['source_choice']['scope']['profile_hash']='changed'
        self.assertFalse(self.e.validate_state()['valid'])
        self.p.spec[L.KEY]=before
        self.a.spec[G.KEY]['numbers']['evasion_mod']['sources'][sid]=1
        self.assertFalse(self.e.validate_state()['valid'])
        with self.assertRaisesRegex(ValueError,'shield differs'):self.e.export_state()


if __name__=='__main__':unittest.main()
