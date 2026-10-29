"""Whole-scope category 3 introduction, performance and position regressions."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from contest import Contestant,ContestEngine,ContestRules

class Sequence:
    def __init__(self,faces):self.faces=list(faces)
    def randint(self,a,b):
        n=self.faces.pop(0)
        assert a<=n<=b
        return n
class Ones:
    def randint(self,a,b):return 1

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=ContestRules(ROOT)
    def setUp(self):self.e=ContestEngine(self.rules,73)
    def actor(self,name='A',**kw):
        data=dict(name=name,stat_dice={},moves=['연속자르기'],intro_skill='매력',intro_rank_dice=1,intro_stat='귀여움')
        data.update(kw)
        return Contestant(**data)
    def native_actors(self):
        from engine import Engine, Rules, Combatant
        r=Rules(ROOT)
        engine=Engine(r)
        base={'level':20,'stats':dict.fromkeys(['hp','atk','def','spa','spd','spe'],10),'moves':['연속자르기']}
        trainer=Combatant(r,dict(base,id='trainer-a',name='T',kind='trainer',skills={'매력':'초보'},edges=[]))
        pokemon=Combatant(r,dict(base,id='pokemon-a',name='P',kind='pokemon',trainer_id='trainer-a'))
        engine.gm.add_combatant(trainer,reason='actual native contest trainer')
        engine.gm.add_combatant(pokemon,reason='actual owned native contest performer')
        return engine,pokemon,trainer
    def test_native_equipped_item_sources_generate_intro_bonuses(self):
        import items
        engine,pokemon,trainer=self.native_actors()
        items.register_item(engine,pokemon,'콘테스트 장신구')
        items.register_item(engine,trainer,'멋진 옷')
        c=self.e.contestant_from_combatants(engine,pokemon,trainer,'매력',{},bonus_stats={'item/콘테스트-장신구':'강인함','item/멋진-옷':'아름다움'})
        self.e.rng=Sequence([3,4,1,3,1,3,4]);self.e.intro_stage([c],'귀여움')
        self.assertEqual(c.stat_dice,{'귀여움':2,'강인함':1,'아름다움':2})
        self.assertEqual(c.appeal,2)
    def test_native_unequip_prevents_prepared_item_bonus(self):
        import items
        engine,pokemon,trainer=self.native_actors()
        items.register_item(engine,pokemon,'콘테스트 장신구')
        c=self.e.contestant_from_combatants(engine,pokemon,trainer,'매력',{},bonus_stats={'item/콘테스트-장신구':'강인함'})
        items.unregister_item(engine,pokemon,'콘테스트 장신구')
        before=self.e.rng.getstate()
        with self.assertRaises(ValueError):self.e.intro_stage([c],'귀여움')
        self.assertEqual(self.e.rng.getstate(),before);self.assertEqual(c.appeal,0)
    def test_native_unregistered_inventory_item_or_wrong_owner_is_not_equipped(self):
        engine,pokemon,trainer=self.native_actors()
        pokemon.spec['inventory']=['콘테스트 장신구']
        with self.assertRaises(ValueError):self.e.contestant_from_combatants(engine,pokemon,trainer,'매력',{},bonus_stats={'item/콘테스트-장신구':'강인함'})
        pokemon.spec['trainer_id']='other'
        with self.assertRaises(ValueError):self.e.contestant_from_combatants(engine,pokemon,trainer,'매력',{})
    def test_introduction_cannot_be_reapplied_in_same_contest(self):
        c=self.actor();self.e.rng=Ones();self.e.intro_stage([c],'귀여움')
        before=(deepcopy(vars(c)),list(self.e.log_lines))
        with self.assertRaises(ValueError):self.e.intro_stage([c],'귀여움')
        self.assertEqual((vars(c),self.e.log_lines),before)
    def test_native_grooming_action_grants_one_die_for_current_day_only(self):
        import frequency
        engine,pokemon,trainer=self.native_actors()
        trainer.spec['edges']=['미용사'];trainer.spec['skills']['포켓몬학']='초보'
        trainer.spec['items']={'미용사 킷':1}
        engine.everyone=engine.gm.everyone=[trainer,pokemon]
        engine.pokemon_activity(trainer,'groom',targets=[pokemon],safe=True)
        self.assertEqual(engine.elapsed_seconds,3600)
        c=self.e.contestant_from_combatants(engine,pokemon,trainer,'매력',{},bonus_stats={'edge/미용사':'슬기로움'})
        self.e.rng=Sequence([3,1,2,6]);self.e.intro_stage([c],'귀여움')
        self.assertEqual(c.stat_dice,{'귀여움':1,'슬기로움':1})
        prepared=self.e.contestant_from_combatants(engine,pokemon,trainer,'매력',{},bonus_stats={'edge/미용사':'슬기로움'})
        frequency.new_day(pokemon);frequency.new_day(trainer)
        self.e.rng=Ones()
        with self.assertRaises(ValueError):self.e.intro_stage([prepared],'귀여움')
        next_day=self.e.contestant_from_combatants(engine,pokemon,trainer,'매력',{})
        self.e.intro_stage([next_day],'귀여움');self.assertEqual(next_day.stat_dice,{'귀여움':0})
    def test_native_failed_grooming_does_not_supply_an_intro_source(self):
        engine,pokemon,trainer=self.native_actors()
        trainer.spec['items']={'미용사 킷':1}
        with self.assertRaises(ValueError):engine.pokemon_activity(trainer,'groom',targets=[pokemon],safe=True)
        self.assertEqual(engine.elapsed_seconds,0)
        with self.assertRaises(ValueError):self.e.contestant_from_combatants(engine,pokemon,trainer,'매력',{},bonus_stats={'edge/미용사':'슬기로움'})

    def test_stat_pool_uses_unstaged_values_floor_and_basic_cap(self):
        engine,pokemon,trainer=self.native_actors()
        pokemon.stats.update(atk=9,def_=0)
        pokemon.stats['def']=29;pokemon.stats['spa']=30;pokemon.stats['spd']=41;pokemon.stats['spe']=20
        pokemon.stages.update(atk=6,**{'def':-6,'spa':6,'spd':-6,'spe':6})
        pool=self.e.stat_pool_from_combatant(pokemon,smart_stat_policy='ptu-original-special-defense')
        self.assertEqual(pool,{'근사함':0,'강인함':2,'아름다움':3,'슬기로움':3,'귀여움':2})
        with self.assertRaises(Exception):self.e.stat_pool_from_combatant(pokemon)
        literal=self.e.stat_pool_from_combatant(pokemon,smart_stat_policy='ptk-literal-defense')
        self.assertEqual(literal['슬기로움'],2)
    def test_stat_pool_poffin_level_allowance_and_six_cap(self):
        engine,pokemon,trainer=self.native_actors()
        for level,cap in [(1,1),(4,1),(5,2),(10,3),(15,4),(20,5),(25,6),(100,6)]:
            pokemon.level=level;pokemon.spec['poffins']=['귀여움']*cap
            pool=self.e.stat_pool_from_combatant(pokemon,smart_stat_policy='ptk-literal-defense')
            self.assertEqual(pool['귀여움'],1+cap)
            pokemon.spec['poffins'].append('귀여움')
            if cap<6:
                with self.assertRaises(ValueError):self.e.stat_pool_from_combatant(pokemon,smart_stat_policy='ptk-literal-defense')
            else:
                self.assertEqual(self.e.stat_pool_from_combatant(pokemon,smart_stat_policy='ptk-literal-defense')['귀여움'],7)
    def test_native_generated_pool_is_spent_by_actual_performance(self):
        engine,pokemon,trainer=self.native_actors()
        pokemon.stats['atk']=30;pokemon.spec['poffins']=['근사함']
        c=self.e.contestant_from_combatants(engine,pokemon,trainer,'매력',smart_stat_policy='ptu-original-special-defense')
        self.e.perform(c,'연속자르기','근사함',[],False,spend_stat_dice=3,fixed_rolls=[2]*7)
        self.assertEqual((c.stat_dice['근사함'],c.appeal),(1,7))
        self.e.perform(c,'연속자르기','근사함',[],False,spend_stat_dice=1,fixed_rolls=[2]*6)
        self.assertEqual(c.stat_dice['근사함'],0)

    def test_book_stat_mapping_and_all_five_native_move_types_reach_actual_performance(self):
        engine,pokemon,trainer=self.native_actors()
        pokemon.stats.update(atk=10,spa=30,spd=40,spe=10);pokemon.stats['def']=20
        pokemon.stages.update(atk=6,spa=-6,spd=6,spe=-6);pokemon.stages['def']=-6
        expected={'근사함':1,'강인함':2,'아름다움':3,'슬기로움':2,'귀여움':1}
        moves={'근사함':'move/연속자르기','강인함':'move/더블촙',
               '아름다움':'move/화염바퀴','슬기로움':'move/엄습하는일격','귀여움':'move/스위프뺨치기'}
        for move in moves.values():
            engine.gm.set_move(pokemon,move,True,reason='GM grants the selected native contest test move')
        native_before=deepcopy((pokemon.stats,pokemon.stages,pokemon.spec))
        for kind,move in moves.items():
            with self.subTest(kind=kind,move=move):
                contest=ContestEngine(self.rules,73)
                self.assertEqual(self.rules.move_contest(move),(kind,'신뢰'))
                c=contest.contestant_from_combatants(engine,pokemon,trainer,'매력',smart_stat_policy='ptk-literal-defense')
                self.assertEqual(c.stat_dice,expected)
                contest.perform(c,move,kind,[],False,spend_stat_dice=1,fixed_rolls=[2]*5)
                remaining=dict(expected);remaining[kind]-=1
                self.assertEqual(c.stat_dice,remaining);self.assertEqual((c.appeal,c.fumble),(5,0))
                self.assertEqual(c.last_move,move)
        self.assertEqual((pokemon.stats,pokemon.stages,pokemon.spec),native_before)

    def test_source_scope_excerpts_still_match(self):
        ledger=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))
        for e in ledger['entries']:
            if e['id'] not in ['DOMAIN-039','DOMAIN-041','DOMAIN-042','DOMAIN-043']:continue
            for a in e['source_snapshot']['anchors']:
                excerpt='\n'.join((ROOT/a['file']).read_text(encoding='utf-8').splitlines()[a['start']-1:a['end']])
                self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(),a['sha256'])
    def test_all_five_intro_skills_map_rank_dice_and_success_faces(self):
        for skill,stat in [('매력','귀여움'),('명령','근사함'),('교활','슬기로움'),('협박','강인함'),('직감','아름다움')]:
            with self.subTest(skill=skill):
                c=self.actor(intro_skill=skill,intro_rank_dice=6,intro_stat=stat)
                self.e.rng=Sequence([1,2,3,4,5,6]);self.e.intro_stage([c],stat)
                self.assertEqual(c.stat_dice,{stat:4});self.assertEqual(c.appeal,2)
                self.assertEqual(self.e.rng.faces,[])
    def test_intro_matching_bonus_depends_on_skill_and_standard_topic(self):
        for topic,expected in [('귀여움',2),('아름다움',0),(None,0)]:
            c=self.actor();self.e.rng=Ones();self.e.intro_stage([c],topic)
            self.assertEqual(c.appeal,expected)
    def test_intro_bonus_sources_roll_for_other_stats_and_count_for_letters(self):
        a=self.actor('A',intro_sources=['item/콘테스트-장신구','edge/미용사'],intro_bonuses=[{'source_id':'item/콘테스트-장신구','stat':'강인함'},{'source_id':'edge/미용사','stat':'슬기로움'}])
        b=self.actor('B',intro_rank_dice=2)
        self.e.rng=Sequence([1,3,6,4,3,4])
        self.e.intro_stage([a,b],'아름다움')
        self.assertEqual(a.stat_dice,{'귀여움':0,'강인함':2,'슬기로움':1})
        self.assertEqual((a.letter,b.letter),('A','B'))
    def test_intro_fancy_clothes_fixed_source_dice(self):
        a=self.actor(intro_sources=['item/멋진-옷'],intro_bonuses=[{'source_id':'item/멋진-옷','stat':'근사함','dice':2}])
        self.e.rng=Sequence([1,2,3]);self.e.intro_stage([a],'귀여움')
        self.assertEqual(a.stat_dice,{'귀여움':0,'근사함':1});self.assertEqual(a.appeal,2)
    def test_intro_rejects_unowned_duplicate_or_inflated_bonus_without_mutation(self):
        for sources,bonuses in [([], [{'source_id':'edge/미용사','stat':'귀여움'}]),(['edge/미용사'],[{'source_id':'edge/미용사','stat':'귀여움','dice':5}]),(['edge/미용사'],[{'source_id':'edge/미용사','stat':'귀여움'}]*2)]:
            a=self.actor(intro_sources=sources,intro_bonuses=bonuses)
            before=(deepcopy(vars(a)),self.e.rng.getstate(),list(self.e.log_lines))
            with self.assertRaises(ValueError):self.e.intro_stage([a],'귀여움')
            self.assertEqual((vars(a),self.e.rng.getstate(),self.e.log_lines),before)
    def test_intro_invalid_later_actor_does_not_consume_any_dice(self):
        a=self.actor();b=self.actor('B',intro_skill='육상')
        before=(deepcopy(vars(a)),self.e.rng.getstate())
        with self.assertRaises(ValueError):self.e.intro_stage([a,b],'귀여움')
        self.assertEqual((vars(a),self.e.rng.getstate()),before)
    def test_intro_stat_override_requires_selected_grace_and_eligible_rank(self):
        for rank,edges in [(3,[]),(2,['edge/우아함'])]:
            a=self.actor(intro_skill='교활',intro_rank_dice=rank,trainer_edges=edges)
            with self.assertRaises(ValueError):self.e.intro_stage([a],'귀여움')
        a=self.actor(intro_skill='교활',intro_rank_dice=3,trainer_edges=['edge/우아함'])
        self.e.rng=Sequence([3,4,1]);self.e.intro_stage([a],'귀여움')
        self.assertEqual(a.stat_dice,{'귀여움':2});self.assertEqual(a.appeal,0)
    def test_intro_tie_coin_can_reverse_order_but_not_unequal_totals(self):
        for coin,letters in [(1,('A','B')),(6,('B','A'))]:
            a,b=self.actor('X'),self.actor('Y')
            self.e.rng=Sequence([1,1,coin]);self.e.intro_stage([a,b],'아름다움')
            self.assertEqual((a.letter,b.letter),letters)
        a,b=self.actor('X'),self.actor('Y')
        self.e.rng=Sequence([3,1]);self.e.intro_stage([a,b],'아름다움')
        self.assertEqual((a.letter,b.letter),('A','B'));self.assertEqual(self.e.rng.faces,[])
    def test_starting_stat_pool_does_not_change_introduction_order(self):
        a,b=self.actor('X',stat_dice={'귀여움':99}),self.actor('Y')
        self.e.rng=Sequence([1,3]);self.e.intro_stage([a,b],'아름다움')
        self.assertEqual((a.letter,b.letter),('B','A'))
    def test_turn_start_excitement_only_and_clamps_zero_to_five(self):
        a=self.actor(moves=['헤롱헤롱']);a.excitement=4
        self.e.perform(a,'헤롱헤롱','귀여움',[],False,fixed_rolls=[2]*8)
        self.assertEqual((a.appeal,a.excitement),(8,5))
        self.e.clamp_ex(a,-99);self.assertEqual(a.excitement,0)
    def test_all_twenty_five_type_pairs_follow_ring(self):
        ring=['근사함','아름다움','귀여움','슬기로움','강인함']
        for i,move in enumerate(ring):
            for j,topic in enumerate(ring):
                distance=min(abs(i-j),5-abs(i-j))
                self.assertEqual(self.e.type_mod(move,topic)[0],{0:1,1:0,2:-1}[distance])
        for args in [('bad','근사함'),('근사함','bad')]:
            with self.assertRaises(ValueError):self.e.type_mod(*args)
    def test_contest_ignores_battle_daily_frequency_but_requires_learned_moves(self):
        a=self.actor(moves=['회복지령','기가임팩트'])
        self.assertEqual(self.rules.move('회복지령')['frequency'],'하루 x2')
        for _ in range(4):
            self.e.perform(a,'회복지령','근사함',[],False,fixed_rolls=[])
            self.e.perform(a,'기가임팩트','근사함',[],False,fixed_rolls=[])
        self.assertEqual(a.fumble,4)
        with self.assertRaises(ValueError):self.e.perform(a,'파괴광선','근사함',[],False)
    def test_invalid_excitement_or_duplicate_neighbor_aborts(self):
        for value in [-1,6,True,1.5]:
            a=self.actor();a.excitement=value
            with self.assertRaises(ValueError):self.e.perform(a,'연속자르기','근사함',[],False)
        a,b=self.actor(),self.actor('B')
        for neighbors in [[a],[b,b]]:
            with self.assertRaises(ValueError):self.e.perform(a,'연속자르기','근사함',neighbors,False)
    def test_actual_run_positions_turns_adjacency_and_center_match_every_table(self):
        for size in [3,4,5]:
            cs=[self.actor(str(i)) for i in range(size)];self.e.rng=Ones()
            visits=[]
            def choose(c,rnd,adj,center):
                visits.append((rnd,c.letter,tuple(x.letter for x in adj),center))
                return '연속자르기',0
            self.e.run(cs,'근사함',choose)
            table=self.rules.mech('contest/position-tables')[str(size)]
            expected=[]
            for rnd,row in enumerate(table['rounds'],1):
                for i in sorted(range(size),key=lambda i:table['turn_order_by_column'][i]):
                    expected.append((rnd,row[i],tuple(row[j] for j in [i-1,i+1] if 0<=j<size),table['turn_order_by_column'][i]==1))
            self.assertEqual(visits,expected)
            self.assertEqual(Counter(v[1] for v in visits),dict.fromkeys('ABCDE'[:size],size))
            self.assertEqual(Counter(v[1] for v in visits if v[3]),dict.fromkeys('ABCDE'[:size],1))
            pairs=Counter((v[1],other) for v in visits for other in v[2])
            self.assertEqual(set(pairs.values()),{2});self.assertEqual(len(pairs),size*(size-1))
    def test_position_tables_match_source_literal_and_visually_confirmed_center(self):
        expected={'5':([5,3,1,2,4],['ECABD','CDBEA','ABCDE','BEDAC','DAECB']), '4':([2,4,1,3],['BDAC','DCBA','ABCD','CADB']), '3':([3,1,2],['CAB','ABC','BCA'])}
        tables=self.rules.mech('contest/position-tables')
        for n,(order,rows) in expected.items():
            self.assertEqual(tables[n],{'turn_order_by_column':order,'rounds':[list(x) for x in rows]})
            self.assertEqual(order.index(1),{'5':2,'4':2,'3':1}[n])
    def test_round_expiration_clears_saving_grace_protection(self):
        cs=[self.actor(str(i)) for i in range(3)];self.e.rng=Ones()
        def choose(c,rnd,adj,center):
            if center:
                self.assertFalse(c.immune_fumble)
                for actor in cs:actor.immune_fumble=True
            return '연속자르기',0
        self.e.run(cs,'근사함',choose)

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
        def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    paths=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/common_action_checks.py','engine/gm_state.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/movement_actions.py','engine/weapon_actions.py','data/weapon-policy.json','engine/bandages.py','engine/crafting_activities.py','data/planter-policy.json','engine/capability_actions.py','engine/physical_limits.py','data/capability-policy.json','engine/temporary_hp.py','engine/contest_features.py','engine/action_points.py','engine/turn.py','engine/action_lifecycle.py','engine/contest.py','engine/ruleset.py','engine/engine.py','engine/skill_modifiers.py','engine/items.py','engine/pokemon_activities.py','engine/frequency.py','engine/common_checks.py','engine/resolution_transaction.py','tools/test_category3_contest_next.py','data/core-rules.json','data/lookup-tables.json','data/conditions.json','data/skill-check-policy.json','data/items-mech.json','data/items-llm.json','data/items-reviewed.json','data/contest-rules.json','data/rulesets.json','output/entities/moves.json','output/ruleunits.jsonl','input/ch08-contests.md','input/ch03-skills-edges-feats.md','input/ch09-equipment.md','output/source-audit/2026-10-10/ptu-core-1.05.pdf']
    paths += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
    paths += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
    paths += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

    paths += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

    paths += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['DOMAIN-039','DOMAIN-041','DOMAIN-042','DOMAIN-043'],'results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},'source_visual_review':{'pdf_page':265,'center_columns_zero_based':{'3':1,'4':2,'5':2},'reviewed':True,'stats_ring_pdf_page':262,'stats_ring_clockwise':['근사함','아름다움','귀여움','슬기로움','강인함'],'note':'Rendered and visually inspected the yellow columns and all position chart cells against the saved Korean table.'}}
    (ROOT/'output/category3-contest-next-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
