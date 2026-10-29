"""C09-085 actual weapon/appendage identity, native damage and terminal use."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_cleanse_tags as _fixture_test_category2_cleanse_tags
from engine import Engine,Rules,Combatant
from grid import Grid
import cleanse_tags as TAG,optional_weapon_framework as FW,world_entities as W
import state_codec as CODEC,turn as TURN,weapon_actions as WA,body_state as BODY
import attack_damage_history as HISTORY,temporary_hp as TEMP


class WeaponTagTests(unittest.TestCase):
    actor=_fixture_test_category2_cleanse_tags.CleanseTagTests.actor
    craft=_fixture_test_category2_cleanse_tags.CleanseTagTests.craft
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def setUp(self):
        self.rules=Rules(str(ROOT),ruleset='core')
        self.weapon_declarations=[]
        _fixture_test_category2_cleanse_tags.CleanseTagTests.setUp(self)
        self.a.spec['skills']['전투']=6
        self.a.spec['moves']=['struggle','move/막치기','move/깨트리기','move/물대포','move/스피드스타']
        self.a.moves=list(self.a.spec['moves'])
        for c,pos,side in ((self.a,(2,2),'party'),(self.p,(3,2),'enemy'),(self.q,(3,3),'enemy')):
            c.pos=pos;c.side=side;c.spec.update(side=side,size='Medium',movement={'land':6})
        self.p.types=['고스트','강철'];self.q.types=['고스트']
        self.e.everyone=self.e.gm.everyone=[self.a,self.p,self.q]
        self.e.grid=Grid(20,20)
        self.craft()
    def weapon(self,uid='weapon:one',slot='주요손'):
        W.register_object(self.e,uid,location={'kind':'unknown'},reason='actual owned weapon',owner_id=self.a.entity_id)
        FW.observe_weapon(self.e,self.a,uid,name=uid,kind='소형 근접무기',grade='좋음',arcane=False,
            metal=True,moves=['move/으깨기'],reason='GM saw actual sword')
        key=FW.equip(self.e,self.a,uid,slot=slot)
        self.weapon_declarations.append(deepcopy(self.a.custom_conditions['equipped_weapons'][key]['weapon']))
        return key
    def attach(self,uid='weapon:one',tag='tag:one'):
        return TAG.observe_weapon(self.e,self.a,tag,event_id='attach:'+tag,weapon_id=uid,reason='actual paper stuck to weapon')
    def part(self,bearer=None):
        bearer=bearer or self.a
        BODY.observe_appendage(self.e,bearer,'actual:right-hand',reason='GM observed actual right hand')
        BODY.observe_appendage(self.e,bearer,'actual:left-hand',reason='GM observed actual left hand')
        return TAG.observe_appendage(self.e,self.a,'tag:one',bearer,'actual:right-hand',event_id='part',reason='paper stuck on right hand')
    def start(self,actor=None):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.a)
    def hit(self,move='struggle',target=None,**options):
        self.start()
        with patch.object(Engine,'accuracy_check',return_value=(True,12,False)):
            return self.e.use_move(self.a,target or self.p,move,set_damage=True,**options)
    def restore(self):
        # Save codec requires matching externally defined weapon Rules. Body
        # appendage state has no such definitions and uses ordinary fresh Rules.
        fresh=self.e.r if self.weapon_declarations else Rules(str(ROOT),ruleset='core')
        payload=CODEC.dump_engine(self.e)
        self.assertEqual(payload['rules'],CODEC.rules_fingerprint(fresh))
        self.e=CODEC.load_engine(fresh,payload)
        index=W.actor_index(self.e)
        self.a,self.p,self.q=(index[c.entity_id] for c in (self.a,self.p,self.q))
    def used(self):return self.e._physical_objects['tag:one'].get('destroyed')

    def test_weapon_normal_and_fighting_are_exact_regular_matchups_including_dual_ghost(self):
        for fighting in (False,True):
            with self.subTest(fighting=fighting):
                self.setUp();key=self.weapon();self.attach()
                move=key
                if fighting:self.a.registry.append(dict(type='type_override_moves',moves=[key],as_type='격투'))
                prepared=WA.prepare(self.e,self.a,self.rules.move(move),'weapon:one')
                self.p.types=[]
                expected=self.e.roll_damage(self.a,self.p,prepared,set_damage=True)
                self.p.types=['고스트','강철']
                hp=self.p.hp
                self.assertEqual(self.hit(move,weapon_id='weapon:one'),expected)
                self.assertEqual(hp-self.p.hp,expected)
                self.assertEqual(self.used()['cleanse_weapon_use']['weapon_id'],'weapon:one')
                self.assertEqual(HISTORY.amount(HISTORY.records(self.p)[-1]),expected)
                self.assertEqual(self.a.spec['items'][TAG.ITEM],0)

    def test_other_weapon_unarmed_type_and_ghost_trainer_never_spend_tag(self):
        key=self.weapon();self.weapon('weapon:two',slot='반대손');self.attach()
        other=next(k for k,v in self.a.custom_conditions['equipped_weapons'].items() if v['instance_id']=='weapon:two')
        self.assertEqual(self.hit(other,weapon_id='weapon:two'),0)
        self.assertEqual(self.hit('move/막치기'),0)
        self.hit('move/물대포')
        trainer=self.actor('ghost-trainer','trainer');trainer.types=['고스트'];trainer.side='enemy';trainer.pos=(3,2);trainer.spec['size']='Medium'
        self.e.gm.add_combatant(trainer)
        self.assertEqual(self.hit(key,target=trainer,weapon_id='weapon:one'),0)
        self.assertIsNone(self.used())

    def test_preview_miss_prevented_and_native_zero_damage_keep_same_tag(self):
        key=self.weapon();self.attach()
        move=WA.prepare(self.e,self.a,self.rules.move(key),'weapon:one')
        before=deepcopy(self.e._physical_objects['tag:one'])
        self.assertGreater(self.e.roll_damage(self.a,self.p,move,set_damage=True),0)
        self.assertEqual(before,self.e._physical_objects['tag:one'])
        self.start()
        with patch.object(Engine,'accuracy_check',return_value=(False,1,False)):
            self.assertEqual(self.e.use_move(self.a,self.p,key,weapon_id='weapon:one',set_damage=True),0)
        self.p.move_immune=[key]
        self.assertEqual(self.hit(key,weapon_id='weapon:one'),0)
        self.p.move_immune.remove(key)
        self.p.abilities=['불가사의부적'];self.e.register_abilities(self.p)
        self.assertEqual(self.hit(key,weapon_id='weapon:one'),0)
        self.p.abilities=[]
        self.e.rulings.add_situational('damage',-10000,who=self.a.name,reason='GM observed all damage prevented')
        self.assertEqual(self.hit(key,weapon_id='weapon:one'),0)
        self.assertIsNone(self.used())
        self.assertEqual(HISTORY.amount(HISTORY.records(self.p)[-1]),0)

    def test_temporary_hp_only_is_real_native_damage_and_consumes_once(self):
        key=self.weapon();self.attach();TEMP.grant(self.e,self.p,1000)
        hp=self.p.hp
        self.assertGreater(self.hit(key,weapon_id='weapon:one'),0)
        self.assertEqual(self.p.hp,hp)
        self.assertEqual(self.used()['cleanse_weapon_use']['receipt']['net_hp_loss'],0)
        self.assertGreater(self.used()['cleanse_weapon_use']['receipt']['net_temporary_hp_loss'],0)
        original=deepcopy(self.used())
        self.assertEqual(self.hit(key,weapon_id='weapon:one'),0)
        self.assertEqual(original,self.used())

    def test_appendage_native_selection_is_exact_and_other_part_cannot_borrow_it(self):
        self.part()
        self.assertEqual(self.hit(),0)
        self.assertEqual(self.hit(appendage_id='actual:left-hand'),0)
        self.assertIsNone(self.used())
        self.assertGreater(self.hit('move/깨트리기',appendage_id='actual:right-hand'),0)
        self.assertEqual(self.used()['cleanse_weapon_use']['appendage'],
            {'actor_id':self.a.entity_id,'appendage_id':'actual:right-hand'})

    def test_appendage_observation_and_weapon_mutual_exclusion_are_atomic(self):
        self.part();before=CODEC.dump_engine(self.e)
        with self.assertRaises(ValueError):self.e.use_move(self.a,self.p,'struggle',appendage_id='invented')
        self.assertEqual(before,CODEC.dump_engine(self.e))
        key=self.weapon();self.start();before=CODEC.dump_engine(self.e)
        with self.assertRaises(ValueError):self.e.use_move(self.a,self.p,key,weapon_id='weapon:one',appendage_id='actual:right-hand')
        self.assertEqual(before,CODEC.dump_engine(self.e))

    def test_both_restores_keep_live_and_spent_attachment_and_reject_forged_receipt(self):
        key=self.weapon();self.attach();self.e.gm.snapshot('attached')
        self.e.gm.restore('attached')
        self.restore();self.assertEqual(TAG.attached_weapon(self.e._physical_objects['tag:one']),'weapon:one')
        self.assertGreater(self.hit(key,weapon_id='weapon:one'),0)
        self.e.gm.snapshot('spent');self.e.gm.restore('spent');self.assertTrue(self.used());self.restore()
        self.assertTrue(self.e.validate_state()['valid'])
        use=self.e._physical_objects['tag:one'][TAG.WEAPON]['use']
        use['receipt']['net_hp_loss']+=1
        with self.assertRaises(ValueError):CODEC.dump_engine(self.e)

    def test_late_failure_rolls_back_damage_rng_action_and_same_body(self):
        key=self.weapon();self.attach();self.start()
        # Warm read-only policies before comparing state; source bytes are fixed.
        self.e.roll_damage(self.a,self.p,WA.prepare(self.e,self.a,self.rules.move(key),'weapon:one'),set_damage=True)
        before=CODEC.dump_engine(self.e);native=W.finish_physical_use
        def fail(*args,**kwargs):
            native(*args,**kwargs);raise RuntimeError('late terminal failure')
        with patch.object(Engine,'accuracy_check',return_value=(True,12,False)),patch.object(W,'finish_physical_use',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'late terminal'):
                self.e.use_move(self.a,self.p,key,weapon_id='weapon:one',set_damage=True)
        self.assertEqual(before,CODEC.dump_engine(self.e))

    def test_multiple_actual_tags_do_not_stack_base_multiplier_and_each_expires_on_damage(self):
        self.a.spec['frequency_state']['day']+=1;self.craft('two')
        key=self.weapon();self.attach();self.attach(tag='tag:two')
        self.hit(key,weapon_id='weapon:one')
        one=self.e._physical_objects['tag:one'];two=self.e._physical_objects['tag:two']
        self.assertEqual(one['destroyed']['cleanse_weapon_use']['history_sequence'],two['destroyed']['cleanse_weapon_use']['history_sequence'])
        self.assertEqual(one['destroyed']['cleanse_weapon_use']['receipt'],two['destroyed']['cleanse_weapon_use']['receipt'])

    def test_equipment_transfer_and_location_follow_original_attachment(self):
        key=self.weapon();self.attach()
        self.assertEqual(W.effective_location(self.e,self.e._physical_objects['tag:one']),W.location_of(self.a))
        TURN.unequip_weapon(self.e,self.a,key)
        self.assertEqual(TAG.attached_weapon(self.e._physical_objects['tag:one']),'weapon:one')
        other=self.actor('new-holder','trainer');other.spec.update(skills={'전투':6},size='Medium');other.pos=(5,5)
        self.e.gm.add_combatant(other)
        self.e._physical_objects['weapon:one']['owner_id']=other.entity_id
        key=FW.equip(self.e,other,'weapon:one')
        self.assertEqual(W.effective_location(self.e,self.e._physical_objects['tag:one']),W.location_of(other))
        self.restore();self.assertTrue(self.e.validate_state()['valid'])

    def test_separate_surface_stock_or_second_attachment_rejects_same_attached_body(self):
        self.weapon();self.attach();before=CODEC.dump_engine(self.e)
        with self.assertRaises(ValueError):W.require_physical_access(self.e._physical_objects['tag:one'])
        import items as ITEMS
        with self.assertRaises(ValueError):ITEMS.register_item(self.e,self.a,TAG.ITEM,source_instance_id='tag:one')
        with self.assertRaises(ValueError):self.e.gm.observe_cleanse_barrier('tag:one',event_id='surface',attached=False,reason='invalid double use')
        with self.assertRaises(ValueError):TAG.observe_weapon(self.e,self.a,'tag:one',event_id='second',weapon_id='weapon:one',reason='second attach')
        self.assertEqual(before,CODEC.dump_engine(self.e))

    def test_appendage_multiple_actual_recipients_spend_before_next_ghost_and_restore(self):
        self.part();self.restore();self.start();hp=(self.p.hp,self.q.hp)
        with patch.object(Engine,'accuracy_check',return_value=(True,12,False)):
            self.e.use_move_on(self.a,self.p,'move/스피드스타',self.e.everyone,
                appendage_id='actual:right-hand',aim=(3,2))
        self.assertLess(self.p.hp,hp[0]);self.assertEqual(self.q.hp,hp[1])
        self.assertTrue(self.used());self.restore();self.assertTrue(self.used())
        self.assertTrue(self.e.validate_state()['valid'])

    def test_actual_one_shot_fighting_type_is_not_recomputed_after_consumption(self):
        self.part();self.a.type_override_next='격투'
        self.assertGreater(self.hit(appendage_id='actual:right-hand'),0)
        self.assertEqual(self.used()['cleanse_weapon_use']['actual_type'],'격투')
        self.assertIsNone(self.a.type_override_next)

    def test_optional_physical_weapon_without_framework_rolls_back_terminal_failure(self):
        self.rules=Rules(str(ROOT),ruleset='all');self.setUp_optional()

    def test_intercept_resume_uses_actual_pokemon_recipient_not_original_ghost_flag(self):
        import passive_events as PE
        for original_ghost in (False,True):
            with self.subTest(original_ghost=original_ghost):
                self.setUp();self.part();self.p.types=['고스트'] if original_ghost else []
                self.q.types=[] if original_ghost else ['고스트'];self.q.pos=(3,5);self.q.spec['loyalty']=6
                self.e.watch_move_defense(self.p,[{'actor_id':self.q.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual ally intercept')
                self.start();hp=(self.p.hp,self.q.hp)
                with patch.object(Engine,'accuracy_check',return_value=(True,12,False)):
                    with self.assertRaises(PE.PassiveEventPending):
                        self.e.use_move(self.a,self.p,'move/막치기',appendage_id='actual:right-hand',set_damage=True)
                self.assertIsNone(self.used());event=self.e._passive_pending;self.restore()
                count=self.e._prepare_skill_roll(self.q,'육상')[-1]['dice_count']
                options={'path':[(3,5),(3,4),(3,3),(3,2)],'skill':'육상','mode':'land',
                    'shove_destination':[4,2],'roll_options':{'fixed':[6]*count}}
                self.e.choose_move_defense(event,self.q,use=True,options=options,reason='actual pending reaction')
                self.assertEqual(self.p.hp,hp[0]);self.assertLess(self.q.hp,hp[1])
                self.assertEqual(bool(self.used()),not original_ghost)
                if self.used():self.assertEqual(self.used()['cleanse_weapon_use']['target_id'],self.q.entity_id)

    def test_post_damage_pending_and_fresh_restore_never_repeat_same_consumption(self):
        import passive_events as PE
        self.part(self.q);self.q.moves=['struggle'];self.q.spec['moves']=['struggle']
        self.q.abilities=['자기과신'];self.e.register_abilities(self.q)
        self.q.side='party';self.p.hp=1;del self.p.side;self.p.spec.pop('side',None)
        self.e.grid=None  # Existing unknown-side passive boundary has no flanking map.
        self.start(self.q)
        with patch.object(Engine,'accuracy_check',return_value=(True,12,False)):
            with self.assertRaises(PE.PassiveEventPending):
                self.e.use_move(self.q,self.p,'struggle',appendage_id='actual:right-hand',set_damage=True)
        self.assertTrue(self.used());event=self.e._passive_pending;self.restore()
        before=(self.p.hp,deepcopy(self.q.move_uses),deepcopy(self.used()),self.e.rng.getstate())
        self.p.side='enemy';self.assertEqual(self.e.deliver_passive_event(event),'applied')
        self.assertEqual(before,(self.p.hp,self.q.move_uses,self.used(),self.e.rng.getstate()))
        self.assertEqual(self.e.deliver_passive_event(event),'already_delivered')

    def setUp_optional(self):
        # Same original maker/physical tag, selected all for the printed optional weapon.
        _fixture_test_category2_cleanse_tags.CleanseTagTests.setUp(self);self.weapon_declarations=[];self.a.spec['skills']['전투']=6
        self.e.grid=Grid(20,20)
        for c,pos in ((self.a,(2,2)),(self.p,(3,2)),(self.q,(4,2))):
            c.pos=pos;c.spec.update(size='Medium',movement={'land':6})
        self.a.side='party';self.p.side=self.q.side='enemy';self.p.types=['고스트']
        self.craft()
        import items as ITEMS
        uid='optional:glove';item='crafted_item/스톰-글러브'
        W.register_object(self.e,uid,kind='item_instance',item_rule_id=item,owner_id=self.a.entity_id,
            location={'kind':'unknown'},reason='actual crafted physical glove')
        ITEMS.register_item(self.e,self.a,item,source_instance_id=uid)
        key,entry=next((key,row) for key,row in self.a.custom_conditions['equipped_weapons'].items() if row['instance_id']==uid)
        self.assertNotIn('framework_instance',entry['weapon']);self.attach(uid);self.start()
        self.e.roll_damage(self.a,self.p,WA.prepare(self.e,self.a,self.rules.move(key),item),set_damage=True)
        before=CODEC.dump_engine(self.e);native=W.finish_physical_use
        def fail(*args,**kwargs):native(*args,**kwargs);raise RuntimeError('optional terminal failure')
        with patch.object(Engine,'accuracy_check',return_value=(True,12,False)),patch.object(W,'finish_physical_use',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'optional terminal'):
                self.e.use_move(self.a,self.p,key,weapon_id=item,set_damage=True)
        self.assertEqual(before,CODEC.dump_engine(self.e))
        with patch.object(Engine,'accuracy_check',return_value=(True,12,False)):
            self.assertGreater(self.e.use_move(self.a,self.p,key,weapon_id=item,set_damage=True),0)
        self.assertTrue(self.used())
        # A spent tag alone no longer expands the native atomic interest scope.
        @FW.atomic_move
        def observe(engine,actor):return getattr(engine,'_optional_weapon_atomic',False)
        self.assertFalse(observe(self.e,self.a))


if __name__=='__main__':unittest.main()
