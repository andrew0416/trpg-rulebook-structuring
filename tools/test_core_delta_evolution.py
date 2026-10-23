"""Delta Evolution through the real Mega, learned-move and equipment consumers."""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer
from ruleset import ExcludedRuleSelection
import test_category2_mega_forms as fixture
import state_grants as G,mega_forms as M,world_entities as W,items as I
import equipment_protection as PROTECTION,move_state as MOVES


class DeltaEvolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='playtest')
    add=fixture.MegaFormTests.add
    equip=fixture.MegaFormTests.equip
    turn=fixture.MegaFormTests.turn
    state=fixture.MegaFormTests.state
    valid=fixture.MegaFormTests.valid

    def reload(self):
        # The existing fixture reload hardcodes core. Preserve this actual
        # explicitly admitting profile; the codec must still reject mismatches.
        self.e.gm.restore(self.e.gm.snapshot());ids=(self.t.entity_id,self.p.entity_id)
        rules=Rules(str(ROOT),ruleset=self.e.r.ruleset.name)
        self.e=Engine.import_state(rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        index=W.actor_index(self.e);self.t,self.p=(index[uid] for uid in ids);self.valid()

    def setUp(self):
        self.e=Engine(self.r,seed=916)
        self.t=self.add(build_trainer(self.r,'Delta Trainer',30,
            {'hp':20,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},moves=[],abilities=[]))
        self.p=self.add(build_pokemon(self.r,'레쿠쟈',50,moves=['화룡점정'],abilities=[],
            extra={'trainer_id':self.t.entity_id},pos=(2,1)))
        self.equip(self.t,'ring','메가링')

    def activate(self,**options):
        return self.e.mega_evolve(self.t,self.p,'mega/레쿠쟈',ring='ring',**options)

    def test_actual_stoneless_activation_both_turns_exact_form_and_scene_restore(self):
        for payer in ('trainer','pokemon'):
            with self.subTest(payer=payer):
                if payer=='pokemon':self.setUp()
                actor=self.t if payer=='trainer' else self.p
                before=deepcopy(self.p.stats);types=list(self.p.types);hp=self.p.hp
                self.turn(actor);budget=actor.budget['swift'];out=self.activate(actor=actor)
                self.assertEqual(self.p.stats,{k:v+{'atk':3,'def':1,'spa':3,'spd':1,'spe':2}.get(k,0) for k,v in before.items()})
                self.assertEqual(self.p.types,types);self.assertEqual(self.p.hp,hp)
                self.assertIn('도주 [Playtest]',self.p.abilities);self.assertEqual(self.p.form,'mega/레쿠쟈')
                self.assertEqual(actor.budget['swift'],budget-1)
                self.assertIsNone(out['stone_instance']);self.assertIsNone(out['stone_registration'])
                self.assertEqual(out['stone_exception'],{'rule_id':M.DELTA,'move_id':self.r.move_id('화룡점정')})
                self.assertEqual(set(self.e._physical_objects),{'ring'})
                self.reload();self.e.end_scene();self.assertEqual(self.p.stats,before)
                self.assertEqual(self.p.types,types);self.assertNotIn('도주 [Playtest]',self.p.abilities)
                self.assertNotIn(M.KEY,self.p.spec);self.assertFalse(M.state(self.e)['uses']);self.valid()

    def test_current_learned_ownership_accepts_temporary_learning_and_hidden_baseline_not_permission_or_display(self):
        mid=self.r.move_id('화룡점정')
        for mode in ('available_only','raw_cache','display','permission','learned','hidden_baseline'):
            with self.subTest(mode=mode):
                self.setUp();self.e.gm.set_move(self.p,mid,add=False,reason='actual current move is forgotten')
                if mode=='raw_cache':self.p.moves.append(mid)
                elif mode=='display':G.overlay(self.p,'display:only',moves=[mid])
                elif mode in ('permission','learned'):
                    G.grant_moves(self.p,[mid],'sourced:'+mode,'fixture',lifetime='scene',mode=mode)
                elif mode=='hidden_baseline':
                    self.e.gm.set_move(self.p,mid,reason='actual learned move observed')
                    G.overlay(self.p,'display:hidden',moves=[])
                self.turn(self.t);before=self.state()
                if mode in ('learned','hidden_baseline'):
                    self.activate();self.valid()
                else:
                    with self.assertRaisesRegex(ValueError,'know Dragon Ascent'):self.activate()
                    self.assertEqual(self.state(),before)
                if mode=='learned':
                    self.assertIn(mid,MOVES.known(self.r,{'moves':MOVES.owned_list(self.p.spec,'moves')}))

    def test_learning_loss_after_activation_preserves_scene_then_requires_learning_next_scene(self):
        mid=self.r.move_id('화룡점정');self.turn(self.t);self.activate()
        self.e.gm.set_move(self.p,mid,add=False,reason='actual move forgotten after successful transformation')
        self.assertNotIn(mid,MOVES.known(self.r,{'moves':MOVES.owned_list(self.p.spec,'moves')}))
        self.assertEqual(self.p.form,'mega/레쿠쟈');self.reload()
        self.e.end_encounter();self.assertEqual(self.p.form,'mega/레쿠쟈')
        self.e.end_scene();self.turn(self.t);before=self.state()
        with self.assertRaisesRegex(ValueError,'know Dragon Ascent'):self.activate()
        self.assertEqual(self.state(),before)
        self.e.gm.set_move(self.p,mid,reason='actual move learned again');self.activate();self.valid()

    def test_delta_keeps_actual_ring_trainer_species_action_and_scene_quota(self):
        self.turn(self.t)
        other=self.add(build_trainer(self.r,'Other Trainer',30,
            {'hp':20,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},moves=[],abilities=[]))
        wrong_species=self.add(build_pokemon(self.r,'리자몽',40,moves=['화룡점정'],abilities=[],
            extra={'trainer_id':self.t.entity_id},pos=(4,1)))
        for trainer,pokemon,options in ((other,self.p,{}),(self.t,wrong_species,{}),(self.t,self.p,{'actor':self.p})):
            before=self.state()
            with self.assertRaises(ValueError):self.e.mega_evolve(trainer,pokemon,'mega/레쿠쟈',ring='ring',**options)
            self.assertEqual(self.state(),before)
        I.unregister_item(self.e,self.t,'메가링');before=self.state()
        with self.assertRaises(ValueError):self.activate()
        self.assertEqual(self.state(),before);I.register_item(self.e,self.t,'메가링',source_instance_id='ring')
        self.t.budget.update({'swift':0,'standard':0});before=self.state()
        with self.assertRaisesRegex(ValueError,'Swift'):self.activate()
        self.assertEqual(self.state(),before);self.turn(self.t);self.activate()
        second=self.add(build_pokemon(self.r,'레쿠쟈',50,name='Second Rayquaza',moves=['화룡점정'],abilities=[],
            extra={'trainer_id':self.t.entity_id},pos=(6,1)))
        self.turn(self.t);before=self.state()
        with self.assertRaisesRegex(ValueError,'Trainer already'):self.e.mega_evolve(self.t,second,'mega/레쿠쟈',ring='ring')
        self.assertEqual(self.state(),before);self.valid()

    def test_unrelated_held_item_is_not_a_stone_link_and_duplicate_ability_uses_existing_choice(self):
        self.equip(self.p,'independent-held','메가스톤')
        self.e.gm.set_ability(self.p,'도주 [Playtest]',reason='Rayquaza already learned its exact selected Run Away ability')
        self.turn(self.p);before=self.state()
        with self.assertRaisesRegex(ValueError,'duplicate Mega ability'):self.activate()
        self.assertEqual(self.state(),before)
        self.activate(stone='independent-held',replacement_ability='에어록')
        self.assertEqual(self.p.abilities.count('도주 [Playtest]'),1);self.assertIn('에어록',self.p.abilities)
        option=I.equipment_options(self.p,('held',))[0]
        self.assertNotEqual(PROTECTION.status(self.e,self.p,option,'drop')['status'],'blocked')
        I.unregister_item(self.e,self.p,'메가스톤');self.assertIsNone(self.p.item)
        I.unregister_item(self.e,self.t,'메가링');self.reload()
        self.assertEqual(self.p.form,'mega/레쿠쟈');self.e.end_scene()
        self.assertIn('도주 [Playtest]',self.p.abilities);self.assertNotIn('에어록',self.p.abilities);self.valid()

    def test_exact_source_and_exception_scope_reject_forged_forms_bindings_and_restore_links(self):
        self.turn(self.t);form=self.r.mega_form_policy['forms']['mega/레쿠쟈']
        self.equip(self.p,'not-a-delta-stone','메가스톤');before=self.state()
        with self.assertRaisesRegex(ValueError,'does not bind'):self.e.gm.bind_mega_stone('not-a-delta-stone','mega/레쿠쟈',reason='cannot invent a Delta Stone')
        self.assertEqual(self.state(),before)
        ordinary=self.r.mega_form_policy['forms']['mega/리자몽-x']
        for replacement in ({'id':'mega/forged'}, {'base_species':'pokemon/리자몽'}, {'origin':'custom'}):
            with self.subTest(replacement=replacement),patch.dict(form,replacement):
                with self.assertRaisesRegex(ValueError,'exact Rayquaza|custom Mega'):self.activate()
        with patch.dict(ordinary,{'stone_rules':[]}):
            with self.assertRaisesRegex(ValueError,'actual stone rules'):M.definition(self.e,'mega/리자몽-x')
        for reference in ('source_reference','learnset_reference','move_reference','ability_reference'):
            with self.subTest(reference=reference),patch.dict(form['stone_exception'][reference],{'sha256':'0'*64}):
                with self.assertRaisesRegex(ValueError,'source changed'):self.activate()
                self.assertEqual(self.state(),before)
        self.activate();snapshot=self.e.gm.snapshot()
        for key,value in (('stone_instance','not-a-delta-stone'),('stone_registration','not-a-delta-stone'),('stone_exception',None)):
            self.p.spec[M.KEY][key]=value
            with self.assertRaises(ValueError):self.e.export_state()
            self.e.gm.restore(snapshot)
        self.reload();self.valid()

    def test_core_profile_preserves_exact_playtest_ability_exclusion_without_spending(self):
        self.r=Rules(str(ROOT),ruleset='core');self.setUp();self.turn(self.t);before=self.state()
        self.assertEqual(self.r.mega_form_policy['forms']['mega/레쿠쟈']['ability'],'ability/도주-playtest')
        with self.assertRaises(ExcludedRuleSelection):self.activate()
        self.assertEqual(self.state(),before);self.assertNotIn(M.KEY,self.p.spec)
        self.assertEqual(self.r.ruleset.name,'core');self.valid()


if __name__=='__main__':unittest.main()
