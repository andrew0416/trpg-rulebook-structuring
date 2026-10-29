"""Category2 source-ownership tests; fixtures do not certify acquisition legality."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"engine"))
from engine import Rules,Engine,Combatant
from builder import build_trainer
import state_grants as G
import state_fields as F
import items as I


class StateGrantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(str(ROOT),ruleset="core")

    def setUp(self):
        self.e=Engine(self.rules)
        self.c=Combatant(self.rules,build_trainer(self.rules,"source-owner",10,
                         {"hp":10,"atk":10,"def":10,"spa":10,"spd":10,"spe":10},
                         abilities=[]))
        self.e.everyone=[self.c];self.e.gm.everyone=[self.c]

    def ability(self,*names):
        G.set_baseline(self.c,"abilities",list(names));G.reconcile(self.e,self.c)

    def item(self,name,effects):
        original=self.rules.item_effects
        def lookup(value):
            if value==name:return deepcopy(effects),{"id":"item/"+name,"category":"fixture","use":"held"}
            return original(value)
        with patch.object(self.rules,"item_effects",side_effect=lookup):
            I.register_item(self.e,self.c,name)
        return name

    def assert_generated_weapon_usable(self,engine,actor,mid):
        import state_codec as CODEC,world_entities as WORLD
        move=engine.r.move(mid)
        self.assertEqual(move['id'],mid)
        self.assertIsInstance(engine.r.move_mech(mid)[0],dict)
        self.assertEqual(engine.r._selected_rule(mid),mid)
        for mapping in (engine.r.moves,engine.r.moves_mech,engine.r.selection.units,
                        engine.r.selection.dependencies,engine.r._runtime_weapon_declarations):
            self.assertIn(mid,mapping)
        self.assertIn(mid,engine.r.selection.names[move['name']])
        self.assertIn(mid,actor.custom_conditions['equipped_weapons'])
        self.assertEqual(actor.moves.count(mid),1)
        restored=CODEC.load_engine(engine.r,json.loads(json.dumps(CODEC.dump_engine(engine))))
        holder=WORLD.actor_index(restored)[actor.entity_id]
        self.assertIn(mid,holder.custom_conditions['equipped_weapons'])
        self.assertEqual(restored.r.move(mid)['id'],mid)
        self.assertIsInstance(restored.r.move_mech(mid)[0],dict)

    def assert_generated_weapon_absent(self,mid,name):
        for mapping in (self.rules.moves,self.rules.moves_mech,self.rules.selection.units,
                        self.rules.selection.dependencies,self.rules._runtime_weapon_declarations):
            self.assertNotIn(mid,mapping)
        self.assertNotIn(mid,self.rules.selection.names.get(name+' 발버둥',[]))
        self.assertNotIn(mid,self.c.moves)
        self.assertNotIn(mid,self.c.custom_conditions.get('equipped_weapons',{}))

    def test_stale_transition_preserves_independent_native_weapon_publication(self):
        import turn as TURN
        self.e.gm.set_skill(self.c,'전투',4,reason='actual Adept weapon user')
        staged_weapon={'name':'v2-discarded-staged-weapon','kind':'대형 근접무기','grade':'좋음','moves':['백스윙']}
        live_weapon=dict(staged_weapon,name='v2-independent-live-weapon')
        observed={};before_hp=self.c.hp;before_rng=self.e.rng.getstate()
        def apply(staged,actor):
            actor.hp-=1;staged.rng.random()
            observed['discarded']=TURN.equip_weapon(staged,actor,staged_weapon)
            observed['live']=G.transition(self.e,self.c,
                lambda live,holder:TURN.equip_weapon(live,holder,live_weapon))
        with self.assertRaisesRegex(ValueError,'original world changed before commit'):
            G.transition(self.e,self.c,apply)
        self.assertEqual(self.c.hp,before_hp);self.assertEqual(self.e.rng.getstate(),before_rng)
        self.assert_generated_weapon_absent(observed['discarded'],staged_weapon['name'])
        self.assert_generated_weapon_usable(self.e,self.c,observed['live'])

    def test_stale_transition_preserves_independent_same_key_weapon_publication(self):
        import turn as TURN
        self.e.gm.set_skill(self.c,'전투',4,reason='actual Adept weapon user')
        weapon={'name':'v2-overlapping-native-weapon','kind':'대형 근접무기','grade':'좋음','moves':['백스윙']}
        observed={};before_hp=self.c.hp
        def apply(staged,actor):
            actor.hp-=1
            observed['staged']=TURN.equip_weapon(staged,actor,weapon)
            observed['live']=G.transition(self.e,self.c,
                lambda live,holder:TURN.equip_weapon(live,holder,weapon))
        with self.assertRaisesRegex(ValueError,'original world changed before commit'):
            G.transition(self.e,self.c,apply)
        self.assertEqual(observed['staged'],observed['live'])
        self.assertEqual(self.c.hp,before_hp)
        self.assert_generated_weapon_usable(self.e,self.c,observed['live'])

    def test_independent_weapon_same_title_does_not_keep_rejected_name_binding(self):
        import turn as TURN
        self.e.gm.set_skill(self.c,'전투',4,reason='actual Adept weapon user')
        staged_weapon={'name':'v2-same-display-title','kind':'대형 근접무기','grade':'좋음','moves':['백스윙']}
        live_weapon=dict(staged_weapon,grade='간단');observed={}
        def apply(staged,actor):
            observed['discarded']=TURN.equip_weapon(staged,actor,staged_weapon)
            observed['live']=G.transition(self.e,self.c,
                lambda live,holder:TURN.equip_weapon(live,holder,live_weapon))
        with self.assertRaisesRegex(ValueError,'original world changed before commit'):
            G.transition(self.e,self.c,apply)
        self.assertNotEqual(observed['discarded'],observed['live'])
        self.assert_generated_weapon_absent(observed['discarded'],staged_weapon['name'])
        self.assertEqual(self.rules.selection.names[live_weapon['name']+' 발버둥'],[observed['live']])
        self.assert_generated_weapon_usable(self.e,self.c,observed['live'])

    def test_failed_parent_removes_nested_staged_weapon_publication(self):
        import turn as TURN
        self.e.gm.set_skill(self.c,'전투',4,reason='actual Adept weapon user')
        weapon={'name':'v2-aborted-nested-weapon','kind':'대형 근접무기','grade':'좋음','moves':['백스윙']}
        observed={};before_hp=self.c.hp;before_rng=self.e.rng.getstate()
        def apply(staged,actor):
            actor.hp-=1;staged.rng.random()
            observed['id']=G.transition(staged,actor,
                lambda child,holder:TURN.equip_weapon(child,holder,weapon))
            raise ValueError('actual parent refuses after nested equip')
        with self.assertRaisesRegex(ValueError,'actual parent refuses'):
            G.transition(self.e,self.c,apply)
        self.assertEqual(self.c.hp,before_hp);self.assertEqual(self.e.rng.getstate(),before_rng)
        self.assert_generated_weapon_absent(observed['id'],weapon['name'])

    def test_successful_nested_staged_weapon_publication_survives_lookup_and_save(self):
        import turn as TURN
        self.e.gm.set_skill(self.c,'전투',4,reason='actual Adept weapon user')
        weapon={'name':'v2-successful-nested-weapon','kind':'대형 근접무기','grade':'좋음','moves':['백스윙']}
        before_hp=self.c.hp
        def apply(staged,actor):
            actor.hp-=1
            return G.transition(staged,actor,
                lambda child,holder:TURN.equip_weapon(child,holder,weapon))
        mid=G.transition(self.e,self.c,apply)
        self.assertEqual(self.c.hp,before_hp-1)
        self.assert_generated_weapon_usable(self.e,self.c,mid)

    def test_sibling_weapon_commit_survives_child_conflict_but_not_parent_abort(self):
        import turn as TURN
        for abort_parent in (False,True):
            with self.subTest(abort_parent=abort_parent):
                self.setUp();self.e.gm.set_skill(self.c,'전투',4,reason='actual Adept weapon user')
                weapon={'name':'v2-sibling-weapon-'+str(abort_parent),'kind':'대형 근접무기','grade':'좋음','moves':['백스윙']}
                observed={};before_hp=self.c.hp
                def parent(staged,actor):
                    def child(candidate,holder):
                        holder.hp-=1
                        observed['candidate']=TURN.equip_weapon(candidate,holder,weapon)
                        observed['id']=G.transition(staged,actor,
                            lambda sibling,user:TURN.equip_weapon(sibling,user,weapon))
                    with self.assertRaisesRegex(ValueError,'original world changed before commit'):
                        G.transition(staged,actor,child)
                    self.assertEqual(observed['candidate'],observed['id'])
                    self.assertIn(observed['id'],staged.r.moves)
                    if abort_parent:raise ValueError('outer parent refuses sibling equip')
                    return observed['id']
                if abort_parent:
                    with self.assertRaisesRegex(ValueError,'outer parent refuses'):
                        G.transition(self.e,self.c,parent)
                    self.assert_generated_weapon_absent(observed['id'],weapon['name'])
                else:
                    mid=G.transition(self.e,self.c,parent)
                    self.assert_generated_weapon_usable(self.e,self.c,mid)
                self.assertEqual(self.c.hp,before_hp)

    def generated_weapon_state(self,mid,name):
        mappings=(self.rules.moves,self.rules.moves_mech,self.rules.selection.units,
                  self.rules.selection.dependencies,self.rules._runtime_weapon_declarations)
        return deepcopy([(mid in mapping,mapping.get(mid)) for mapping in mappings]+
                        [(name+' 발버둥' in self.rules.selection.names,
                          self.rules.selection.names.get(name+' 발버둥'))])

    def test_independent_original_root_keeps_its_normal_staged_weapon_child(self):
        import turn as TURN
        self.e.gm.set_skill(self.c,'전투',4,reason='actual Adept weapon user')
        weapon={'name':'v2-independent-root-normal-child','kind':'대형 근접무기','grade':'좋음','moves':['백스윙']}
        observed={};before_hp=self.c.hp
        def outer(staged,actor):
            actor.hp-=1
            def independent(live,holder):
                return G.transition(live,holder,
                    lambda child,user:TURN.equip_weapon(child,user,weapon))
            observed['id']=G.transition(self.e,self.c,independent)
        with self.assertRaisesRegex(ValueError,'original world changed before commit'):
            G.transition(self.e,self.c,outer)
        self.assertEqual(self.c.hp,before_hp)
        self.assert_generated_weapon_usable(self.e,self.c,observed['id'])

    def test_cross_root_return_refuses_weapon_publication_before_actor_rules_or_rng_change(self):
        import turn as TURN
        for abort_parent in (False,True):
            with self.subTest(abort_parent=abort_parent):
                self.setUp();self.e.gm.set_skill(self.c,'전투',4,reason='actual Adept weapon user')
                weapon={'name':'v2-cross-root-refusal-'+str(abort_parent),'kind':'대형 근접무기','grade':'좋음','moves':['백스윙']}
                observed={};before_hp=self.c.hp;before_rng=self.e.rng.getstate()
                def outer(staged,actor):
                    def independent(candidate,holder):
                        observed['id']=TURN.equip_weapon(candidate,holder,weapon)
                        rules_before=self.generated_weapon_state(observed['id'],weapon['name'])
                        actor_before=(actor.hp,list(actor.moves),deepcopy(actor.custom_conditions),staged.rng.getstate())
                        def crossing(branch,user):
                            user.hp-=1;branch.rng.random()
                            return TURN.equip_weapon(branch,user,weapon)
                        with self.assertRaisesRegex(ValueError,'suspended nonancestor graph'):
                            G.transition(staged,actor,crossing)
                        self.assertEqual(self.generated_weapon_state(observed['id'],weapon['name']),rules_before)
                        self.assertEqual((actor.hp,actor.moves,actor.custom_conditions,staged.rng.getstate()),actor_before)
                        raise ValueError('independent tentative root aborts')
                    with self.assertRaisesRegex(ValueError,'independent tentative root aborts'):
                        G.transition(self.e,self.c,independent)
                    self.assert_generated_weapon_absent(observed['id'],weapon['name'])
                    if abort_parent:raise ValueError('suspended parent also aborts')
                if abort_parent:
                    with self.assertRaisesRegex(ValueError,'suspended parent also aborts'):
                        G.transition(self.e,self.c,outer)
                else:G.transition(self.e,self.c,outer)
                self.assertEqual(self.c.hp,before_hp);self.assertEqual(self.e.rng.getstate(),before_rng)
                self.assert_generated_weapon_absent(observed['id'],weapon['name'])

    def test_same_root_cousin_return_refuses_publication_without_orphan(self):
        import turn as TURN
        self.e.gm.set_skill(self.c,'전투',4,reason='actual Adept weapon user')
        weapon={'name':'v2-cousin-return-refusal','kind':'대형 근접무기','grade':'좋음','moves':['백스윙']}
        observed={};before_hp=self.c.hp;before_rng=self.e.rng.getstate()
        def outer(staged,actor):
            def first(branch,user):
                def sibling(candidate,holder):
                    observed['id']=TURN.equip_weapon(candidate,holder,weapon)
                    rules_before=self.generated_weapon_state(observed['id'],weapon['name'])
                    actor_before=(user.hp,list(user.moves),deepcopy(user.custom_conditions),branch.rng.getstate())
                    def crossing(child,subject):
                        subject.hp-=1;child.rng.random()
                        return TURN.equip_weapon(child,subject,weapon)
                    with self.assertRaisesRegex(ValueError,'suspended nonancestor graph'):
                        G.transition(branch,user,crossing)
                    self.assertEqual(self.generated_weapon_state(observed['id'],weapon['name']),rules_before)
                    self.assertEqual((user.hp,user.moves,user.custom_conditions,branch.rng.getstate()),actor_before)
                    raise ValueError('tentative sibling aborts')
                with self.assertRaisesRegex(ValueError,'tentative sibling aborts'):
                    G.transition(staged,actor,sibling)
            G.transition(staged,actor,first)
        G.transition(self.e,self.c,outer)
        self.assertEqual(self.c.hp,before_hp);self.assertEqual(self.e.rng.getstate(),before_rng)
        self.assert_generated_weapon_absent(observed['id'],weapon['name'])

    def test_failed_child_publication_is_not_promoted_by_successful_independent_parent(self):
        import turn as TURN
        self.e.gm.set_skill(self.c,'전투',4,reason='actual Adept weapon user')
        weapon={'name':'v2-failed-child-not-a-claim','kind':'대형 근접무기','grade':'좋음','moves':['백스윙']}
        observed={};before_hp=self.c.hp;before_rng=self.e.rng.getstate()
        def outer(staged,actor):
            observed['outer']=TURN.equip_weapon(staged,actor,weapon)
            def independent(candidate,holder):
                def failing_child(child,user):
                    observed['child']=TURN.equip_weapon(child,user,weapon)
                    raise ValueError('child equip is refused')
                with self.assertRaisesRegex(ValueError,'child equip is refused'):
                    G.transition(candidate,holder,failing_child)
                self.assertNotIn(observed['child'],holder.custom_conditions.get('equipped_weapons',{}))
            G.transition(self.e,self.c,independent)
            self.assertEqual(observed['outer'],observed['child'])
            raise ValueError('outer staged equip also aborts')
        with self.assertRaisesRegex(ValueError,'outer staged equip also aborts'):
            G.transition(self.e,self.c,outer)
        self.assertEqual(self.c.hp,before_hp);self.assertEqual(self.e.rng.getstate(),before_rng)
        self.assert_generated_weapon_absent(observed['outer'],weapon['name'])

    def test_stale_transition_preserves_external_gm_skill_and_rejects_staged_cost(self):
        import skill_modifiers as SK
        self.e.gm.set_skill(self.c,'육상',3,reason='initial actual skill')
        original_spec=self.c.spec;before_hp=self.c.hp;before_rng=self.e.rng.getstate()
        def apply(staged,actor):
            actor.hp-=1;staged.rng.random()
            self.e.gm.set_skill(self.c,'육상',4,reason='separately authorized live GM correction')
            return 'must not publish stale candidate'
        with self.assertRaisesRegex(ValueError,'original world changed before commit'):
            G.transition(self.e,self.c,apply)
        self.assertIs(self.c.spec,original_spec)
        self.assertEqual(SK.rank(self.e.r,self.c,'육상')[2],4)
        self.assertEqual(self.c.hp,before_hp)
        self.assertEqual(self.e.rng.getstate(),before_rng)

    def test_stale_transition_preserves_external_weather_and_rng_observation(self):
        before_hp=self.c.hp;observed={}
        def apply(staged,actor):
            actor.hp-=1;staged.rng.random()
            self.e.gm.set_weather('비',rounds=3,reason='separately authorized observed weather')
            self.e.rng.random();observed['rng']=self.e.rng.getstate()
        with self.assertRaisesRegex(ValueError,'original world changed before commit'):
            G.transition(self.e,self.c,apply)
        self.assertEqual(self.e.weather,'rain')
        self.assertEqual(self.c.hp,before_hp)
        self.assertEqual(self.e.rng.getstate(),observed['rng'])

    def test_nested_staged_transition_with_gm_correction_still_commits_once(self):
        import skill_modifiers as SK
        self.e.gm.set_skill(self.c,'육상',3,reason='initial actual skill')
        original_spec=self.c.spec;before_hp=self.c.hp
        def apply(staged,actor):
            staged.gm.set_skill(actor,'육상',4,reason='authorized correction within staged action')
            def nested(inner,subject):
                subject.hp-=1
                return subject
            return G.transition(staged,actor,nested)
        result=G.transition(self.e,self.c,apply)
        self.assertIs(result,self.c);self.assertIs(self.c.spec,original_spec)
        self.assertEqual(SK.rank(self.e.r,self.c,'육상')[2],4)
        self.assertEqual(self.c.hp,before_hp-1)

    def test_transition_replacement_splits_actor_and_engine_shared_container(self):
        shared={'value':1}
        self.c.shared_probe=shared
        self.e._source_policy_executions=shared
        def apply(e,c):
            c.shared_probe={'value':2}
            e._source_policy_executions['value']=3
            return c.shared_probe,e._source_policy_executions
        result=G.transition(self.e,self.c,apply)
        self.assertEqual(self.c.shared_probe,{'value':2})
        self.assertEqual(shared,{'value':3})
        self.assertIs(self.e._source_policy_executions,shared)
        self.assertIsNot(self.c.shared_probe,shared)
        self.assertIs(result[0],self.c.shared_probe);self.assertIs(result[1],shared)

    def test_transition_commits_engine_registry_deletion_and_keeps_surviving_alias(self):
        shared={'entry':1};self.e._source_policy_executions=shared
        self.c.retained=shared
        untouched=self.e.r
        def apply(e,c):
            del e._source_policy_executions
            c.retained['entry']=2
        G.transition(self.e,self.c,apply)
        self.assertFalse(hasattr(self.e,'_source_policy_executions'))
        self.assertIs(self.c.retained,shared);self.assertEqual(shared,{'entry':2})
        self.assertIs(self.e.r,untouched)

    def test_transition_rejects_duplicate_actor_before_callback(self):
        duplicate=deepcopy(self.c);calls=[]
        before=self.c.hp,self.e.rng.getstate()
        with self.assertRaisesRegex(ValueError,'distinct actors share identity'):
            G.transition(self.e,self.c,lambda *args:calls.append(True),participants=(duplicate,))
        self.assertEqual(calls,[]);self.assertEqual(before,(self.c.hp,self.e.rng.getstate()))

    def test_invalid_result_identity_rolls_back_deletion_cost_and_rng(self):
        self.e._source_policy_executions={'entry':1}
        before=deepcopy(self.c.spec),self.c.hp,self.e.rng.getstate()
        def apply(e,c):
            del e._source_policy_executions
            c.hp-=1;e.rng.random();c.spec['id']='changed identity'
        with self.assertRaisesRegex(ValueError,'identity'):
            G.transition(self.e,self.c,apply)
        self.assertEqual(before,(self.c.spec,self.c.hp,self.e.rng.getstate()))
        self.assertEqual(self.e._source_policy_executions,{'entry':1})

    def test_cross_store_identity_collision_is_rejected_before_callback(self):
        self.e._physical_objects={self.c.entity_id:{'id':self.c.entity_id,'kind':'physical_object'}}
        calls=[]
        with self.assertRaisesRegex(ValueError,'collides'):
            G.transition(self.e,self.c,lambda *args:calls.append(True))
        self.assertEqual(calls,[])

    def test_invalid_object_result_rolls_back_cost_rng_logs_and_registry(self):
        self.e._physical_objects={'object/kept':{'id':'object/kept','kind':'physical_object'}}
        registry=self.e._physical_objects;kept=registry['object/kept']
        before=(self.c.hp,self.e.rng.getstate(),deepcopy(self.e.log_lines),deepcopy(registry))
        def apply(e,c):
            c.hp-=1;e.rng.random();e.log_lines.append('staged effect')
            e._physical_objects['object/kept']['changed']=True
            e._physical_objects[c.entity_id]={'id':c.entity_id,'kind':'physical_object'}
        with self.assertRaisesRegex(ValueError,'collides'):
            G.transition(self.e,self.c,apply)
        self.assertEqual((self.c.hp,self.e.rng.getstate(),self.e.log_lines,registry),before)
        self.assertIs(self.e._physical_objects,registry)
        self.assertIs(registry['object/kept'],kept)

    def test_transition_repeated_generator_participant_is_one_live_actor(self):
        def apply(e,c,other):
            self.assertIs(c,other);c.hp-=1
            return other
        before=self.c.hp
        result=G.transition(self.e,self.c,apply,participants=(x for x in [self.c]))
        self.assertIs(result,self.c);self.assertEqual(self.c.hp,before-1)

    def test_native_ability_registers_only_once(self):
        self.ability("복안")
        self.e.register_abilities_one(self.c,"복안")
        self.e.register_abilities(self.c)
        self.assertEqual(self.c.accuracy_stage,3)
        self.assertEqual(len(G.state(self.c)["ability_receipts"]),1)

    def test_last_native_ability_removal_removes_passive(self):
        self.ability("복안");self.ability()
        self.assertEqual(self.c.accuracy_stage,0)
        self.assertEqual(self.c._passive_acc,0)
        self.assertFalse(G.state(self.c)["ability_receipts"])

    def test_equipment_duplicate_of_permanent_ability_has_one_effect(self):
        self.ability("복안")
        self.item("grant-glasses",[{"type":"grant_ability","grant_ability":"복안"}])
        self.assertEqual(self.c.abilities.count("복안"),1)
        self.assertEqual(self.c.accuracy_stage,3)
        I.unregister_item(self.e,self.c,"grant-glasses")
        self.assertIn("복안",self.c.abilities)
        self.assertEqual(self.c.accuracy_stage,3)

    def test_permanent_acquisition_after_item_survives_unequip(self):
        self.item("grant-glasses",[{"type":"grant_ability","grant_ability":"복안"}])
        self.ability("복안")
        I.unregister_item(self.e,self.c,"grant-glasses")
        self.assertEqual(self.c.accuracy_stage,3)
        self.ability()
        self.assertEqual(self.c.accuracy_stage,0)

    def test_independent_move_after_equipment_grant_survives(self):
        self.item("grant-move",[{"type":"grant_move","moves":["몸통박치기"]}])
        mid=self.rules.move_id("몸통박치기")
        self.assertIn(mid,self.c.moves)
        G.set_baseline(self.c,"moves",list(self.c.spec["moves"])+[mid])
        I.unregister_item(self.e,self.c,"grant-move")
        self.assertIn(mid,self.c.moves)

    def test_two_equipment_ability_sources_remove_only_last(self):
        for name in ("a","b"):self.item(name,[{"type":"grant_ability","grant_ability":"복안"}])
        self.assertEqual(self.c.accuracy_stage,3)
        I.unregister_item(self.e,self.c,"a")
        self.assertEqual(self.c.accuracy_stage,3)
        I.unregister_item(self.e,self.c,"b")
        self.assertEqual(self.c.accuracy_stage,0)

    def test_two_equipment_immunity_sources_overlap(self):
        for name in ("a","b"):self.item(name,[{"type":"immunity","status":["독"]}])
        I.unregister_item(self.e,self.c,"a")
        self.assertIn("독",self.c.status_immune)
        I.unregister_item(self.e,self.c,"b")
        self.assertNotIn("독",self.c.status_immune)

    def test_two_native_immunity_sources_overlap(self):
        self.ability("클리어바디","하얀연기")
        self.assertIn("all",self.c.stage_loss_immune)
        self.ability("하얀연기")
        self.assertIn("all",self.c.stage_loss_immune)
        self.ability()
        self.assertNotIn("all",self.c.stage_loss_immune)

    def test_capped_sources_use_declared_contributions_not_observed_deltas(self):
        for name in ("a","b"):self.item(name,[{"type":"accuracy_mod","value":5}])
        self.assertEqual(self.c.accuracy_stage,6)
        I.unregister_item(self.e,self.c,"a")
        self.assertEqual(self.c.accuracy_stage,5)
        I.unregister_item(self.e,self.c,"b")
        self.assertEqual(self.c.accuracy_stage,0)

    def test_negative_capped_sources_are_reversible(self):
        for name in ("a","b"):self.item(name,[{"type":"evasion_mod","value":-5}])
        self.assertEqual(self.c.evasion_mod,-6)
        I.unregister_item(self.e,self.c,"a")
        self.assertEqual(self.c.evasion_mod,-5)
        I.unregister_item(self.e,self.c,"b")
        self.assertEqual(self.c.evasion_mod,0)

    def test_base_stat_change_preserves_equipment_then_unequip_preserves_base(self):
        self.item("stats",[{"type":"stat_base_mod","stat":"atk","value":3}])
        new=dict(self.c.spec["stats"]);new["atk"]=11
        F.base_patch(self.c,{"stats":new},reason="verified permanent adjustment",source="gm/state")
        self.assertEqual(self.c.stats["atk"],14)
        self.assertEqual(self.c.spec["stats"]["atk"],11)
        I.unregister_item(self.e,self.c,"stats")
        self.assertEqual(self.c.stats["atk"],11)

    def test_stage_sources_remain_correct_at_six(self):
        for name in ("a","b"):self.item(name,[{"type":"stage_change","stat":"atk","delta":5,"base":True}])
        self.assertEqual(self.c.stages["atk"],6)
        I.unregister_item(self.e,self.c,"a")
        self.assertEqual(self.c.stages["atk"],5)
        I.unregister_item(self.e,self.c,"b")
        self.assertEqual(self.c.stages["atk"],0)

    def test_snapshot_restores_ability_receipts_without_reregistering(self):
        self.item("glasses",[{"type":"grant_ability","grant_ability":"복안"}])
        self.e.gm.snapshot("equipped")
        I.unregister_item(self.e,self.c,"glasses")
        for _ in range(2):
            self.e.gm.restore("equipped",reason="source receipt round trip")
            self.e.register_abilities_one(self.c,"복안")
            self.assertEqual(self.c.accuracy_stage,3)
            I.unregister_item(self.e,self.c,"glasses")
            self.assertEqual(self.c.accuracy_stage,0)

    def test_grant_records_are_json_data(self):
        self.item("glasses",[{"type":"grant_ability","grant_ability":"복안"}])
        self.assertEqual(json.loads(json.dumps(self.c.spec[G.KEY],ensure_ascii=False)),self.c.spec[G.KEY])

    def test_same_source_provenance_collision_is_rejected(self):
        G.grant(self.c,"moves","move/몸통박치기","source","item",owner_id="a")
        before=deepcopy(self.c.spec)
        with self.assertRaises(ValueError):
            G.grant(self.c,"moves","move/울음소리","source","feat",owner_id="a")
        self.assertEqual(self.c.spec,before)

    def test_owner_revoke_refunds_known_cost_once_and_keeps_independent_grant(self):
        self.c.spec["tutor_points"]=2
        G.grant(self.c,"moves","move/몸통박치기","mentor","feat",owner_id="old",lifetime="your_pokemon",tutor_points=2)
        G.grant(self.c,"moves","move/몸통박치기","independent","gm")
        before=deepcopy(self.c.spec)
        plan=G.preview_owner_revoke(self.c,"old")
        self.assertEqual(self.c.spec,before)
        self.assertEqual(plan["tutor_points_refunded"],2)
        G.revoke_owner(self.e,self.c,"old","trade")
        self.assertIn("move/몸통박치기",self.c.moves)
        self.assertEqual(self.c.spec["tutor_points"],4)
        G.revoke_owner(self.e,self.c,"old","same trade retry")
        self.assertEqual(self.c.spec["tutor_points"],4)

    def test_owner_preview_on_legacy_actor_is_read_only(self):
        before=deepcopy(self.c.spec)
        self.assertEqual(G.preview_owner_revoke(self.c,"old")["sources"],[])
        self.assertEqual(self.c.spec,before)

    def test_invalid_bounded_external_mutation_rejects_before_unequip(self):
        self.item("a",[{"type":"accuracy_mod","value":5}])
        self.c.accuracy_stage=1
        before=deepcopy((self.c.spec,self.c._item_reg,self.c.accuracy_stage))
        with self.assertRaises(ValueError):I.unregister_item(self.e,self.c,"a")
        self.assertEqual((self.c.spec,self.c._item_reg,self.c.accuracy_stage),before)

    def test_recorded_bounded_combat_change_keeps_source_identity(self):
        self.item("a",[{"type":"accuracy_mod","value":5}])
        self.assertTrue(G.adjust_numeric(self.c,"accuracy_stage",-2))
        self.assertEqual(self.c.accuracy_stage,3)
        I.unregister_item(self.e,self.c,"a")
        self.assertEqual(self.c.accuracy_stage,-2)

    def test_weapon_removal_keeps_alias_baseline_after_canonical_materialization(self):
        import turn as TURN
        actor = Combatant(self.rules, build_trainer(self.rules, 'alias-baseline-weapon-owner', 10,
            dict(self.c.spec['stats']), moves=['백스윙'], skills={'전투':4}, abilities=[]))
        self.e.everyone = self.e.gm.everyone = [actor]
        key = TURN.equip_weapon(self.e, actor,
            {'name':'alias-baseline-weapon', 'kind':'대형 근접무기', 'grade':'좋음', 'moves':['백스윙']})
        self.assertNotIn('move/백스윙', actor.custom_conditions['equipped_weapons'][key]['independently_known'])
        original = list(actor.spec['moves'])
        G.materialize(actor, 'moves')
        self.assertEqual(actor.moves.count('move/백스윙'), 1)
        TURN.unequip_weapon(self.e, actor, key)
        self.assertEqual(actor.spec['moves'], original)
        self.assertIn('move/백스윙', actor.moves)
        self.assertNotIn(key, actor.moves)

    def test_invalid_move_overlay_rejects_before_any_field_or_ledger_mutation(self):
        G.overlay(self.c, 'existing-overlay', moves=['move/방어'])
        original_spec = self.c.spec
        before = deepcopy((self.c.spec, self.c.moves, self.c.abilities, self.c.registry))
        for source in ('existing-overlay', 'new-invalid-overlay'):
            for values in (['몸통박치기','move/몸통박치기'],
                           ['move/몸통박치기','move/몸통박치기'], ['move/not-registered']):
                with self.subTest(source=source, values=values):
                    with self.assertRaisesRegex(ValueError, 'distinct selected known moves'):
                        G.overlay(self.c, source, abilities=['복안'], moves=values)
                    self.assertIs(self.c.spec, original_spec)
                    self.assertEqual((self.c.spec, self.c.moves, self.c.abilities, self.c.registry), before)
        G.revoke(self.c, 'existing-overlay', engine=self.e)
        self.assertEqual(self.c.moves, self.c.spec['moves'])

    def test_runtime_overlay_never_rewrites_permanent_moves(self):
        base=list(self.c.spec["moves"])
        G.overlay(self.c,"transform",moves=["move/방어"])
        self.assertEqual(self.c.moves,["move/방어"])
        self.assertEqual(self.c.spec["moves"],base)
        G.revoke(self.c,"transform",engine=self.e)
        self.assertEqual(self.c.moves,base)

    def test_baseline_update_preserves_unrelated_legacy_live_grants(self):
        self.c.moves.append("move/몸통박치기")
        G.set_baseline(self.c,"moves",self.c.spec["moves"]+["move/튀어오르기"])
        self.assertIn("move/몸통박치기",self.c.moves)
        self.assertNotIn("move/몸통박치기",self.c.spec["moves"])
        G.set_baseline(self.c,"moves",self.c.spec["moves"])
        self.assertIn("move/몸통박치기",self.c.moves)

    def test_feature_and_item_overlap_then_owner_removal(self):
        self.item("grant-glasses",[{"type":"grant_ability","grant_ability":"복안"}])
        owner=Combatant(self.rules,build_trainer(self.rules,"teacher",5,dict(self.c.spec["stats"])))
        G.register_feature_effect(self.e,owner,self.c,"fixture","feat/fixture",0,{"type":"grant_ability","grant_ability":"복안"})
        I.unregister_item(self.e,self.c,"grant-glasses")
        self.assertEqual(self.c.accuracy_stage,3)
        G.revoke_owner(self.e,self.c,owner.spec["id"],"transfer")
        self.assertEqual(self.c.accuracy_stage,0)

    def test_feature_static_repeated_registration_is_idempotent(self):
        effect={"type":"stat_base_mod","stat":"atk","value":3}
        for _ in range(2):G.register_feature_effect(self.e,self.c,self.c,"fixture","feat/fixture",0,effect)
        self.assertEqual(self.c.stats["atk"],13)
        key="feature:"+self.c.spec["id"]+":feat/fixture"
        G.revoke(self.c,key,engine=self.e)
        self.assertEqual(self.c.stats["atk"],10)

    def test_ability_replacement_overlay_survives_permanent_acquisition(self):
        import effects as FX
        self.ability("복안")
        FX.h_ability_change(self.e,self.c,self.c,{"set_ability":"괴력집게"},{"source_id":"move/test","effect_occurrence":"one"})
        self.assertEqual(self.c.accuracy_stage,0)
        G.set_baseline(self.c,"abilities",["복안","하얀연기"]);G.reconcile(self.e,self.c)
        self.assertEqual(self.c.abilities,["괴력집게"])
        key=next(iter(G.state(self.c)["overlays"]))
        G.revoke(self.c,key,engine=self.e)
        self.assertIn("복안",self.c.abilities);self.assertIn("하얀연기",self.c.abilities)
        self.assertEqual(self.c.accuracy_stage,3)

    def test_transform_preserves_type_weight_and_move_baseline(self):
        import effects_ext as X
        self.c.spec["weight_class"]=4
        target=Combatant(self.rules,build_trainer(self.rules,"copy-target",5,dict(self.c.spec["stats"]),abilities=["복안"],extra={"weight_class":2,"types":["물"]}))
        original=deepcopy({k:self.c.spec.get(k) for k in ("moves","abilities","types","weight_class")})
        X.h_transform(self.e,self.c,target,{},{"source_id":"move/변신","effect_occurrence":"transform-one"})
        self.assertEqual(self.c.types,["물"]);self.assertEqual(self.c.weight_class,2)
        self.assertEqual({k:self.c.spec.get(k) for k in original},original)
        key=self.c.custom_conditions["transformed"]["source"]
        G.revoke(self.c,key,engine=self.e)
        self.assertEqual(self.c.weight_class,4)
        self.assertEqual(self.c.types,[])
        self.assertEqual(self.c.accuracy_stage,0)

    def test_unknown_item_replacement_preserves_old_source_and_rng(self):
        self.c.item="선제공격손톱";I.register_item(self.e,self.c)
        old=(self.c.item,self.c.initiative_bonus,deepcopy(self.c.spec),self.e.rng.getstate(),list(self.e.log_lines))
        with self.assertRaises(ValueError):I.replace_item(self.e,self.c,"definitely-unknown-item")
        self.assertEqual((self.c.item,self.c.initiative_bonus,self.c.spec,self.e.rng.getstate(),self.e.log_lines),old)

    def test_successful_item_replacement_preserves_actor_and_registry_identity(self):
        self.c.item="선제공격손톱";I.register_item(self.e,self.c)
        original=self.c
        result=I.replace_item(self.e,self.c,"예리한손톱")
        self.assertTrue(result["changed"])
        self.assertIs(self.e.everyone[0],original)
        self.assertIs(self.e.gm.everyone[0],original)
        self.assertEqual(self.c.item,"예리한손톱")
        self.assertEqual(self.c.initiative_bonus,0)
        self.assertTrue(any(row.get("type")=="crit_range" for row in self.c.modifiers))
        I.unregister_item(self.e,self.c)
        self.assertFalse(any(row.get("type")=="crit_range" for row in self.c.modifiers))

    def test_source_owned_accuracy_change_and_reset_follow_native_effect_path(self):
        import effects as FX
        self.ability("복안")
        FX.h_accuracy_mod(self.e,self.c,self.c,{"target":"self","value":-2},{})
        self.assertEqual(self.c.accuracy_stage,1)
        G.reset_numeric(self.c,"accuracy_stage")
        self.assertEqual(self.c.accuracy_stage,3)


    def test_unknown_weight_accepts_known_replacement_and_restores_without_inventing_base(self):
        import state_codec as CODEC,world_entities as WORLD
        self.assertIsNone(self.c.weight_class);self.assertNotIn('weight_class',self.c.spec)
        def apply(source,value,mode='set'):
            def change(e,actor):
                G._source(actor,source,'effect')
                G.weight(actor,value,source,mode=mode)
            return G.transition(self.e,self.c,change)
        before=self.e.export_state()
        for value,mode in ((1,'add'),(True,'set'),(2.0,'set')):
            with self.subTest(value=value,mode=mode):
                with self.assertRaises(ValueError):apply('fixture:invalid-weight',value,mode)
                self.assertEqual(self.e.export_state(),before)
        for invalid_base in (True,2.0,'unknown'):
            with self.subTest(invalid_base=invalid_base):
                with self.assertRaisesRegex(ValueError,'known base weight'):
                    G._weight_value({'base':invalid_base,'sources':{'copy':{'mode':'set','value':3,'minimum':1}}},None)
        with self.assertRaisesRegex(ValueError,'known base weight'):
            G._weight_value({'base':None,'sources':{'first':{'mode':'add','value':1,'minimum':1},
                                                    'later':{'mode':'set','value':3,'minimum':1}}},None)
        apply('fixture:known-weight-copy',3)
        apply('fixture:later-weight',1,'add')
        self.assertEqual(self.c.weight_class,4);self.assertNotIn('weight_class',self.c.spec)
        paid=self.e.export_state()
        with self.assertRaisesRegex(ValueError,'identity collision'):apply('fixture:known-weight-copy',4)
        with self.assertRaisesRegex(ValueError,'known base weight'):
            G.transition(self.e,self.c,lambda e,c:G.revoke(c,'fixture:known-weight-copy',engine=e))
        self.assertEqual(self.e.export_state(),paid)
        saved=self.e.gm.snapshot('known-replacement');self.e.gm.restore(saved)
        loaded=CODEC.load_engine(self.rules,self.e.export_state())
        restored=WORLD.actor_index(loaded)[self.c.entity_id]
        for engine,actor in ((self.e,self.c),(loaded,restored)):
            self.assertEqual(actor.weight_class,4)
            for source in ('fixture:later-weight','fixture:known-weight-copy'):
                G.transition(engine,actor,lambda e,c,source=source:G.revoke(c,source,engine=e))
            self.assertIsNone(actor.weight_class);self.assertNotIn('weight_class',actor.spec)

    def test_weight_contributions_recompute_after_each_source_ends(self):
        import effects as FX
        self.c.spec["weight_class"]=4
        for source in ("one","two"):
            FX.h_stat_mod(self.e,self.c,self.c,{"stat":"weight_class","value":-2},{"source_id":"move/test","effect_occurrence":source})
        self.assertEqual(self.c.weight_class,1)
        sources=list(G.state(self.c)["weight_sources"]["sources"])
        G.revoke(self.c,sources[0],engine=self.e)
        self.assertEqual(self.c.weight_class,2)
        G.revoke(self.c,sources[1],engine=self.e)
        self.assertEqual(self.c.weight_class,4)
        self.assertEqual(self.c.spec["weight_class"],4)

    def test_weight_replacement_hides_earlier_contribution_until_removed(self):
        self.c.spec["weight_class"]=4
        for key in ("metal","copy","later"):G._source(self.c,key,"effect")
        G.weight(self.c,2,"metal",mode="add")
        G.weight(self.c,3,"copy")
        G.weight(self.c,-1,"later",mode="add")
        self.assertEqual(self.c.weight_class,2)
        G.revoke(self.c,"metal",engine=self.e)
        self.assertEqual(self.c.weight_class,2)
        G.revoke(self.c,"copy",engine=self.e)
        self.assertEqual(self.c.weight_class,3)
        G.revoke(self.c,"later",engine=self.e)
        self.assertEqual(self.c.weight_class,4)

    def test_passive_weight_source_is_reversible(self):
        self.c.spec["weight_class"]=4
        self.item("light-metal-fixture",[{"type":"stat_mod","stat":"weight_class","value":-2}])
        self.assertEqual(self.c.weight_class,2)
        I.unregister_item(self.e,self.c,"light-metal-fixture")
        self.assertEqual(self.c.weight_class,4)

    def test_registered_item_instance_is_the_effect_source(self):
        import world_entities as W
        W.register_object(self.e,"physical/claw",location={"kind":"unknown"},reason="observed actual claw",
                          kind="item_instance",item_rule_id="item/선제공격손톱",owner_id=self.c.entity_id)
        I.register_item(self.e,self.c,"선제공격손톱",source_instance_id="physical/claw")
        receipt=self.c._item_reg["선제공격손톱"]
        self.assertEqual(receipt["instance_id"],"physical/claw")
        self.assertEqual(receipt["state_source"],"equipment:physical/claw")
        I.unregister_item(self.e,self.c,"선제공격손톱")
        self.assertEqual(self.c.initiative_bonus,0)
        self.assertIn("physical/claw",self.e._physical_objects)

    def test_wrong_instance_replacement_is_atomic(self):
        import world_entities as W
        self.c.item="선제공격손톱";I.register_item(self.e,self.c)
        W.register_object(self.e,"physical/claw",location={"kind":"unknown"},reason="observed actual claw",
                          kind="item_instance",item_rule_id="item/선제공격손톱",owner_id=self.c.entity_id)
        old=deepcopy((self.c.spec,self.c._item_reg,self.c.initiative_bonus))
        with self.assertRaises(ValueError):I.replace_item(self.e,self.c,"예리한손톱",source_instance_id="physical/claw")
        self.assertEqual((self.c.spec,self.c._item_reg,self.c.initiative_bonus),old)

    def test_rejected_vitamin_does_not_spend_or_change_history(self):
        self.c.spec["items"]={"타우린":1}
        self.c.custom_conditions["transformed"]={"source":"fixture"}
        self.c.budget={"standard":1,"shift":1,"swift":1}
        before=deepcopy((self.c.spec,self.c.budget,self.c.stats))
        with self.assertRaises(ValueError):self.e.use_item(self.c,"타우린",self.c)
        self.assertEqual((self.c.spec,self.c.budget,self.c.stats),before)


    def test_unknown_ability_baseline_transition_is_atomic(self):
        self.ability("복안")
        before=deepcopy((self.c.spec,self.c.accuracy_stage,self.e.log_lines,self.e.rng.getstate()))
        with self.assertRaises(Exception):G.replace_baseline(self.e,self.c,"abilities",["unknown-ability"])
        self.assertEqual((self.c.spec,self.c.accuracy_stage,self.e.log_lines,self.e.rng.getstate()),before)
        self.assertIs(self.e.everyone[0],self.c)

    def test_successful_baseline_transition_removes_only_expired_ability(self):
        self.ability("복안")
        self.item("glasses",[{"type":"grant_ability","grant_ability":"복안"}])
        G.replace_baseline(self.e,self.c,"abilities",["하얀연기"])
        self.assertIn("복안",self.c.abilities)
        self.assertEqual(self.c.accuracy_stage,3)
        I.unregister_item(self.e,self.c,"glasses")
        self.assertEqual(self.c.accuracy_stage,0)
        self.assertIn("all",self.c.stage_loss_immune)


    def test_known_consumable_can_be_held_without_applying_consumption(self):
        before=self.c.hp
        result=I.replace_item(self.e,self.c,"오랭열매")
        self.assertTrue(result["changed"])
        self.assertEqual(self.c.item,"오랭열매")
        self.assertIn("오랭열매",self.c._item_reg)
        self.assertEqual(self.c.hp,before)
        I.replace_item(self.e,self.c,None)
        self.assertIsNone(self.c.item)


    def test_manual_feature_registration_is_source_owned_and_idempotent(self):
        self.c.spec["feats"]=["깡다구"]
        I.register_feats(self.e,self.c)
        first=deepcopy((self.c.registry,self.c.ability_triggers))
        I.register_feats(self.e,self.c)
        self.assertEqual((self.c.registry,self.c.ability_triggers),first)
        source=next(key for key in G.state(self.c)["sources"] if key.startswith("feature:"))
        G.revoke(self.c,source,engine=self.e)
        self.assertFalse(any(row.get("name")=="깡다구" for row in self.c.registry+self.c.ability_triggers))


    def test_floored_raw_stat_contribution_recomputes_after_permanent_change(self):
        self.item("floor",[{"type":"stat_mod","stat":"atk","value":-20}])
        self.assertEqual(self.c.stats["atk"],1)
        new=dict(self.c.spec["stats"]);new["atk"]=20
        F.base_patch(self.c,{"stats":new},reason="verified baseline growth")
        self.assertEqual(self.c.stats["atk"],1)
        self.assertEqual(self.c.spec["stats"]["atk"],20)
        I.unregister_item(self.e,self.c,"floor")
        self.assertEqual(self.c.stats["atk"],20)

    def test_stat_floor_order_and_source_removal_preserve_raw_operations(self):
        self.item("floor",[{"type":"stat_mod","stat":"atk","value":-20}])
        self.item("bonus",[{"type":"stat_base_mod","stat":"atk","value":3}])
        self.assertEqual(self.c.stats["atk"],4)
        I.unregister_item(self.e,self.c,"floor")
        self.assertEqual(self.c.stats["atk"],13)
        I.unregister_item(self.e,self.c,"bonus")
        self.assertEqual(self.c.stats["atk"],10)

    def test_untracked_source_stat_write_blocks_baseline_change_before_mutation(self):
        self.item("floor",[{"type":"stat_mod","stat":"atk","value":-20}])
        self.c.stats["atk"]=6
        old=deepcopy((self.c.spec,self.c.stats))
        new=dict(self.c.spec["stats"]);new["atk"]=20
        with self.assertRaises(ValueError):F.base_patch(self.c,{"stats":new},reason="unverified raw overwrite")
        self.assertEqual((self.c.spec,self.c.stats),old)


    def test_atomic_transition_preserves_cross_field_and_external_container_aliases(self):
        shared={"value":1}
        self.c.spec["fixture_alias"]=shared
        self.c.custom_conditions["fixture_alias"]=shared
        self.c.registry.append({"actor":self.c,"shared":shared})
        self.c.custom_conditions["actor_dict"]=vars(self.c)
        original_spec=self.c.spec;original_shared=shared;original_registry=self.c.registry
        G.replace_baseline(self.e,self.c,"moves",[self.rules.move_id("몸통박치기")])
        self.assertIs(self.c.spec,original_spec)
        self.assertIs(self.c.spec["fixture_alias"],original_shared)
        self.assertIs(self.c.custom_conditions["fixture_alias"],original_shared)
        self.assertIs(self.c.registry,original_registry)
        self.assertIs(self.c.registry[0]["actor"],self.c)
        self.assertIs(self.c.registry[0]["shared"],original_shared)
        self.assertIs(self.c.custom_conditions["actor_dict"],vars(self.c))
        I.replace_item(self.e,self.c,"선제공격손톱")
        self.assertIs(self.c.spec,original_spec)
        self.assertIs(self.c.custom_conditions["fixture_alias"],original_shared)
        self.assertIs(self.c.custom_conditions["actor_dict"],vars(self.c))


    def test_swap_actual_item_instances_keeps_owner_and_changes_equipped_holder(self):
        import world_entities as W
        other=Combatant(self.rules,build_trainer(self.rules,"other-holder",10,dict(self.c.spec["stats"]),abilities=[]))
        self.e.everyone.append(other);self.e.gm.everyone=self.e.everyone
        for actor,name,instance in ((self.c,"선제공격손톱","physical/a"),(other,"예리한손톱","physical/b")):
            actor.item=name;actor.spec["item"]=name
            W.register_object(self.e,instance,location={"kind":"unknown"},reason="actual equipment fixture",kind="item_instance",item_rule_id="item/"+name,owner_id=actor.entity_id)
            I.register_item(self.e,actor,name,source_instance_id=instance,as_held=True)
        a_object=self.e._physical_objects["physical/a"]
        self.c.pos=(0,0);other.pos=(1,0)
        G.replace_baseline(self.e,self.c,"moves",["move/바꿔치기"])
        self.e.rng.seed(0)
        self.e.use_move(self.c,other,"move/바꿔치기")
        self.assertEqual(self.c.item,"예리한손톱");self.assertEqual(other.item,"선제공격손톱")
        self.assertIs(self.e._physical_objects["physical/a"],a_object)
        self.assertEqual(a_object["owner_id"],self.c.entity_id)
        self.assertEqual(a_object["equipped_by"],other.entity_id)
        self.assertEqual(other._item_reg["선제공격손톱"]["instance_id"],"physical/a")
        self.assertEqual(self.c.initiative_bonus,0);self.assertEqual(other.initiative_bonus,10)

    def test_failed_item_swap_preserves_both_actors(self):
        other=Combatant(self.rules,build_trainer(self.rules,"other-holder",10,dict(self.c.spec["stats"]),abilities=[]))
        self.e.everyone.append(other)
        self.c.item="선제공격손톱";I.register_item(self.e,self.c)
        other.item="unknown-item"
        before=deepcopy((self.c.spec,other.spec,self.c.item,other.item,self.c.initiative_bonus))
        with self.assertRaises(ValueError):I.exchange_items(self.e,self.c,other)
        self.assertEqual((self.c.spec,other.spec,self.c.item,other.item,self.c.initiative_bonus),before)

    def test_steal_actual_carried_instance_moves_only_known_weight_observation(self):
        import world_entities as W
        import capability_actions as C
        import effects_ext as X
        other=Combatant(self.rules,build_trainer(self.rules,"other-holder",10,dict(self.c.spec["stats"]),abilities=[]))
        self.e.everyone.append(other)
        for actor in (self.c,other):
            actor.spec.setdefault("movement",{})["power"]=4
            actor.spec["power_basis"]="current"  # This fixture observes current carrying Power.
        name="선제공격손톱";self.c.item=name
        W.register_object(self.e,"physical/a",location={"kind":"unknown"},reason="actual known-weight fixture",kind="item_instance",item_rule_id="item/"+name,owner_id=self.c.entity_id,weight_kg=1)
        C.set_carried(self.e,self.c,[{"id":"physical/a","weight_kg":1}],"weighed held item")
        I.register_item(self.e,self.c,name,source_instance_id="physical/a")
        X.h_steal_item(self.e,other,self.c,{"if":"user holds nothing"},{})
        self.assertIsNone(self.c.item);self.assertEqual(other.item,name)
        self.assertEqual(self.e._physical_objects["physical/a"]["carrier_id"],other.entity_id)
        self.assertEqual(self.e._physical_objects["physical/a"]["owner_id"],self.c.entity_id)
        self.assertFalse(self.c.spec["_carried_load"]["objects"])
        self.assertEqual(other.spec["_carried_load"]["objects"],[{"id":"physical/a","weight_kg":1}])

    def test_permanent_weight_change_replays_saturating_modifier(self):
        self.c.spec['weight_class']=2
        G.weight(self.c,-5,'light-source',mode='add',minimum=1)
        F.base_patch(self.c,{'weight_class':7},reason='observed permanent weight')
        self.assertEqual(self.c.weight_class,2)
        G.remove_owned(self.e,self.c,'light-source')
        self.assertEqual(self.c.weight_class,7)

    def test_permanent_type_change_keeps_overlay_and_new_baseline_after_end(self):
        F.base_patch(self.c,{'types':['노말']},reason='permanent initial type')
        G.type_operation(self.c,'add',['고스트'],'ghost-source')
        F.base_patch(self.c,{'types':['불꽃']},reason='permanent new type')
        self.assertEqual(self.c.types,['불꽃','고스트'])
        G.remove_owned(self.e,self.c,'ghost-source')
        self.assertEqual(self.c.types,['불꽃'])

    def test_soulless_zero_base_hp_survives_stat_baseline_projection(self):
        self.c.spec['kind']='pokemon';self.c.spec['capabilities']=['영혼없음']
        self.c.spec['stats']['hp']=0;self.c.stats['hp']=0
        proposed=dict(self.c.spec['stats'],atk=11)
        self.assertEqual(G.prepare_stat_baseline(self.c,proposed)['hp'],0)
        G.stat(self.c,'hp',0,'soulless-zero')
        self.assertEqual(self.c.stats['hp'],0)

    def poffin_pokemon(self):
        from builder import build_pokemon
        p=Combatant(self.rules,build_pokemon(self.rules,'피카츄',25,extra={'trainer_id':self.c.entity_id}))
        self.e.everyone.append(p);return p

    def test_grace_history_is_preserved_but_available_tracks_actual_owner(self):
        import poffin_state as P
        p=self.poffin_pokemon();p.spec['poffins']=['근사함']*8
        self.c.spec['edges']=['edge/우아함'];self.c.spec['skills']={'매력':3}
        self.assertEqual(len(P.available(p,self.c,engine=self.e)),8)
        self.c.spec['edges']=[]
        self.assertEqual(len(P.available(p,self.c,engine=self.e)),6)
        self.assertEqual(len(p.spec['poffins']),8)
        other=Combatant(self.rules,build_trainer(self.rules,'new-owner',10,dict(self.c.spec['stats']),abilities=[]))
        self.e.everyone.append(other);p.spec['trainer_id']=other.entity_id
        with self.assertRaises(ValueError):P.available(p,self.c,engine=self.e)
        other.spec['edges']=['우아함'];other.spec['skills']={'명령':3}
        self.assertEqual(len(P.available(p,engine=self.e)),8)

    def test_grace_feeding_producer_records_seventh_benefit_and_native_contest_consumes_it(self):
        import crafting_activities as C
        import poffin_state as P
        from contest import ContestEngine,ContestRules
        p=self.poffin_pokemon();p.spec['poffins']=['근사함']*6
        self.c.spec['edges']=['우아함'];self.c.spec['skills']={'매력':3}
        self.c.spec['poffin_batches']={'test-batch':{'count':2,'contest_stat':'근사함'}}
        result=C.feed_poffin(self.e,self.c,batch_id='test-batch',target=p,minutes=1,reason='recorded owned meal')
        self.assertTrue(result['effective']);self.assertEqual(len(P.history(p)),7)
        self.assertEqual(p.spec['poffin_consumption'][-1]['benefit_source'],P.GRACE)
        ce=ContestEngine(ContestRules(str(ROOT),ruleset='core'))
        enhanced=ce.stat_pool_from_combatant(p,trainer=self.c,engine=self.e,smart_stat_policy='ptk-literal-defense')
        self.c.spec['edges']=[]
        ordinary=ce.stat_pool_from_combatant(p,trainer=self.c,engine=self.e,smart_stat_policy='ptk-literal-defense')
        self.assertEqual(enhanced['근사함']-ordinary['근사함'],1)
        self.assertEqual(len(P.history(p)),7)

    def test_grace_requires_one_acquisition_and_any_eligible_novice_skill(self):
        import poffin_state as P
        p=self.poffin_pokemon();self.c.spec['edges']=['우아함']
        self.c.spec['skills']={}
        before=deepcopy(p.spec)
        with self.assertRaises(ValueError):P.available(p,self.c,engine=self.e)
        self.assertEqual(p.spec,before)
        for skill in ('매력','명령','교활','협박','직감'):
            with self.subTest(skill=skill):
                self.c.spec['skills']={skill:3}
                self.assertEqual(P.consumption_limit(p,self.c,engine=self.e),8)
        self.c.spec['edges']=['우아함','edge/우아함']
        with self.assertRaises(ValueError):P.consumption_limit(p,self.c,engine=self.e)

    def test_class_slots_count_distinct_branches_and_shared_legacy_references_once(self):
        import acquired_features as A
        self.c.spec.update(classes=['class/코디네이터','class/스타일-전문가'],feats=['class/코디네이터'],feature_choices={'class/스타일-전문가':['근사함','아름다움','귀여움']})
        before=deepcopy(self.c.spec)
        self.assertEqual(len(A.class_instances(self.c)),4)
        self.assertEqual(self.c.spec,before)
        self.c.spec['feature_choices']['class/스타일-전문가'].append('강인함')
        with self.assertRaises(ValueError):A.validate_class_slots(self.c)
        with self.assertRaises(ValueError):I.register_feats(self.e,self.c)

    def test_class_branch_domain_and_duplicate_aliases_are_rejected(self):
        import acquired_features as A
        self.c.spec.update(classes=['class/스탯-에이스'],feature_choices={'class/스탯-에이스':['공격','atk']})
        with self.assertRaises(ValueError):A.class_instances(self.c)
        self.c.spec['feature_choices']['class/스탯-에이스']=['hp']
        with self.assertRaises(ValueError):A.class_instances(self.c)
        self.c.spec.update(classes=['class/타입-에이스'],feature_choices={'class/타입-에이스':['불꽃','물']})
        self.assertEqual(len(A.class_instances(self.c)),2)
        self.c.spec['feature_choices']['class/타입-에이스'].append('invented')
        with self.assertRaises(ValueError):A.class_instances(self.c)

    def test_ranked_feature_count_respects_source_cap_without_creating_acquisition(self):
        import acquired_features as A
        self.c.spec.update(feats=['feat/근사한-행위'],feat_ranks={'feat/근사한-행위':2})
        self.assertEqual(A.feature_rank(self.c,'feat/근사한-행위'),2)
        self.c.spec['feat_ranks']['feat/근사한-행위']=3
        with self.assertRaises(ValueError):A.feature_rank(self.c,'feat/근사한-행위')
        self.c.spec['feats']=[]
        with self.assertRaises(ValueError):A.feature_rank(self.c,'feat/근사한-행위')

    def test_researcher_pairs_each_take_one_class_slot_and_missing_choices_are_not_invented(self):
        import acquired_features as A
        self.c.spec.update(classes=['class/연구원'])
        with self.assertRaises(ValueError):A.class_instances(self.c)
        self.c.spec['feature_choices']={'class/연구원':[['general','apothecary'],['botany','chemistry']]}
        self.assertEqual(len(A.class_instances(self.c)),2)
        self.c.spec['research_fields']=['general','apothecary']
        with self.assertRaises(ValueError):A.class_instances(self.c)

    def test_untracked_native_stat_registration_rejects_and_restores_entire_graph(self):
        spec=self.c.spec;stats=self.c.stats;conditions=self.c.custom_conditions
        shared={'value':1};spec['alias']=shared;conditions['alias']=shared
        before=deepcopy((self.c.spec,self.c.stats,self.c.registry,self.e.gm_prompts))
        def bad():
            self.c.stats['atk']+=2
            shared['value']=9
            self.c.registry.append({'type':'fixture'})
            self.e.gm_prompts.append({'unknown':'source'})
        with self.assertRaisesRegex(ValueError,'untracked native stat writer'):
            G.apply_owned(self.e,self.c,'bad-native-source',bad)
        self.assertIs(self.c.spec,spec);self.assertIs(self.c.stats,stats)
        self.assertIs(self.c.custom_conditions,conditions)
        self.assertIs(self.c.spec['alias'],shared);self.assertIs(conditions['alias'],shared)
        self.assertEqual((self.c.spec,self.c.stats,self.c.registry,self.e.gm_prompts),before)


    def test_adversarial_weapon_equip_projects_alias_baseline_once(self):
        import turn as TURN,move_state as MOVES
        for baseline in ('백스윙','move/백스윙'):
            with self.subTest(baseline=baseline):
                self.setUp()
                actor=Combatant(self.rules,build_trainer(self.rules,'raw-alias-weapon-owner',10,
                    dict(self.c.spec['stats']),moves=[baseline],skills={'전투':4},abilities=[]))
                baseline_moves=list(actor.spec['moves'])
                self.assertEqual(baseline_moves,[baseline,'struggle'])
                self.e.everyone=self.e.gm.everyone=[actor]
                key=TURN.equip_weapon(self.e,actor,
                    {'name':'adversarial-alias-'+('canonical' if baseline.startswith('move/') else 'display'),'kind':'대형 근접무기','grade':'좋음','moves':['백스윙']})
                self.assertEqual(actor.spec['moves'],baseline_moves)
                self.assertCountEqual(actor.moves,['move/백스윙','struggle',key])
                self.assertEqual([self.rules.move_id(value) for value in actor.moves].count('move/백스윙'),1,
                    'two valid sources must project one semantic Move without manual materialization')
                self.assertIn(key,MOVES.known(self.rules,{'moves':actor.moves}))

    def test_adversarial_late_sourced_move_survives_native_weapon_drop(self):
        import turn as TURN,move_state as MOVES
        for mode in ('learned','permission'):
            for late in (False,True):
                with self.subTest(mode=mode,late=late):
                    self.setUp();G.set_baseline(self.c,'moves',[])
                    self.e.gm.set_skill(self.c,'전투',4,reason='actual Adept weapon user')
                    def grant():
                        G.grant_moves(self.c,['백스윙'],'independent-script-source','feature',
                            rule_id='keyword/연결',mode=mode)
                    if not late:grant()
                    key=TURN.equip_weapon(self.e,self.c,
                        {'name':'adversarial-grant-order-'+mode+'-'+str(late),'kind':'대형 근접무기','grade':'좋음','moves':['백스윙']})
                    if late:grant()
                    source=deepcopy(self.c.spec[G.KEY]['sources']['independent-script-source'])
                    I.drop_equipment(self.e,self.c,['weapon:'+key],slots=('주요손','반대손'),consent_by=(self.c,))
                    self.assertEqual(self.c.spec[G.KEY]['sources']['independent-script-source'],source)
                    self.assertIn('move/백스윙',self.c.moves,'dropping gear cannot revoke another current source')
                    self.assertNotIn(key,self.c.moves)
                    owned=MOVES.owned_list(self.c.spec,'moves',self.c.moves,rules=self.rules)
                    self.assertEqual(owned,['move/백스윙'] if mode=='learned' else [])
                    G.revoke(self.c,'independent-script-source',engine=self.e)
                    self.assertNotIn('move/백스윙',self.c.moves)

    def test_adversarial_weapon_equip_respects_active_transform_move_overlay(self):
        import turn as TURN,effects_ext as X
        self.e.gm.set_skill(self.c,'전투',4,reason='actual Adept weapon user')
        G.set_baseline(self.c,'moves',['몸통박치기']);self.c.spec['weight_class']=4
        target=Combatant(self.rules,build_trainer(self.rules,'observed-transform-donor',10,
            dict(self.c.spec['stats']),moves=['move/방어'],abilities=[],extra={'weight_class':2}))
        donor_moves=list(target.moves)
        self.assertEqual(donor_moves,['move/방어','struggle'])
        self.e.everyone=self.e.gm.everyone=[self.c,target]
        X.h_transform(self.e,self.c,target,{},
            {'source_id':'move/변신','effect_occurrence':'adversarial-transform'})
        source=self.c.custom_conditions['transformed']['source']
        self.assertEqual(self.c.moves,donor_moves)
        key=TURN.equip_weapon(self.e,self.c,
            {'name':'adversarial-transform-weapon','kind':'대형 근접무기','grade':'좋음','moves':['백스윙']})
        self.assertEqual(self.c.moves,donor_moves,'active replacement overlay owns the visible Move list')
        self.assertEqual(self.c.spec['moves'],['몸통박치기'])
        G.revoke(self.c,source,engine=self.e)
        self.assertIn('move/몸통박치기',self.c.moves)
        self.assertIn('move/백스윙',self.c.moves)
        I.drop_equipment(self.e,self.c,['weapon:'+key],slots=('주요손','반대손'),consent_by=(self.c,))
        self.assertEqual(self.c.moves,['move/몸통박치기'])

    def test_weapon_projection_legacy_no_ledger_drop_does_not_promote_equipment_moves(self):
        import turn as TURN,state_codec as CODEC,world_entities as WORLD
        baseline_moves=list(self.c.spec['moves'])
        self.assertEqual(baseline_moves,['struggle'])
        self.e.gm.set_skill(self.c,'전투',4,reason='actual Adept weapon user')
        key=TURN.equip_weapon(self.e,self.c,
            {'name':'v3-legacy-weapon-shape','kind':'대형 근접무기','grade':'좋음','moves':['백스윙']})
        state=self.c.spec[G.KEY]
        self.assertFalse(any(state[field] for field in
            ('sources','overlays','effects','ability_receipts','numbers','sets','scalar_sources')))
        self.assertEqual(state['legacy']['moves'],[])
        # Prior native producer shape had the weapon ledger and no grant ledger.
        self.c.spec.pop(G.KEY)
        I.drop_equipment(self.e,self.c,['weapon:'+key],slots=('주요손','반대손'),consent_by=(self.c,))
        self.assertEqual(self.c.moves,baseline_moves)
        self.assertEqual(self.c.spec[G.KEY]['legacy']['moves'],[])
        restored=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        actor=WORLD.actor_index(restored)[self.c.entity_id]
        self.assertEqual(actor.moves,baseline_moves)
        self.assertNotIn('move/백스윙',actor.spec[G.KEY]['legacy']['moves'])

    def test_weapon_projection_forgetting_baseline_does_not_revive_equip_snapshot(self):
        import turn as TURN,state_codec as CODEC,world_entities as WORLD
        self.e.gm.set_skill(self.c,'전투',4,reason='actual Adept weapon user')
        G.set_baseline(self.c,'moves',['백스윙'])
        key=TURN.equip_weapon(self.e,self.c,
            {'name':'v3-forgotten-baseline-weapon','kind':'대형 근접무기','grade':'좋음','moves':['백스윙']})
        self.assertIn('move/백스윙',self.c.custom_conditions['equipped_weapons'][key]['independently_known'])
        self.e.gm.set_move(self.c,'백스윙',add=False,reason='actual permanent Move forgetting while equipment remains')
        self.assertEqual(self.c.spec['moves'],[])
        self.assertIn('move/백스윙',self.c.moves,'weapon still grants temporary use before removal')
        I.drop_equipment(self.e,self.c,['weapon:'+key],slots=('주요손','반대손'),consent_by=(self.c,))
        self.assertEqual(self.c.moves,[],'old equip-time knowledge is not current learning authority')
        restored=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        self.assertEqual(WORLD.actor_index(restored)[self.c.entity_id].moves,[])

    def test_weapon_projection_two_slots_and_live_item_source_keep_independent_moves(self):
        import turn as TURN
        baseline_moves=list(self.c.spec['moves'])
        self.assertEqual(baseline_moves,['struggle'])
        self.e.gm.set_skill(self.c,'전투',4,reason='actual Adept weapon user')
        first=TURN.equip_weapon(self.e,self.c,
            {'name':'v3-main-hand','kind':'소형 근접무기','grade':'좋음','slot':'주요손','moves':['강타']})
        second=TURN.equip_weapon(self.e,self.c,
            {'name':'v3-off-hand','kind':'소형 근접무기','grade':'좋음','slot':'반대손','moves':['강타']})
        self.assertEqual(self.c.moves.count('move/강타'),1)
        I.drop_equipment(self.e,self.c,['weapon:'+first],slots=('주요손','반대손'),consent_by=(self.c,))
        self.assertIn('move/강타',self.c.moves)
        self.assertIn(second,self.c.moves);self.assertNotIn(first,self.c.moves)
        item=self.item('v3-overlapping-item',[{'type':'grant_move','moves':['강타']}])
        row=self.c._item_reg[item]
        sources=deepcopy(self.c.spec[G.KEY]['sources'])
        self.assertTrue(any(source.get('kind')=='item' and 'move/강타' in source.get('grants',{}).get('moves',[])
                            for source in sources.values()))
        I.drop_equipment(self.e,self.c,['weapon:'+second],slots=('주요손','반대손'),consent_by=(self.c,))
        self.assertEqual(self.c.spec[G.KEY]['sources'],sources)
        self.assertIs(self.c._item_reg[item],row)
        self.assertEqual(self.c.moves,baseline_moves+['move/강타'])
        I.unregister_item(self.e,self.c,item)
        self.assertEqual(self.c.moves,baseline_moves,'last independent item source removes its grant, not basic Struggle')

    def test_move_union_preserves_alias_baseline_and_canonical_sources_through_restore(self):
        import move_state as MOVES, state_codec as CODEC, world_entities as WORLD
        G.set_baseline(self.c, 'moves', ['몸통박치기'])
        original = deepcopy(self.c.spec['moves'])
        G.grant_moves(self.c, ['move/몸통박치기'], 'independent-move', 'feature',
                      owner_id=self.c.entity_id, lifetime='while_owned', rule_id='keyword/연결')
        receipt = deepcopy(self.c.spec[G.KEY]['sources']['independent-move'])
        self.assertEqual(self.c.spec['moves'], original)
        self.assertEqual(receipt['grants']['moves'], ['move/몸통박치기'])
        self.assertEqual(MOVES.owned_list(self.c.spec, 'moves', self.c.moves, rules=self.rules), ['move/몸통박치기'])
        self.assertEqual(self.c.moves, ['move/몸통박치기'])
        self.e.gm.restore(self.e.gm.snapshot('move-union'))
        restored = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(self.e))))
        actor = WORLD.actor_index(restored)[self.c.entity_id]
        self.assertEqual(actor.spec['moves'], original)
        self.assertEqual(actor.spec[G.KEY]['sources']['independent-move'], receipt)
        self.assertEqual(MOVES.describe(self.rules, actor.spec)['known'], ['move/몸통박치기'])

    def test_move_union_rejects_duplicates_within_one_source_without_mutation(self):
        import move_state as MOVES
        G.set_baseline(self.c, 'moves', ['몸통박치기'])
        before = deepcopy((self.c.spec, self.c.moves))
        for values in (['몸통박치기', 'move/몸통박치기'], ['move/몸통박치기', 'move/몸통박치기']):
            with self.subTest(values=values):
                with self.assertRaisesRegex(ValueError, 'distinct selected'):
                    MOVES.known(self.rules, {'moves':values})
                with self.assertRaisesRegex(ValueError, 'distinct selected'):
                    G.grant_moves(self.c, values, 'bad-source', 'feature', rule_id='keyword/연결')
                self.assertEqual((self.c.spec, self.c.moves), before)
                with self.assertRaisesRegex(ValueError, 'distinct selected'):
                    G.set_baseline(self.c, 'moves', values)
                self.assertEqual((self.c.spec, self.c.moves), before)
        candidate = deepcopy(self.c.spec)
        candidate[G.KEY]['sources']['malformed'] = {'kind':'feature', 'grants':{'moves':['몸통박치기','move/몸통박치기']}}
        for read in (MOVES.owned_list, MOVES.effective_list):
            with self.assertRaisesRegex(ValueError, 'distinct selected'):
                read(candidate, 'moves', rules=self.rules)
        self.assertEqual((self.c.spec, self.c.moves), before)

    def test_move_union_revokes_only_one_owner_and_never_promotes_permission(self):
        import move_state as MOVES
        G.set_baseline(self.c, 'moves', ['몸통박치기'])
        for source, move in (('first-owner','move/몸통박치기'), ('second-owner','몸통박치기')):
            G.grant_moves(self.c, [move], source, 'feature', rule_id='keyword/연결')
        second = deepcopy(self.c.spec[G.KEY]['sources']['second-owner'])
        G.grant_moves(self.c, ['방어'], 'temporary-permission', 'feature',
                      rule_id='keyword/연결', mode='permission')
        G.revoke(self.c, 'first-owner', engine=self.e)
        self.assertEqual(self.c.spec[G.KEY]['sources']['second-owner'], second)
        self.assertEqual(MOVES.owned_list(self.c.spec, 'moves', self.c.moves, rules=self.rules), ['move/몸통박치기'])
        G.set_baseline(self.c, 'moves', [])
        self.assertEqual(MOVES.owned_list(self.c.spec, 'moves', self.c.moves, rules=self.rules), ['move/몸통박치기'])
        G.revoke(self.c, 'second-owner', engine=self.e)
        self.assertEqual(MOVES.owned_list(self.c.spec, 'moves', self.c.moves, rules=self.rules), [])
        self.assertEqual(self.c.moves, ['move/방어'])
        G.revoke(self.c, 'temporary-permission', engine=self.e)
        self.assertEqual(self.c.moves, [])

    def test_unknown_move_grant_preflight_changes_nothing(self):
        before=deepcopy(self.c.spec)
        with self.assertRaisesRegex(ValueError,"unresolved move"):
            G.register_feature_effect(self.e,self.c,self.c,"fixture","feat/fixture",0,
                {"type":"grant_move","moves":["방어","unknown-category2-move"]})
        self.assertEqual(self.c.spec,before);self.assertNotIn("move/방어",self.c.moves)

    def test_capability_sources_preserve_baseline_and_use_actual_terrain(self):
        from grid import Grid
        import movement_actions as MOVE
        self.e.grid=Grid(8,2);self.e.grid.slow={(1,0),(2,0),(3,0)}
        self.c.spec['capabilities']=['자연걸음(숲)']
        before=deepcopy(self.c.spec)
        self.assertEqual(G.effective_capabilities(self.c),['자연걸음(숲)'])
        self.assertEqual(before,self.c.spec)
        G.register_feature_effect(self.e,self.c,self.c,'fixture','feat/fixture',0,
            {'type':'grant_capability','capability':'자연걸음(초원), 자연걸음(숲)'})
        MOVE.observe_cell_terrain(self.e,[(1,0)],['초원'],'observed grassland')
        MOVE.observe_cell_terrain(self.e,[(2,0)],['숲'],'observed forest')
        self.assertEqual(MOVE.slow_terrain_penalty(self.e,self.c,(1,0),'육상'),0)
        self.assertEqual(MOVE.slow_terrain_penalty(self.e,self.c,(3,0),'육상'),1)
        G.revoke(self.c,'feature:'+self.c.entity_id+':feat/fixture',engine=self.e)
        self.assertEqual(MOVE.slow_terrain_penalty(self.e,self.c,(1,0),'육상'),1)
        self.assertEqual(MOVE.slow_terrain_penalty(self.e,self.c,(2,0),'육상'),0)
        self.assertEqual(self.c.spec['capabilities'],['자연걸음(숲)'])

    def test_static_immunities_keep_independent_owners(self):
        self.c.status_immune={'얼음'}
        for rule in ('feat/one','feat/two'):
            for index,(kind,label,value) in enumerate((('keyword_immunity','keyword','가루'),('weather_immunity','weather','싸라기눈'),('status_immunity','status','얼음'))):
                G.register_feature_effect(self.e,self.c,self.c,'fixture',rule,index,{'type':kind,label:value})
        G.revoke(self.c,'feature:'+self.c.entity_id+':feat/one',engine=self.e)
        self.assertIn('가루',self.c.keyword_immune);self.assertIn('싸라기눈',self.c.weather_immune)
        G.revoke(self.c,'feature:'+self.c.entity_id+':feat/two',engine=self.e)
        self.assertNotIn('가루',self.c.keyword_immune);self.assertNotIn('싸라기눈',self.c.weather_immune)
        self.assertIn('얼음',self.c.status_immune)

    def test_movement_baseline_patch_survives_equipment_revoke(self):
        self.e.gm.set_movement_capabilities(self.c, {'land':5}, basis='current', reason='observed current sheet')
        self.item('speed-boots',[{'type':'speed_mod','value':2}])
        F.base_patch(self.c,{'movement':{'land':8}},reason='permanent base observation')
        self.assertEqual(self.c.movement,10)
        I.unregister_item(self.e,self.c,'speed-boots')
        self.assertEqual(self.c.movement,8)

    def test_trainer_edge_capability_current_and_base_are_distinct(self):
        import capability_actions as CAP
        import movement_actions as MOVE
        import trainer_capabilities as TRAINER
        self.c.spec.update(edges=['파워 부스트','수영 선수'],skills={'육상':3},movement={'power':5,'swim':3,'land':6},movement_basis='current',power_basis='current')
        self.assertEqual(CAP.power(self.c),5);self.assertEqual(MOVE.capabilities(self.e,self.c)['swim'],3)
        self.c.spec.update(power_basis='base',movement_basis='base')
        self.assertEqual(CAP.power(self.c),7);self.assertEqual(MOVE.capabilities(self.e,self.c)['swim'],5)
        self.c.spec.update(movement={},movement_basis='trainer_base',skills={'육상':3,'곡예':2,'생존':4,'전투':4},power_basis='derived',power_policy='ch02:123')
        self.assertEqual(CAP.power(self.c),7)
        self.c.spec['power_policy']='ch02:208';self.assertEqual(CAP.power(self.c),8)
        self.assertEqual(MOVE.capabilities(self.e,self.c)['swim'],4)
        self.assertEqual(TRAINER.breath_grace(self.c,'water'),240);self.assertEqual(TRAINER.breath_grace(self.c,'airless'),60)

    def test_traveler_explicit_substitutions_and_official_power_correction(self):
        import trainer_capabilities as TRAINER
        self.c.spec.update(edges=['여행자'],skills={'곡예':2,'육상':3,'생존':6},movement_basis='trainer_base')
        with self.assertRaisesRegex(ValueError,'explicit substitutions'):TRAINER.values(self.c)
        self.c.spec['edge_choices']={'여행자':['land','jump']}
        self.assertEqual(TRAINER.values(self.c),{'land':7,'high_jump':2,'long_jump':3})
        self.c.spec['edge_choices']={'여행자':['power']};self.c.spec['power_policy']='ch02:123'
        self.assertEqual(TRAINER.derived_power(self.c),5)
        self.c.spec['skills']['생존']=2;self.assertEqual(TRAINER.derived_power(self.c),4)
        self.c.spec['edge_choices']={'여행자':[]};self.c.spec['skills']['육상']=4
        self.assertEqual(TRAINER.derived_power(self.c),5)

    def test_swimmer_native_clock_uses_water_only_and_keeps_start(self):
        self.c.spec.update(edges=['수영 선수'],skills={'육상':3,'생존':4})
        self.e.observe_breathing(self.c,air_available=False,medium='water',reason='submerged',timing_policy='grace_boundary')
        self.e.advance_time(239)
        self.e.observe_breathing(self.c,air_available=False,medium='water',reason='still submerged')
        self.e.advance_time(1);self.assertEqual(self.c.injuries,1)
        self.e.observe_breathing(self.c,air_available=True,medium='air',reason='surfaced')
        self.assertEqual(self.c.injuries,0)
        self.e.observe_breathing(self.c,air_available=False,medium='airless',reason='sealed room',timing_policy='grace_boundary')
        self.e.advance_time(60);self.assertEqual(self.c.injuries,1)

    def test_changed_swimmer_rank_blocks_clock_until_observed(self):
        self.c.spec.update(edges=['수영 선수'],skills={'육상':3,'생존':4})
        self.e.observe_breathing(self.c,air_available=False,medium='water',reason='submerged',timing_policy='grace_boundary')
        self.c.spec['skills']['생존']=5
        with self.assertRaisesRegex(ValueError,'new timed world observation'):self.e.advance_time(1)
        self.assertEqual(self.e.elapsed_seconds,0)
        self.e.observe_breathing(self.c,air_available=False,medium='water',reason='new sourced capacity')
        self.e.advance_time(299);self.assertEqual(self.c.injuries,0)
        self.e.advance_time(1);self.assertEqual(self.c.injuries,1)

    def test_source_named_move_pairs_apply_both_and_preserve_independent_copy(self):
        pairs={'feat/달맞이산-블루스': ['노래하기', '초음파'], 'feat/불협화음': ['싫은소리', '금속음'], 'feat/소음-신고': ['소란피기', '하이퍼보이스'], 'feat/엇갈린-메시지': ['악마의키스', '트집'], 'feat/불시의-공격': ['따라가때리기', '기습'], 'feat/거리의-싸움꾼': ['승부굳히기', '보복'], 'feat/악감정': ['검은눈빛', '야금야금'], 'feat/잔혹한-응시': ['뱀눈초리', '박치기'], 'feat/굳건함': ['버티기', '게으름피우기'], 'feat/위에서-내려온-죽음': ['애크러뱃', '뛰어오르기'], 'feat/신성-방패': ['리플렉터', '주술'], 'feat/신비의-방어': ['빛의장막', '신비의부적'], 'feat/pk-오메가': ['텔레키네시스', '사이코키네시스'], 'feat/연마된-정신': ['마음의눈', '명상'], 'feat/정신공격': ['신통력', '사이코쇼크'], 'feat/공간-왜곡': ['순간이동', '사이드체인지'], 'feat/지면-뒤틀기': ['중력', '트릭'], 'feat/이상한-힘': ['회복봉인', '매직코트']}
        for uid,moves in pairs.items():
            with self.subTest(uid=uid):
                c=Combatant(self.rules,build_trainer(self.rules,'pair-owner',10,{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
                c.spec['feats']=[uid];G.set_baseline(c,'moves',[self.rules.move_id(moves[0])])
                I.register_feats(self.e,c)
                self.assertTrue(all(self.rules.move_id(move) in c.moves for move in moves))
                G.revoke(c,'feature:'+c.entity_id+':'+uid,engine=self.e)
                self.assertIn(self.rules.move_id(moves[0]),c.moves)
                self.assertNotIn(self.rules.move_id(moves[1]),c.moves)

    def test_naturewalk_changes_native_movement_and_accuracy_only_on_observed_cells(self):
        from grid import Grid
        import movement_actions as MOVE
        import turn
        e=self.e;c=self.c;c.pos=(0,0);c.side='a';c.spec.update(movement={'land':4},movement_basis='current');c.movement=4
        target=Combatant(self.rules,build_trainer(self.rules,'terrain-target',10,{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
        target.pos=(7,0);target.side='b';e.everyone.append(target);e.gm.everyone=e.everyone
        e.grid=Grid(8,1,slow={(1,0),(2,0),(3,0),(4,0)},rough={(7,0)})
        G.grant(c,'capabilities','자연걸음(숲)','native-terrain','fixture')
        MOVE.observe_cell_terrain(e,[(x,0) for x in range(1,8)],['숲'],'actual forest floor')
        e.start_round([c,target]);e.start_of_turn(c);e.approach(c,target)
        self.assertEqual(c.pos,(4,0))
        move=dict(self.rules.moves[self.rules.move_id('몸통박치기')]);move['ac']=5
        target.hp=0
        self.assertTrue(e.accuracy_check(c,target,move,fixed_roll=6)[0])
        G.revoke(c,'native-terrain',engine=e)
        self.assertFalse(e.accuracy_check(c,target,move,fixed_roll=6)[0])

    def test_survivalist_selected_terrain_supplies_native_naturewalk(self):
        from tools.test_category3_survivalist import Tests
        import movement_actions as MOVE
        Tests.setUpClass();fixture=Tests();fixture.setUp();fixture.master('forest')
        fixture.movement();MOVE.observe_cell_terrain(fixture.e,[(1,0)],['forest'],'actual forest')
        self.assertTrue(MOVE.ordinary_terrain(fixture.e,fixture.a,(1,0)))
        self.assertFalse(MOVE.ordinary_terrain(fixture.e,fixture.a,(2,0)))

    def test_species_naturewalk_creation_evolution_and_independent_source(self):
        from builder import build_pokemon
        import downtime
        import movement_actions as MOVE
        from grid import Grid
        c=Combatant(self.rules,build_pokemon(self.rules,'이상해씨',16))
        self.assertEqual(c.spec['naturewalk'],'초원, 숲')
        self.e.grid=Grid(3,1,slow={(1,0)})
        MOVE.observe_cell_terrain(self.e,[(1,0)],['숲'],'observed forest floor')
        self.assertTrue(MOVE.ordinary_terrain(self.e,c,(1,0)))
        self.assertEqual(MOVE.slow_terrain_penalty(self.e,c,(1,0),'육상'),0)
        G.grant(c,'capabilities','자연걸음(사막)','independent','fixture')
        target=self.rules.species['pokemon/이상해풀']
        with patch.dict(target,naturewalk='습지'):
            self.assertTrue(downtime.evolve(self.rules,c.spec,'이상해풀'))
        self.assertEqual(c.spec['naturewalk'],'습지')
        self.assertEqual(MOVE.naturewalk_terrains(self.e,c),frozenset(('wetland','desert')))
        self.assertFalse(MOVE.ordinary_terrain(self.e,c,(1,0)))
        G.revoke(c,'independent',engine=self.e)
        self.assertEqual(MOVE.naturewalk_terrains(self.e,c),frozenset(('wetland',)))

    def test_species_naturewalk_distinct_labels_and_source_errors(self):
        import movement_actions as MOVE
        from grid import Grid
        self.e.grid=Grid(3,1)
        for name in MOVE.NATUREWALK_ADDITIONAL_TERRAINS:
            self.c.spec['naturewalk']=name
            MOVE.observe_cell_terrain(self.e,[(1,0)],[name],'observed exact named terrain')
            self.assertTrue(MOVE.ordinary_terrain(self.e,self.c,(1,0)))
            MOVE.observe_cell_terrain(self.e,[(1,0)],['바다'],'observed ocean')
            self.assertFalse(MOVE.ordinary_terrain(self.e,self.c,(1,0)))
        for invalid in ['슾지','초원s','숲. 초원',4,['숲',4]]:
            self.c.spec['naturewalk']=invalid
            before=deepcopy(self.c.spec)
            with self.assertRaises(ValueError):MOVE.naturewalk_terrains(self.e,self.c)
            self.assertEqual(self.c.spec,before)

if __name__=="__main__":
    unittest.main()
