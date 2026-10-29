"""Actual Wielder consumers; shared equipment/source/resource evidence is reused."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

STAGE=Path(__file__).resolve().parents[1]
ROOT=Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0]=[str(STAGE/'engine'),str(ROOT/'engine')]
from engine import Engine,Rules,Combatant
from builder import build_pokemon
from grid import Grid
import held_equipment as HELD
import items as ITEMS
import optional_weapon_framework as FW
import state_grants as GRANTS
import turn as TURN
import wielder_capability as WIELDER
import world_entities as WORLD


class CoreWielderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    def fixture(self,size='소형',*,wielder=True):
        e=Engine(self.r,seed=151152);e.grid=Grid(20,15)
        actors=[]
        for n in range(2):
            spec=build_pokemon(self.r,'파오리',30,name='wielder-'+str(n),
                moves=['move/몸통박치기'],abilities=[],wild=True,pos=(2+n,2),
                extra={'size':size if n==0 else '중형','skills':{'전투':6,'은신':6,'집중':6},
                       'capabilities':['장착자'] if n==0 and wielder else [],
                       'movement':{'land':6,'power':3},'movement_basis':'current'})
            c=Combatant(self.r,spec);c.side='party' if n==0 else 'wild'
            actors.append(c)
        e.everyone=e.gm.everyone=actors
        return e,*actors

    def weapon(self,e,a,uid='wielder/external',*,kind=None,moves=('move/강타',)):
        kind=kind or ('소형 근접무기' if a.spec['size']=='소형' else '대형 근접무기')
        WORLD.register_object(e,uid,location={'kind':'unknown'},owner_id=a.entity_id,
            weight_kg=1,reason='actual external melee weapon')
        FW.observe_weapon(e,a,uid,name=uid,kind=kind,grade='좋음',arcane=False,
            metal=False,moves=moves,reason='GM observed actual ordinary weapon')
        e.gm.set_carried_objects(a,[*a.spec.get('_carried_load',{}).get('objects',[]),
            {'id':uid,'weight_kg':1}],'actual physical weapon possession')
        return uid

    def start(self,e,a):
        if e._active_turn_actor is not None:e.end_of_turn(e._active_turn_actor)
        e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)

    def valid(self,e):
        result=e.validate_state();self.assertTrue(result['valid'],result['issues'])

    def test_small_medium_large_native_equipment_attack_and_single_held_occupancy(self):
        for size in ('소형','중형','대형'):
            with self.subTest(size=size):
                e,a,b=self.fixture(size);uid=self.weapon(e,a)
                self.start(e,a);out=e.equip_equipment(a,uid)
                self.assertEqual(out['equipped'],uid);self.assertEqual(a.budget['standard'],0)
                ledger=a.custom_conditions['equipped_weapons'];self.assertEqual(len(ledger),1)
                key=next(iter(ledger));held=HELD.entries(a)
                self.assertEqual(len(held),1);self.assertEqual(held[0]['weapon_key'],key)
                self.assertEqual(held[0]['instance_id'],uid)
                self.assertEqual(len(ITEMS.equipment_options(a,('held','주요손','반대손'))),1)
                with self.assertRaisesRegex(ValueError,'held-item slot'):
                    ITEMS.register_item(e,a,'선제공격손톱',as_held=True)
                self.start(e,a);before=b.hp
                damage=e.use_move(a,b,'move/강타',set_damage=True,weapon_id=uid)
                self.assertGreater(damage,0);self.assertEqual(before-b.hp,damage)
                self.assertEqual(a.budget['standard'],0);self.assertEqual(a.move_uses['move/강타'],1)
                self.valid(e)

    def test_actual_attached_identity_blocks_every_removal_and_both_native_disarms(self):
        e,a,b=self.fixture();WIELDER.observe_natural_weapon(e,a,'appendage/blade',name='actual attached blade',reason='observed attached anatomy')
        self.assertNotIn('appendage/blade',getattr(e,'_physical_objects',{}));self.assertEqual(HELD.entries(a),[])
        row=ITEMS.selected_equipment(a,'natural:appendage/blade',('held',))
        import equipment_protection as P
        before=deepcopy((a.custom_conditions,a.spec,e.rng.getstate()))
        for operation in ('transfer','exchange','give','drop','disarm','destroy'):
            with self.subTest(operation=operation):
                with self.assertRaises(P.ProtectedEquipment):P.require(e,a,row,operation,(a,))
        for action in (lambda:ITEMS.transfer_equipment(e,a,b,row['key']),
                       lambda:ITEMS.drop_item(e,a,selection=row['key']),
                       lambda:ITEMS.destroy_equipment(e,a,row['key'],reason='actual removal attempt'),
                       lambda:ITEMS.exchange_items(e,a,b,first_selection=row['key'])):
            with self.assertRaises(P.ProtectedEquipment):action()
        self.assertEqual((a.custom_conditions,a.spec,e.rng.getstate()),before)
        GRANTS.grant(b,'capabilities','Telekinetic','fixture:telekinetic','fixture')
        self.start(e,b);before=deepcopy((b.budget,e.rng.getstate(),getattr(b,'_action_history',[])))
        self.assertFalse(e.disarm(b,a,attacker_skill='전투',defender_skill='전투',item_name=row['key'],fixed_accuracy=20))
        self.assertFalse(e.telekinetic_maneuver(b,a,'disarm',defender_skill='전투',item_name=row['key'],fixed_accuracy=20))
        self.assertEqual((b.budget,e.rng.getstate(),getattr(b,'_action_history',[])),before)
        self.valid(e)

    def test_external_disarm_uses_plus_two_once_on_both_participants_and_telekinetic(self):
        for remote,attacker_wielder in ((False,False),(False,True),(True,False),(True,True)):
            with self.subTest(remote=remote,attacker_wielder=attacker_wielder):
                e,a,b=self.fixture();uid=self.weapon(e,a);key=FW.equip(e,a,uid)
                WIELDER.observe_natural_weapon(e,a,'appendage/blade',name='attached blade',reason='observed actual anatomy')
                if attacker_wielder:GRANTS.grant(b,'capabilities','Wielder','fixture:wielder','fixture')
                GRANTS.grant(b,'capabilities','Telekinetic','fixture:telekinetic','fixture')
                self.start(e,b);observed=[];original=Engine.opposed_check
                def resolve(current,*args,**kwargs):
                    observed.append(deepcopy(kwargs));return original(current,*args,**kwargs)
                with patch.object(Engine,'opposed_check',resolve):
                    options=dict(defender_skill='전투',item_name=key,fixed_accuracy=20,
                        challenger_options={'fixed':[6]*6,'mods':3},defender_options={'fixed':[1]*6,'mods':4})
                    result=(e.telekinetic_maneuver(b,a,'disarm',**options) if remote else
                            e.disarm(b,a,attacker_skill='전투',**options))
                self.assertTrue(result);self.assertEqual(len(observed),1)
                self.assertEqual(observed[0]['challenger_options']['mods'],5 if attacker_wielder else 3)
                self.assertEqual(observed[0]['defender_options']['mods'],6)
                self.assertEqual(b.budget['standard'],0)
                self.assertEqual(HELD.entries(a),[]);self.assertNotIn(key,a.moves)
                obj=e._physical_objects[uid]
                self.assertNotIn('equipped_by',obj);self.assertNotIn('carrier_id',obj)
                self.assertEqual(WORLD.effective_location(e,obj),WORLD.location_of(a))
                self.assertIn('appendage/blade',a.spec['observed_appendages'])
                self.assertEqual(len(ITEMS.equipment_options(a,('held',))),1)
                self.valid(e)

    def test_current_source_size_and_rank_limits_preserve_actual_objects_and_independent_moves(self):
        e,a,b=self.fixture();uid=self.weapon(e,a)
        e.gm.set_move(a,'move/강타',True,reason='independently learned before equipment')
        key=FW.equip(e,a,uid);self.assertEqual(a.custom_conditions['equipped_weapons'][key]['available_moves'],[key,'move/강타'])
        self.start(e,a)
        before=deepcopy((a.budget,a.move_uses,e.rng.getstate(),a.custom_conditions,HELD.entries(a)))
        a.spec['capabilities']=[]
        with self.assertRaisesRegex(ValueError,'current Wielder'):e.use_move(a,b,'move/강타',weapon_id=uid,set_damage=True)
        self.assertEqual((a.budget,a.move_uses,e.rng.getstate(),a.custom_conditions,HELD.entries(a)),before)
        a.spec['capabilities']=['장착자'];a.spec['size']='중형'
        with self.assertRaisesRegex(ValueError,'current Wielder size'):e.use_move(a,b,'move/강타',weapon_id=uid,set_damage=True)
        self.assertEqual(e._physical_objects[uid]['equipped_by'],a.entity_id)
        a.spec['size']='소형'
        a.spec['capabilities']=[]
        e.gm.set_item(a,None,reason='actual Wielder source loss; remove external equipment explicitly')
        self.assertNotIn(key,a.moves);self.assertIn('move/강타',a.moves);self.assertEqual(HELD.entries(a),[])
        self.assertIn(uid,e._physical_objects)
        self.assertNotIn('equipped_by',e._physical_objects[uid]);self.assertEqual(e._physical_objects[uid]['carrier_id'],a.entity_id)
        a.spec['capabilities']=['장착자']
        for kind in ('대형 근접무기','단거리 사격무기'):
            wrong=self.weapon(e,a,'wrong/'+kind,kind=kind)
            with self.assertRaisesRegex(ValueError,'current Wielder size'):FW.equip(e,a,wrong)
        with self.assertRaisesRegex(ValueError,'above Adept'):
            self.weapon(e,a,'wrong/master',moves=('move/출혈',))
        with patch.object(e.r,'_selected_rule',side_effect=lambda source: 'variant/wielder' if source==WIELDER.SOURCE else source):
            with self.assertRaisesRegex(ValueError,'variant'):FW.equip(e,a,uid)
        self.valid(e)

    def test_gm_and_json_restore_retain_one_weapon_slot_attached_identity_and_actual_native_use(self):
        e,a,b=self.fixture();uid=self.weapon(e,a);key=FW.equip(e,a,uid)
        WIELDER.observe_natural_weapon(e,a,'appendage/blade',name='attached blade',reason='observed actual anatomy')
        e.gm.snapshot('wielder-equipped');TURN.unequip_weapon(e,a,key)
        e.gm.restore('wielder-equipped');self.assertIs(WORLD.actor_index(e)[a.entity_id],a)
        self.assertEqual(HELD.entries(a)[0]['weapon_key'],key)
        loaded=Engine.import_state(self.r,json.loads(json.dumps(e.export_state())))
        current=WORLD.actor_index(loaded)[a.entity_id];target=WORLD.actor_index(loaded)[b.entity_id]
        self.assertEqual(HELD.entries(current)[0]['instance_id'],uid)
        self.assertEqual(len(ITEMS.equipment_options(current,('held',))),2)
        self.assertIsNone(TURN.disarm_equipment(loaded,current,'natural:appendage/blade'))
        self.start(loaded,current);before=target.hp
        self.assertGreater(loaded.use_move(current,target,key,weapon_id=uid,set_damage=True),0)
        self.assertLess(target.hp,before);self.assertEqual(current.budget['standard'],0)
        self.valid(loaded)
        import state_codec as CODEC
        saved=loaded.export_state()
        for corruption in ('missing','duplicate'):
            with self.subTest(corruption=corruption):
                forged_engine=Engine.import_state(self.r,deepcopy(saved))
                holder=WORLD.actor_index(forged_engine)[a.entity_id]
                if corruption=='missing':
                    holder.spec['held_equipment']=[];holder.spec['item']=None
                else:
                    extra=deepcopy(HELD.entries(holder)[0]);extra['slot_id']='held:2'
                    HELD.entries(holder).append(extra);holder.spec.pop('item',None)
                self.assertFalse(forged_engine.validate_state()['valid'])
                with self.assertRaisesRegex(ValueError,'held'):
                    forged_engine.export_state()
                with self.assertRaisesRegex(ValueError,'held'):
                    forged_engine.gm.snapshot('forged-held-slot')
                # Encode a syntactically valid forged graph without the save
                # preflight, then use the actual JSON loader admission.
                encoder=CODEC._Encoder(forged_engine)
                payload=deepcopy(saved);payload['root']=encoder.value(forged_engine)
                payload['nodes']=encoder.nodes
                with self.assertRaisesRegex(ValueError,'held'):
                    Engine.import_state(self.r,json.loads(json.dumps(payload)))


if __name__=='__main__':unittest.main()
