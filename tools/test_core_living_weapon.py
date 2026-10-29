"""Actual Living Weapon consumers; no inherited/imported test collection."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
from unittest.mock import patch

STAGE=Path(__file__).resolve().parents[1]
ROOT=Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0]=[str(STAGE/'engine'),str(ROOT/'engine')]
from engine import Engine,Rules,Combatant
from builder import build_pokemon
from grid import Grid
import living_weapon as L
import weapon_actions as WEAPONS
import optional_weapon_framework as FW
import turn as TURN
import world_entities as W
import state_grants as G
import held_equipment as HELD


class CoreLivingWeaponTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    def fixture(self,species='단칼빙',rank=6,*,abilities=(),holder_abilities=(),rules=None):
        rules=rules or self.r
        e=Engine(rules,seed=71079);e.grid=Grid(25,15)
        actors=[]
        for n,name in enumerate(('파오리',species,'파오리')):
            spec=build_pokemon(rules,name,40,name=('holder','weapon','target')[n],
                moves=['move/몸통박치기'],abilities=list(abilities if n==1 else holder_abilities if n==0 else ()),
                wild=True,pos=(2+n,2),extra={'size':'소형','skills':{'전투':rank,'집중':6},
                    'movement':{'land':6 if n==0 else 2,'power':3},'movement_basis':'current'})
            c=Combatant(rules,spec);c.side='party' if n<2 else 'wild';actors.append(c)
        e.everyone=e.gm.everyone=actors
        return e,*actors

    def begin(self,e,c):
        if e._active_turn_actor is not None:e.end_of_turn(e._active_turn_actor)
        if not e.encounter_active:e.start_round(e.everyone)
        e.start_of_turn(c,initiative_count=20)

    def next_round(self,e,c):
        if e._active_turn_actor is not None:e.end_of_turn(e._active_turn_actor)
        e.start_round(e.everyone);e.start_of_turn(c,initiative_count=20)

    def valid(self,e):
        result=e.validate_state();self.assertTrue(result['valid'],result['issues'])

    def test_native_actual_pokemon_equip_and_attack_without_wielder_item_or_held_clone(self):
        e,a,p,t=self.fixture();out=e.equip_living_weapon(a,p,consent=True)
        key=out['weapon_keys'][0];self.assertEqual(p.spec[L.KEY]['wielder_id'],a.entity_id)
        self.assertIs(W.actor_index(e)[p.entity_id],p);self.assertEqual(p.pos,a.pos)
        self.assertEqual(HELD.entries(a),[]);self.assertNotIn(p.entity_id,getattr(e,'_physical_objects',{}))
        self.assertNotIn('framework_instance',a.custom_conditions['equipped_weapons'][key]['weapon'])
        self.begin(e,a);t.pos=(3,2);before=t.hp
        damage=e.use_move(a,t,'move/상처내기',weapon_id=key,set_damage=True)
        self.assertGreater(damage,0);self.assertGreaterEqual(before-t.hp,damage)
        self.assertEqual(a.move_uses['move/상처내기'],1);self.assertEqual(a.budget['standard'],0)
        self.valid(e)

    def test_species_shapes_hand_occupancy_consent_and_native_rank_matrix(self):
        for name,count,grade,evasion in (('단칼빙',1,'간단',0),('쌍검킬',2,'간단',2),('킬가르도',1,'좋음',1)):
            for rank in (3,4,6):
                with self.subTest(species=name,rank=rank):
                    e,a,p,t=self.fixture(name,rank)
                    before=deepcopy((a.spec,p.spec,a.moves,p.moves))
                    with self.assertRaisesRegex(ValueError,'permission'):e.equip_living_weapon(a,p,consent=False)
                    self.assertEqual((a.spec,p.spec,a.moves,p.moves),before)
                    out=e.equip_living_weapon(a,p,consent=True);ledger=a.custom_conditions['equipped_weapons']
                    self.assertEqual(len(ledger),count);self.assertEqual(a.evasion_mod,evasion)
                    expected=[] if rank==3 else L.PROFILES[name]['moves'][:1 if rank==4 else 2]
                    self.assertEqual(ledger[out['weapon_keys'][0]]['available_moves'][1:],expected)
                    self.assertTrue(all(row['weapon']['grade']==grade for row in ledger.values()))
                    with self.assertRaisesRegex(ValueError,'already equipped'):e.equip_living_weapon(t,p,consent=True)
                    if name!='단칼빙':
                        self.assertEqual({s for row in ledger.values() for s in row['slots']},{'주요손','반대손'})
                    self.valid(e)
        e,a,p,t=self.fixture('쌍검킬');e.equip_living_weapon(a,p,consent=True,slots=['주요손'])
        self.assertEqual(a.evasion_mod,0);self.assertEqual(len(a.custom_conditions['equipped_weapons']),1)

    def test_fainted_equipment_accuracy_and_all_equipment_skill_checks_only_once(self):
        e,a,p,t=self.fixture();key=e.equip_living_weapon(a,p,consent=True)['weapon_keys'][0]
        move=WEAPONS.prepare(e,a,e.r.move('move/상처내기'),key)
        self.assertEqual(WEAPONS.accuracy_bonus(move),0)
        self.assertEqual(FW.damage_roll_bonus(e,a,move),0)
        e.gm.set_hp(p,0,reason='actual weapon Pokemon fainted')
        prepared=WEAPONS.prepare(e,a,e.r.move('move/상처내기'),key)
        twice=WEAPONS.prepare(e,a,prepared)
        self.assertEqual(WEAPONS.accuracy_bonus(twice),-2)
        self.assertEqual(FW.damage_roll_bonus(e,a,twice),-2)
        self.assertIn(L.KEY,p.spec)
        t.pos=(3,2)
        observed=[]
        import combat_hit as HIT
        original=HIT.resolve
        def capture(**options):observed.append(options);return original(**options)
        with patch.object(HIT,'resolve',capture):
            e.accuracy_check(a,t,prepared,fixed_roll=10)
            e.accuracy_check(a,t,e.r.move('move/몸통박치기'),fixed_roll=10)
        self.assertEqual(observed[0]['modifier'],observed[1]['modifier']-2)
        context={'living_weapon':{'pokemon_id':p.entity_id}}
        base=e.skill_roll(a,'전투',fixed=[3]*6)
        using=e.skill_roll(a,'전투',fixed=[3]*6,skill_context=context)
        self.assertEqual(using.total,base.total-2)
        self.begin(e,a);before=t.hp
        with patch.object(e,'d20',return_value=20):
            self.assertGreater(e.use_move(a,t,'move/상처내기',weapon_id=key,set_damage=True),0)
        self.assertLess(t.hp,before)
        self.begin(e,p);before=deepcopy((p.move_uses,p.budget))
        self.assertEqual(e.use_move(p,t,'move/상처내기',weapon_id=key,set_damage=True),0)
        self.assertEqual((p.move_uses,p.budget),before)
        self.valid(e)

    def test_each_actual_pokemon_turn_moves_both_at_wielder_speed_without_shared_pool(self):
        e,a,p,t=self.fixture();e.equip_living_weapon(a,p,consent=True);t.pos=(21,2)
        self.begin(e,a);first=e.approach(a,t)
        self.assertEqual(first['distance'],6);self.assertEqual(p.pos,a.pos)
        self.assertEqual(a.budget['shift'],0);self.assertIsNone(getattr(p,'budget',None))
        self.begin(e,p);second=e.approach(p,t)
        self.assertEqual(second['distance'],6);self.assertEqual(p.pos,a.pos)
        self.assertEqual(p.budget['shift'],0);self.assertEqual(a.budget['shift'],0)
        self.assertEqual(a.pos[0],14);self.assertEqual(a.spec['movement']['land'],6)
        self.assertEqual(p.spec['movement']['land'],2)
        self.valid(e)

    def test_live_borrowed_native_moves_use_own_actions_and_frequency_and_detach_preserves_learning(self):
        e,a,p,t=self.fixture('킬가르도');key=e.equip_living_weapon(a,p,consent=True)['weapon_keys'][0]
        self.assertIn('move/출혈',p.moves)
        sid=p.spec[L.KEY]['grant_source'];self.assertEqual(p.spec[G.KEY]['sources'][sid]['move_mode'],'permission')
        e.gm.set_move(p,'move/상처내기',True,reason='independent natural learning overlaps permission')
        t.pos=(3,2);self.begin(e,p)
        with patch.object(e,'d20',return_value=20):
            damage=e.use_move(p,t,'move/출혈',weapon_id=key,set_damage=True)
        self.assertGreater(damage,0);self.assertEqual(p.move_uses['move/출혈'],1)
        self.assertNotIn('move/출혈',a.move_uses);self.assertEqual(p.budget['standard'],0)
        self.assertIn('move/상처내기',p.spec['moves']);used=deepcopy(p.move_uses)
        e.separate_living_weapon(p,destination=(2,3))
        self.assertNotIn('move/출혈',p.moves);self.assertIn('move/상처내기',p.moves)
        self.assertEqual(p.move_uses,used);self.assertNotIn(L.KEY,p.spec)
        self.assertNotIn(sid,p.spec[G.KEY]['sources']);self.assertEqual(a.evasion_mod,0)
        self.valid(e)

    def test_current_donor_rank_changes_and_other_actual_weapon_permissions_are_live(self):
        e,a,p,t=self.fixture(rank=3);key=e.equip_living_weapon(a,p,consent=True)['weapon_keys'][0]
        self.assertNotIn('move/상처내기',p.moves)
        a.spec['skills']['전투']=4;L.refresh(e,p);self.assertIn('move/상처내기',p.moves)
        # The other hand's actual equipped source also supplies C10-076.
        # This holder is a Pokemon, so use the ordinary Wielder owner faithfully.
        a.spec['capabilities']=['장착자']
        W.register_object(e,'external/offhand',location={'kind':'unknown'},owner_id=a.entity_id,weight_kg=1,reason='actual external weapon')
        FW.observe_weapon(e,a,'external/offhand',name='actual other weapon',kind='소형 근접무기',grade='간단',
                          arcane=False,metal=False,moves=['move/강타'],reason='actual ordinary weapon profile')
        e.gm.set_carried_objects(a,[{'id':'external/offhand','weight_kg':1}],'actual possession')
        other=FW.equip(e,a,'external/offhand',slot='반대손');L.refresh(e,p)
        self.assertIn('move/강타',p.moves);t.pos=(3,2);self.begin(e,p)
        with patch.object(e,'d20',return_value=20):
            self.assertGreater(e.use_move(p,t,'move/강타',weapon_id=other,set_damage=True),0)
        self.assertEqual(p.move_uses['move/강타'],1);self.assertNotIn('move/강타',a.move_uses)
        a.spec['skills']['전투']=3
        self.next_round(e,p);before=deepcopy((p.budget,p.move_uses,e.rng.getstate(),t.hp))
        with self.assertRaises(ValueError):e.use_move(p,t,'move/강타',weapon_id=other,set_damage=True)
        self.assertEqual((p.budget,p.move_uses,e.rng.getstate(),t.hp),before)
        a.spec['skills']['전투']=4;L.refresh(e,p);self.valid(e)

    def test_noguard_exact_source_exclusion_on_weapon_attacker_or_target_preserves_caps_and_others(self):
        e,a,p,t=self.fixture(abilities=['노가드 [Playtest]'],holder_abilities=['노가드 [Playtest]'],rules=Rules(ROOT,ruleset='all'))
        e.equip_living_weapon(a,p,consent=True);self.begin(e,a);t.pos=(3,2)
        import combat_hit as HIT
        original=HIT.resolve;seen=[]
        def capture(**options):seen.append(options);return original(**options)
        pairs=((p,t),(a,t),(t,p),(t,a))
        with patch.object(HIT,'resolve',capture):
            for attacker,target in pairs:e.accuracy_check(attacker,target,e.r.move('move/몸통박치기'),fixed_roll=10)
        baseline=[x['modifier'] for x in seen];seen.clear()
        # Native registration retains the exact scoped row from abilities-llm.
        e.register_abilities(a);e.register_abilities(p)
        for owner in (a,p):
            rows=[x for x in owner.modifiers if L.no_guard(x)]
            self.assertEqual(len(rows),1)
            target_effect=next(x for x in rows if x.get('target')=='enemies vs user')
            self.assertEqual((target_effect['type'],target_effect['value'],target_effect['_ability']),
                             ('accuracy_mod',3,'노가드 [Playtest]'))
            self.assertIn(G.TAG,target_effect)
            self.assertEqual(target_effect['_rule_id'],'ability/노가드-playtest')
            self.assertEqual(owner.spec[G.KEY]['numbers']['accuracy_stage']['sources'],
                             {'ability:노가드 [Playtest]':3})
        with patch.object(HIT,'resolve',capture):
            for attacker,target in pairs:e.accuracy_check(attacker,target,e.r.move('move/몸통박치기'),fixed_roll=10)
        self.assertEqual([x['modifier']-old for x,old in zip(seen,baseline)],[0,3,0,3])
        for order in ((p,t),(t,p)):
            shared={};seen.clear();consumed=[];consume=e.rulings.consume
            def ruling(kind,*args,**kwargs):
                if kind=='accuracy':consumed.append(kind)
                return consume(kind,*args,**kwargs)
            with patch.object(HIT,'resolve',capture),patch.object(e.rulings,'consume',ruling):
                for target in order:e.accuracy_check(a,target,e.r.move('move/몸통박치기'),fixed_roll=10,shared_roll=shared)
            self.assertEqual([x['modifier'] for x in seen],[0 if x is p else 3 for x in order])
            self.assertEqual(consumed,['accuracy'])
        sid='fixture:other-accuracy';G._source(p,sid,'fixture');G.numeric(p,'accuracy_stage',5,sid,bounds=(-6,6))
        self.assertEqual(p.accuracy_stage,6)
        self.assertEqual(L.accuracy_stage(e,p,t,6),5)
        self.assertIn('노가드 [Playtest]',p.abilities)
        self.valid(e)

    def test_blade_form_lock_blocks_native_battle_switch_shield_full_action_and_releases_on_separation(self):
        e,a,p,t=self.fixture('킬가르도',abilities=['ability/배틀스위치'])
        e.equip_living_weapon(a,p,consent=True);self.assertEqual(p.form,'블레이드폼')
        blade=deepcopy(p.stats);self.begin(e,p)
        e.activate_ability_state(p,'ability/배틀스위치',choice='실드폼',reason='actual full action attempt')
        self.assertEqual(p.form,'블레이드폼');self.assertEqual(p.stats,blade)
        self.assertEqual(p.budget['standard'],0);self.assertEqual(p.budget['shift'],0)
        import ability_state_projection as P
        P.after_move(e,p,'move/방어',{'class':'변화','keywords':[]},{})
        self.assertEqual(p.form,'블레이드폼')
        import form_allocations as FORMS
        with self.assertRaisesRegex(ValueError,'fixed'):FORMS.switch(e,p,'실드폼')
        e.separate_living_weapon(p,destination=(2,3));self.assertEqual(p.form,'블레이드폼')
        self.next_round(e,p)
        e.activate_ability_state(p,'ability/배틀스위치',choice='실드폼',reason='normal independent full action')
        self.assertEqual(p.form,'실드폼');self.valid(e)

    def test_joint_reattachment_cost_failure_atomicity_and_both_real_standard_payments(self):
        e,a,p,t=self.fixture();e.equip_living_weapon(a,p,consent=True)
        self.begin(e,a);e.separate_living_weapon(a,destination=(2,3))
        # Holder already spent its Standard. The joint reattachment must not
        # spend the partner action, alter RNG or install any partial relation.
        a.budget['standard']=0;before=deepcopy((a.spec,p.spec,a.budget,getattr(p,'budget',None),e.rng.getstate()))
        with self.assertRaisesRegex(ValueError,'Standard'):e.equip_living_weapon(a,p,consent=True)
        self.assertEqual((a.spec,p.spec,a.budget,getattr(p,'budget',None),e.rng.getstate()),before)
        self.next_round(e,a);e.equip_living_weapon(a,p,consent=True)
        self.assertEqual(a.budget['standard'],0);self.assertEqual(p.pending_action_loss,{'standard':1})
        self.begin(e,p);self.assertEqual(p.budget['standard'],0);self.assertIsNone(p.pending_action_loss)
        self.valid(e)

    def test_gm_json_identity_restore_tamper_and_unavailable_actor_never_becomes_remote_equipment(self):
        e,a,p,t=self.fixture();key=e.equip_living_weapon(a,p,consent=True)['weapon_keys'][0]
        e.gm.snapshot('living-equipped');e.separate_living_weapon(a,destination=(2,3))
        e.gm.restore('living-equipped');self.assertIs(W.actor_index(e)[p.entity_id],p)
        saved=json.loads(json.dumps(e.export_state()));loaded=Engine.import_state(self.r,saved)
        a2,p2,t2=(W.actor_index(loaded)[x.entity_id] for x in (a,p,t))
        self.assertEqual(p2.spec[L.KEY]['wielder_id'],a2.entity_id)
        self.assertEqual(HELD.entries(a2),[]);self.begin(loaded,a2);t2.pos=(3,2)
        self.assertGreater(loaded.use_move(a2,t2,'move/상처내기',weapon_id=key,set_damage=True),0)
        self.valid(loaded)
        p2.spec[L.KEY]['pokemon_id']='forged/actor'
        self.assertFalse(loaded.validate_state()['valid'])
        with self.assertRaises(ValueError):loaded.export_state()
        p2.spec[L.KEY]['pokemon_id']=p2.entity_id;p2.on_field=False
        self.next_round(loaded,a2);before=deepcopy((a2.budget,a2.move_uses,t2.hp,loaded.rng.getstate()))
        with self.assertRaisesRegex(ValueError,'available'):loaded.use_move(a2,t2,'move/상처내기',weapon_id=key,set_damage=True)
        self.assertEqual((a2.budget,a2.move_uses,t2.hp,loaded.rng.getstate()),before)
        self.assertIn(L.KEY,p2.spec);self.assertTrue(a2.on_field)


if __name__=='__main__':unittest.main()
