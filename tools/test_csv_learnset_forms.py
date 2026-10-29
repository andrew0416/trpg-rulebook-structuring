"""Whole selected CSV form contracts through actual existing native owners."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json, sys, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine'), str(ROOT/'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer, species_lookup, STATS
from state_codec import dump_engine, load_engine
import csv_item_form_contracts as C, growth_stats as GROWTH, state_grants as G
import world_entities as W, items as I, downtime as DT, skill_modifiers as SKILL
import native_scenario_fixture as N


class CsvLearnsetFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.r = Rules(str(ROOT), ruleset='all')
    def setUp(self):
        self.e = Engine(self.r, seed=1026)
        self.t = self.add(build_trainer(self.r, 'actual form owner', 30, dict.fromkeys(STATS, 20), moves=[], abilities=[]))
    def add(self, spec):
        c = Combatant(self.r, spec)
        self.e.gm.add_combatant(c, pos=tuple(spec.get('pos', (1,1))), side=spec.get('side', 'party'), reason='actual observed participant')
        return c
    def pokemon(self, species, **options):
        return self.add(build_pokemon(self.r, species, 1, moves=[self.r.move_id(x) for x in options.pop('moves', [])], abilities=options.pop('abilities', []),
                                    extra={'trainer_id':self.t.entity_id, **options}))
    def forms(self, family, active=None, moves=(), abilities=None, custom_appliances=(), level=1, trained=True):
        names = (*C.FORM_FAMILIES[family][1], *custom_appliances)
        active = names[0] if active is None else active
        if abilities is None: abilities = self.r.learnsets[active]['abilities']['기본 특성'][:1]
        if family == 'rotom': abilities = ['ability/폴터가이스트-playtest']
        if family == 'oricorio': abilities = ['무희']
        spec = build_pokemon(self.r, active, level, moves=[self.r.move_id(x) for x in moves], abilities=abilities, extra={'trainer_id':self.t.entity_id} if trained else {})
        points = spec['initial_allocation']['points']; investments = {}; plans = {}
        for name in names:
            base = species_lookup(self.r, name)['base_stats']
            # Author a legal equal-HP set, without granting a stat-relation exception.
            investment = GROWTH.allocate(base, points, rules=self.r, excluded=('hp',))['investment']
            plans[name] = GROWTH.compose(base, investment, points=points, rules=self.r, strategy='balanced')
            investments[name] = investment
        spec['initial_allocation'] = deepcopy(plans[active]); spec['stats'] = deepcopy(plans[active]['stats'])
        c = self.add(spec)
        C.configure_learnset_forms(self.e, c, family, investments,custom_appliances=custom_appliances,
                                  gm_reason='actual authored air-cleaner appliance' if custom_appliances else None)
        return c
    def physical(self, actor, uid, item):
        N.prepare_object(self.e, uid, kind='item_instance', item_rule_id='item/'+item, owner_id=actor.entity_id,
                         location={'kind':'unknown'}, reason='actual inspected source-named object')
        return self.e._physical_objects[uid]
    def turn(self, actor):
        if self.e._active_turn_actor is not None: self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.gm.everyone); self.e.start_of_turn(actor)
    def valid(self): self.assertTrue(self.e.validate_state()['valid'], self.e.validate_state())
    def reload(self, *actors):
        self.e.gm.restore(self.e.gm.snapshot())
        ids = [c.entity_id for c in actors]
        self.e = load_engine(self.r, json.loads(json.dumps(dump_engine(self.e), ensure_ascii=False)))
        self.r = self.e.r
        self.t = W.actor_index(self.e)[self.t.entity_id]
        self.valid()
        return [W.actor_index(self.e)[uid] for uid in ids]
    def test_exact_selected_sources_full_sheets_and_unknown_form_atomicity(self):
        for record, _ in C.FORM_FAMILIES.values():
            source, proof = C.learnset_source(self.r, record)
            self.assertEqual(proof['record'], record); self.assertEqual(self.r._selected_rule(source['id']), source['id'])
        c = self.forms('deoxys'); before = dump_engine(self.e)
        N.assert_rejected_unchanged(self.e,lambda:C.change_deoxys(self.e,c,'invented',seconds=5),reason_pattern='declared actual form')
        self.assertEqual(before, dump_engine(self.e))
        # The only catalog Pressure is an optional Playtest, not a core alias.
        core = Rules(str(ROOT), ruleset='core')
        with self.assertRaises(ValueError): core._selected_rule('ability/프레셔-playtest')
        bad = deepcopy(c.spec[C.STATE]); c.spec[C.STATE]['learnset_forms']['forms'].pop('테오키스 스피드폼')
        self.assertFalse(self.e.validate_state()['valid']); c.spec[C.STATE] = bad; self.valid()
    def test_deoxys_four_real_sheets_extended_outside_only_growth_and_both_restores(self):
        selected=self.forms('deoxys'); before=dump_engine(self.e)
        # Actual Weird Power rows differ and have no implemented damage owner.
        # This prerequisite remains deferred, never guessed from the first name.
        with self.assertRaises(ValueError): C.change_deoxys(self.e,selected,'테오키스 어택폼',seconds=5)
        self.assertEqual(before,dump_engine(self.e))
        c = self.forms('deoxys',abilities=[]); hp = c.hp; self.turn(c); before = dump_engine(self.e)
        with self.assertRaisesRegex(ValueError, 'outside'): C.change_deoxys(self.e, c, '테오키스 스피드폼', seconds=5)
        self.assertEqual(before, dump_engine(self.e)); self.e.end_encounter()
        G._source(c, 'independent:atk', 'fixture'); G.stat(c, 'atk', 2, 'independent:atk')
        for name in C.FORM_FAMILIES['deoxys'][1]:
            C.change_deoxys(self.e, c, name, seconds=5)
            self.assertEqual(c.form, name); self.assertEqual(c.spec['species'], species_lookup(self.r,name)['id'])
            self.assertEqual(c.stats['atk'], c.spec['stats']['atk']+2); self.assertEqual(c.hp,hp)
        self.assertEqual(self.e.elapsed_seconds, 20)
        c, = self.reload(c); DT.gain_exp_combatant(self.e,c,'to next level',stat_choices={2:'hp'})
        self.assertEqual(c.level,2); self.assertEqual(len(c.spec['form_growth_allocations']['plans']),4); self.valid()
    def test_rotom_actual_appliance_projects_types_skills_capabilities_size_and_learning_source(self):
        import ability_state_projection as P, movement_actions as MOVEMENT
        c = self.forms('rotom',level=40)
        self.assertEqual((c.spec['movement_basis'],c.spec['movement']['levitate']),('base',4))
        self.assertIn('ability/폴터가이스트-playtest',c.abilities)
        self.assertFalse({'부유','ability/부유'}.intersection(c.abilities))
        self.assertEqual(MOVEMENT.capabilities(self.e,c,environment=False)['levitate'],4)
        appliance = N.prepare_object(self.e, 'washer', kind='physical_object', owner_id=c.entity_id,
                                     location={'kind':'unknown'}, reason='actual compatible washing machine')
        appliance['rotom_appliance_form'] = '워시로토무'
        before = dump_engine(self.e)
        with self.assertRaises(ValueError): C.inhabit_appliance(self.e,c,'워시로토무',appliance_id='missing')
        self.assertEqual(before,dump_engine(self.e))
        C.inhabit_appliance(self.e,c,'워시로토무',appliance_id='washer')
        self.assertIn('ability/저수',c.abilities); self.assertIn('move/하이드로펌프',c.moves)
        self.assertEqual(c.types,['전기','물']); self.assertEqual((c.spec['size'],c.weight_class),('중형',3))
        self.assertIn('물줄기',G.effective(c,'capabilities')); self.assertEqual(c.spec['skills'],{k:str(v['rank'])+'d6'+format(int(v.get('mod',0)),'+d') for k,v in self.r.species_skills['워시로토무'].items()})
        self.assertEqual(species_lookup(self.r,c.spec['species'])['name'],'워시로토무')
        self.assertEqual(MOVEMENT.capabilities(self.e,c,environment=False)['levitate'],4)
        c, = self.reload(c); C.inhabit_appliance(self.e,c,'로토무')
        self.assertEqual(MOVEMENT.capabilities(self.e,c,environment=False)['levitate'],6)
        c, = self.reload(c)
        self.assertEqual((c.spec['movement']['levitate'],MOVEMENT.capabilities(self.e,c,environment=False)['levitate']),(4,6))
        self.assertIn('ability/부유',c.abilities); self.assertNotIn('ability/저수',c.abilities); self.assertNotIn('move/하이드로펌프',c.moves)
        self.assertEqual(c.spec[P.KEY]['ability/폴터가이스트-playtest']['observation'],{'form':'로토무'})
        N.assert_rejected_unchanged(self.e,lambda:P.activate(self.e,c,'ability/폴터가이스트-playtest',choice='히트로토무',reason='wrong nonbase form must not alias'),reason_pattern='actual current form')
        self.assertEqual(c.types,['전기','고스트']); self.assertEqual((c.spec['size'],c.weight_class),('소형',1)); self.valid()
        self.r=Rules(str(ROOT),ruleset='all',custom_species=[str(ROOT/'tools/fixtures/csv-custom-rotom.json')]); self.setUp()
        c=self.forms('rotom',custom_appliances=('GM 공기청정로토무',),level=40)
        G._source(c,'fixture:independent-ability','fixture'); G.grant(c,'abilities','ability/방음','fixture:independent-ability','fixture')
        washer=N.prepare_object(self.e,'prior-washer',kind='physical_object',owner_id=c.entity_id,location={'kind':'unknown'},reason='actual prior compatible washing machine')
        washer['rotom_appliance_form']='워시로토무'; C.inhabit_appliance(self.e,c,'워시로토무',appliance_id='prior-washer')
        self.assertIn('ability/저수',c.abilities); self.assertIn('move/하이드로펌프',c.moves)
        body=N.prepare_object(self.e,'air-cleaner',kind='physical_object',owner_id=c.entity_id,location={'kind':'unknown'},reason='actual GM-designed air-cleaner appliance')
        body['rotom_appliance_form']='GM 공기청정로토무'
        C.inhabit_appliance(self.e,c,'GM 공기청정로토무',appliance_id='air-cleaner')
        self.assertNotIn('ability/폴터가이스트-playtest',c.spec.get(P.KEY,{}))
        self.assertNotIn('ability/저수',c.abilities); self.assertNotIn('move/하이드로펌프',c.moves); self.assertIn('ability/방음',c.abilities)
        self.assertEqual(c.types,['전기','독']); self.assertEqual((c.spec['size'],c.weight_class),('중형',3))
        self.assertEqual(species_lookup(self.r,c.spec['species'])['name'],'GM 공기청정로토무')
        c,=self.reload(c); C.inhabit_appliance(self.e,c,'로토무'); self.assertIn('ability/부유',c.abilities); self.assertIn('ability/방음',c.abilities); self.valid()
    def test_unowned_rotom_appliance_uses_actual_map_cell_and_roundtrips(self):
        c = self.forms('rotom')
        obj = N.prepare_object(self.e, 'unowned-washer', kind='physical_object',
            location={'kind':'grid', 'cell':list(c.pos)}, reason='actual nearby unowned appliance')
        obj['rotom_appliance_form'] = '워시로토무'
        use = lambda: C.inhabit_appliance(self.e, c, '워시로토무', appliance_id='unowned-washer')
        for location in ({'kind':'unknown'},
                {'kind':'grid', 'cell':[c.pos[0]+1,c.pos[1]], 'pos':list(c.pos)},
                {'kind':'grid', 'cell':list(c.pos), 'map_id':'another-map'}):
            with self.subTest(location=location):
                W.observe_location(self.e, self.e._physical_objects['unowned-washer'], location, reason='actual appliance location')
                N.assert_rejected_unchanged(self.e, use, reason_pattern='reach its appliance')
        W.observe_location(self.e, self.e._physical_objects['unowned-washer'], {'kind':'grid', 'cell':list(c.pos)},
                           reason='actual same-map same-cell appliance')
        use(); self.assertEqual(c.form, '워시로토무')
        c, = self.reload(c)
        self.assertEqual(W.distance_known(self.e._physical_objects['unowned-washer'], c), 0)
        C.inhabit_appliance(self.e, c, '로토무')
        C.inhabit_appliance(self.e, c, '워시로토무', appliance_id='unowned-washer')
        self.assertEqual(c.form, '워시로토무'); self.valid()

    def test_unowned_flower_and_bottle_require_same_map_cell_without_mutation_on_refusal(self):
        for family, item, expected in (('shaymin','그라시데아꽃','쉐이미 스카이폼'),
                                       ('hoopa','굴레의항아리','굴레를 벗어난 후파')):
            with self.subTest(family=family):
                self.setUp(); c = self.forms(family)
                uid = 'unowned-form-item'
                N.prepare_object(self.e, uid, kind='item_instance', item_rule_id='item/'+item,
                    location={'kind':'grid', 'cell':list(c.pos)}, reason='actual nearby unowned form item')
                def use():
                    if family == 'shaymin':
                        return C.observe_form_environment(self.e, c, reason='actual sun and flower',
                            sunlight=True, gracidea_instance=uid, choose_sky=True)
                    return C.uncork_prison_bottle(self.e, c, uid, reason='actual nearby uncorked Bottle')
                for location in ({'kind':'unknown'},
                        {'kind':'grid', 'cell':[c.pos[0]+1,c.pos[1]], 'pos':list(c.pos)},
                        {'kind':'grid', 'cell':list(c.pos), 'map_id':'another-map'}):
                    with self.subTest(location=location):
                        W.observe_location(self.e, self.e._physical_objects[uid], location, reason='actual form item location')
                        N.assert_rejected_unchanged(self.e, use, reason_pattern='not accessible')
                W.observe_location(self.e, self.e._physical_objects[uid], {'kind':'grid', 'cell':list(c.pos)},
                                   reason='actual same-map same-cell form item')
                use(); self.assertEqual(c.form, expected)
                c, = self.reload(c)
                self.assertEqual(c.form, expected)
                self.assertEqual(W.distance_known(self.e._physical_objects[uid], c), 0)
                self.assertIsNone(self.e._physical_objects[uid].get('owner_id')); self.valid()

    def test_giratina_actual_reverse_world_and_fragment_boundaries(self):
        import movement_actions as MOVEMENT
        c=self.forms('giratina')
        self.assertEqual(MOVEMENT.capabilities(self.e,c,environment=False)['levitate'],0)
        for world,fragment,form in ((True,False,'기라티나 오리진폼'),(False,True,'기라티나 오리진폼'),(False,False,'기라티나 어나더폼')):
            C.observe_form_environment(self.e,c,reason='GM observes actual Reverse World presence',reverse_world=world,reverse_fragment=fragment)
            self.assertEqual(c.form,form)
            if world:c,=self.reload(c)
            self.assertEqual((c.spec['movement_basis'],c.spec['movement']['levitate']),('base',0))
            movement=MOVEMENT.capabilities(self.e,c,environment=False)
            self.assertEqual(movement['levitate'],4 if form=='기라티나 오리진폼' else 0)
            self.assertEqual(movement['sky'],10)
        c,=self.reload(c); self.assertEqual(c.form,'기라티나 어나더폼'); self.valid()
        self.assertEqual(MOVEMENT.capabilities(self.e,c,environment=False)['levitate'],0)
    def test_shaymin_actual_flower_sun_ice_and_native_ice_move_hit(self):
        import move_completion as COMPLETE, passive_events as PASSIVE, move_defense_reactions as DEFENSE
        from grid import Grid
        c=self.forms('shaymin'); self.physical(c,'flower','그라시데아꽃')
        C.observe_form_environment(self.e,c,reason='actual sun and rare flower',sunlight=True,gracidea_instance='flower',choose_sky=True)
        self.assertEqual(c.form,'쉐이미 스카이폼')
        # Losing proximity alone is not one of the printed reversion events.
        C.observe_form_environment(self.e,c,reason='actual continuing sun, flower now absent',sunlight=True)
        self.assertEqual(c.form,'쉐이미 스카이폼')
        C.observe_form_environment(self.e,c,reason='actual ice contact',sunlight=True,touches_ice=True)
        self.assertEqual(c.form,'쉐이미')
        C.observe_form_environment(self.e,c,reason='actual sun and rare flower',sunlight=True,gracidea_instance='flower',choose_sky=True)
        foe=self.add(build_trainer(self.r,'actual Ice Beam opponent',1,dict.fromkeys(STATS,10),moves=['move/냉동빔'],abilities=[],side='opponent',pos=(1,2))); self.turn(foe); self.e.rng.seed(31)
        self.e.use_move(foe,c,'move/냉동빔')
        self.assertFalse(list(self.e._move_completions.values())[-1]['results'][c.entity_id]['hit']); self.assertEqual(c.form,'쉐이미 스카이폼')
        # The printed EOT Move needs one real intervening turn before reuse.
        self.turn(foe); self.turn(foe); self.e.rng.seed(0)
        result=self.e.use_move(foe,c,'move/냉동빔'); self.assertGreater(result,0)
        self.assertEqual(self.e._passive_events,{})
        completion=list(self.e._move_completions.values())[-1]
        self.assertTrue(completion['results'][c.entity_id]['hit']); self.assertEqual(c.form,'쉐이미')
        before=dump_engine(self.e); COMPLETE.refresh(self.e,completion['id']); self.assertEqual(before,dump_engine(self.e))
        self.e.end_encounter(); C.observe_form_environment(self.e,c,reason='actual rare flower again',sunlight=True,gracidea_instance='flower',choose_sky=True)
        c,=self.reload(c); C.observe_form_environment(self.e,c,reason='actual sunset',sunlight=False)
        self.assertEqual(c.form,'쉐이미'); self.valid()
        # An actual native Protect consumes its own receipt, without an Ice hit.
        self.setUp(); c=self.forms('shaymin',moves=('방어',),trained=False); self.physical(c,'shield-flower','그라시데아꽃')
        C.observe_form_environment(self.e,c,reason='actual sunlight and flower',sunlight=True,gracidea_instance='shield-flower',choose_sky=True)
        foe=self.add(build_trainer(self.r,'actual blocked Ice Beam',1,dict.fromkeys(STATS,10),moves=['move/냉동빔'],abilities=[],side='opponent',pos=(1,2)))
        self.turn(c); self.e.use_move(c,c,'move/방어',set_damage=True); self.assertIsNotNone(c.shield)
        self.e.end_of_turn(c); self.e.start_of_turn(foe); self.e.rng.seed(0)
        self.assertEqual(self.e.use_move(foe,c,'move/냉동빔',set_damage=True),0)
        self.assertFalse(list(self.e._move_completions.values())[-1]['results'][c.entity_id]['hit']); self.assertEqual(c.form,'쉐이미 스카이폼'); self.assertIsNone(c.shield); self.valid()
        # A routed Ice hit changes only the real recipient, not the displaced Sky ally.
        self.setUp(); self.e.grid=Grid(20,20)
        protected=self.forms('shaymin'); c=self.forms('shaymin'); c.spec['loyalty']=6
        for actor,uid in ((protected,'protected-flower'),(c,'recipient-flower')):
            self.physical(actor,uid,'그라시데아꽃')
            C.observe_form_environment(self.e,actor,reason='actual sunlight and rare flower',sunlight=True,gracidea_instance=uid,choose_sky=True)
        protected.pos=(3,2); c.pos=(3,4)
        foe=self.add(build_trainer(self.r,'actual routed Ice Beam',1,dict.fromkeys(STATS,10),moves=['move/냉동빔'],abilities=[],side='opponent',pos=(2,2))); self.turn(foe); self.e.rng.seed(530)
        self.e.watch_move_defense(protected,[{'actor_id':c.entity_id,'source':DEFENSE.MELEE}],reason='actual loyal ally intercepts Ice Beam')
        with self.assertRaises(PASSIVE.PassiveEventPending):self.e.use_move(foe,protected,'move/냉동빔',set_damage=True)
        event=self.e._passive_pending; hp=protected.hp
        self.e.choose_move_defense(event,c,use=True,options={'path':[(3,4),(3,3),(3,2)],'skill':'육상','mode':'land','shove_destination':[4,2],'roll_options':{'fixed':[6]*SKILL.rank(self.r,c,'육상')[2]}},reason='actual allied recipient')
        row=list(self.e._move_completions.values())[-1]; self.assertEqual(set(row['received']),{c.entity_id})
        self.assertTrue(row['received'][c.entity_id]['hit']); self.assertEqual(c.form,'쉐이미'); self.assertEqual((protected.form,protected.hp),('쉐이미 스카이폼',hp))
        before=dump_engine(self.e); COMPLETE.refresh(self.e,row['id']); self.assertEqual(before,dump_engine(self.e)); self.valid()
    def test_forces_nature_actual_held_mirror_equip_remove_all_four_families(self):
        for family in ('tornadus','thundurus','landorus','enamorus'):
            with self.subTest(family=family):
                c=self.forms(family); uid='mirror-'+family; self.physical(c,uid,'비추는거울')
                if family=='tornadus':
                    with patch.object(C,'_switch_profile',side_effect=ValueError('late form callback')):
                        N.assert_rejected_unchanged(self.e,lambda:I.equip_held(self.e,c,'비추는거울',source_instance_id=uid),reason_pattern='late form callback')
                I.equip_held(self.e,c,'비추는거울',source_instance_id=uid)
                self.assertEqual(c.form,C.FORM_FAMILIES[family][1][1])
                self.assertTrue(self.e.validate_state()['valid'],self.e.validate_state())
                c,=self.reload(c)
                if family=='tornadus':
                    with patch.object(C,'_switch_profile',side_effect=ValueError('late form callback')):
                        N.assert_rejected_unchanged(self.e,lambda:I.replace_item(self.e,c,None),reason_pattern='late form callback')
                I.replace_item(self.e,c,None)
                self.assertEqual(c.form,C.FORM_FAMILIES[family][1][0]); self.valid()
    def test_oricorio_all_four_real_nectar_units_extended_cost_and_restore(self):
        c=self.forms('oricorio'); c.spec['items']={name:1 for name in C.NECTARS}
        for nectar,form in C.NECTARS.items():
            C.drink_nectar(self.e,c,nectar,seconds=7,quantity_key=nectar)
            self.assertEqual(c.form,form); self.assertEqual(c.spec['items'][nectar],0); self.assertEqual(c.types[1],'비행')
        before=dump_engine(self.e)
        with self.assertRaises(ValueError): C.drink_nectar(self.e,c,'보라꿀',seconds=7,quantity_key='보라꿀')
        self.assertEqual(before,dump_engine(self.e)); self.assertEqual(self.e.elapsed_seconds,28)
        c,=self.reload(c); self.assertEqual(c.form,'춤추새 하늘하늘스타일'); self.valid()
    def test_kyurem_actual_willing_partner_disappears_xp_splits_and_extended_release(self):
        c=self.forms('kyurem'); partner=self.pokemon('제크로무')
        before=dump_engine(self.e)
        with self.assertRaises(ValueError): C.fuse_kyurem(self.e,c,partner,willing=False,seconds=10)
        self.assertEqual(before,dump_engine(self.e))
        with self.assertRaisesRegex(ValueError,'actual Gene Fusion partner'):
            C.fuse_kyurem(self.e,c,self.t,willing=True,seconds=10)
        self.assertEqual(before,dump_engine(self.e))
        C.fuse_kyurem(self.e,c,partner,willing=True,seconds=10)
        self.assertEqual(c.form,'블랙큐레무'); self.assertFalse(partner.on_field)
        with self.assertRaises(ValueError): C.require_independent(self.e,partner)
        old=[a.spec.get('exp',DT.exp_for_level(self.r,a.level)) for a in (c,partner)]
        DT.gain_exp_combatant(self.e,c,4)
        self.assertEqual([a.spec['exp']-x for a,x in zip((c,partner),old)],[2,2])
        import encounter_settlement as SETTLEMENT
        self.turn(c); self.e.end_encounter()
        reward=SETTLEMENT.observe(self.e,encounter_id='actual-fusion-battle',rewarded_trainers=[self.t],
            participating_pokemon={self.t.entity_id:[c]},winner=self.t,defeated_levels=[1],reason='GM observes actual completed battle participants')
        old=[a.spec['exp'] for a in (c,partner)]
        SETTLEMENT.allocate_pokemon_xp(self.e,encounter_id='actual-fusion-battle',trainer=self.t,allocations={c.entity_id:reward['xp_share']})
        self.assertEqual([a.spec['exp']-x for a,x in zip((c,partner),old)],[reward['xp_share']//2]*2)
        c,partner=self.reload(c,partner); C.release_kyurem(self.e,c,seconds=10)
        self.assertEqual(c.form,'큐레무'); self.assertTrue(partner.on_field); self.assertNotIn('off_field_reason',partner.spec); self.valid()
        reshiram=self.pokemon('레시라무'); C.fuse_kyurem(self.e,c,reshiram,willing=True,seconds=1)
        self.assertEqual(c.form,'화이트큐레무'); C.release_kyurem(self.e,c,seconds=1); self.valid()
    def test_hoopa_real_bottle_three_day_form_then_three_day_cooldown_and_native_incurable(self):
        c=self.forms('hoopa',moves=['이차원홀','섀도볼','고스트다이브']); self.physical(c,'bottle','굴레의항아리')
        C.uncork_prison_bottle(self.e,c,'bottle',reason='actual uncorked Bottle exposure')
        self.assertEqual(c.form,'굴레를 벗어난 후파'); self.assertIn('난동',c.conditions)
        for mid in ('move/이차원러시','move/악의파동','move/탁쳐서떨구기'): self.assertIn(mid,c.moves)
        self.assertFalse(self.e.cure_status(c,'난동')); c,=self.reload(c)
        self.e.advance_time(3*86400-1,[]); self.assertEqual(c.form,'굴레를 벗어난 후파')
        self.e.advance_time(1,[]); self.assertEqual(c.form,'후파'); self.assertNotIn('난동',c.conditions)
        self.assertIn('move/이차원홀',c.moves); before=dump_engine(self.e)
        with self.assertRaises(ValueError): C.uncork_prison_bottle(self.e,c,'bottle',reason='actual attempted reuse')
        self.assertEqual(before,dump_engine(self.e)); self.e.advance_time(3*86400,[])
        C.uncork_prison_bottle(self.e,c,'bottle',reason='actual cooldown completed reuse'); self.valid()
    def test_hoopa_native_physical_destruction_permanent_and_new_actual_bottle_seals(self):
        c=self.forms('hoopa'); self.physical(c,'bottle','굴레의항아리')
        I.register_item(self.e,c,'굴레의항아리',source_instance_id='bottle')
        C.uncork_prison_bottle(self.e,c,'bottle',reason='actual exposed Hoopa')
        I.destroy_equipment(self.e,c,'bottle',reason='actual broken Prison Bottle',consent_by=(c,))
        self.assertTrue(c.spec[C.STATE]['hoopa_unbound']['permanent'])
        c,=self.reload(c); self.e.advance_time(7*86400,[]); self.assertEqual(c.form,'굴레를 벗어난 후파')
        self.physical(c,'new-bottle','굴레의항아리')
        C.seal_hoopa(self.e,c,'new-bottle',newly_created=True,reason='GM observes newly created Bottle sealing Hoopa')
        self.assertEqual(c.form,'후파'); self.assertNotIn('난동',c.conditions); self.valid()
    def test_altaria_native_mega_payload_and_actual_sky_stealth_pool(self):
        reader=self.add(build_trainer(self.r,'ordinary stealth reader',30,dict.fromkeys(STATS,20),
                                      skills={'은신':2},moves=[],abilities=[]))
        self.assertNotIn('species',reader.spec)
        self.assertIsNone(C.skill_pool_projection(reader,'stealth'))
        self.assertEqual(SKILL.rank(self.r,reader,'stealth')[1:],('2d6',2))
        reader,=self.reload(reader)
        self.assertNotIn('species',reader.spec)
        self.assertIsNone(C.skill_pool_projection(reader,'stealth'))
        self.assertEqual(SKILL.rank(self.r,reader,'stealth')[1:],('2d6',2))
        c=self.pokemon('파비코리'); self.physical(self.t,'ring','메가링'); self.physical(c,'stone','파비코리나이트')
        I.register_item(self.e,self.t,'메가링',source_instance_id='ring'); I.register_item(self.e,c,'파비코리나이트',source_instance_id='stone')
        before=deepcopy(c.stats); self.turn(c)
        self.e.mega_evolve(self.t,c,'mega/파비코리',actor=c,ring='ring',stone='stone')
        self.assertEqual(c.types,['드래곤','페어리']); self.assertIn('페어리스킨',c.abilities)
        self.assertEqual(c.stats,{s:v+{'atk':4,'def':2,'spa':4}.get(s,0) for s,v in before.items()})
        self.assertIsNone(C.skill_pool_projection(c,'stealth'))
        # The native paid vertical movement producer owns the actual altitude.
        from grid import Grid
        import movement_actions as MOVEMENT
        self.e.grid=Grid(10,10)
        self.e.gm.set_position(c,(2,2),reason='actual open sky position')
        MOVEMENT.aerial_move(self.e,c,(2,2),mode='sky',altitude=1,reason_text='actual paid Sky ascent')
        self.assertEqual(C.skill_pool_projection(c,'stealth'),(6,3)); self.assertEqual(SKILL.rank(self.r,c,'stealth')[2],6)
        import researcher_features as SKILLS
        plan=SKILLS.native_plan(self.e,c,'stealth'); self.assertEqual((plan['dice_count'],plan['modifier']),(6,3))
        c,=self.reload(c); self.assertEqual(C.skill_pool_projection(c,'stealth'),(6,3)); self.valid()


class CsvOricorioBirthTests(unittest.TestCase):
    def test_actual_egg_hatch_uses_immutable_parent_form_and_both_source_editions(self):
        import test_foundation_egg_creation as F
        import creation_egg as EGGS, pokemon_entities as P
        F.EggTests.setUpClass(); f=F.EggTests(); f.setUp()
        f.parents=[f.add(build_pokemon(f.r,'춤추새 하늘하늘스타일',5,moves=[],abilities=['무희'],extra={'trainer_id':f.a.entity_id,'gender':'female'})),
                   f.add(build_pokemon(f.r,'춤추새 이글이글스타일',5,moves=[],abilities=['무희'],extra={'trainer_id':f.a.entity_id,'gender':'male'}))]
        policy=f.policy(); policy['inheritance']={'kind':'declared','parents':[0,1],'knowledge':'any','moves':[]}
        for case,expected in (('ordinary','춤추새 하늘하늘스타일'),('ditto','춤추새 이글이글스타일')):
            if case=='ditto':
                f.parents[0]=f.add(build_pokemon(f.r,'메타몽',5,moves=[],abilities=[],extra={'trainer_id':f.a.entity_id,'gender':'genderless'}))
                policy['requirements'][2]['condition']['value']='genderless'
                policy['requirements'][2]['reason']='actual genderless Ditto parent, not an assumed mother'
            row=f.create(policy,request_id='oricorio-'+case,species='춤추새 이글이글스타일',inheritance_moves=[])
            selected={'gender':'male','nature':'노력','abilities':['무희'],'moves':[],'special_appearance':False,'inheritance_moves':[]}
            child=f.e.hatch_declared_egg(f.a,row['entity_id'],name='actual Oricorio child',ready=True,reason='actual hatch observed',choices=selected)['pokemon']
            self.assertEqual(species_lookup(f.r,child.spec['species'])['name'],expected)
        self.assertTrue(f.e.validate_state()['valid'])


if __name__=='__main__': unittest.main()
