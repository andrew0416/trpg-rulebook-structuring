"""Whole scoped combat clauses; tests use existing Engine producers, never fake completion."""
import hashlib,json,re,sys,unittest
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
sys.path.insert(0,str(ROOT/'tools'))
from engine import Rules,Engine,Combatant
import effects as FX
import effects_ext as EXT
import turn as TURN
from synthetic_rule_fixture import register_synthetic
CLAUSES=['DOMAIN-010','DOMAIN-011','DOMAIN-012','DOMAIN-014','C3-EX-095','C3-EX-022','DOMAIN-018','DOMAIN-031','DOMAIN-019','C3-EX-026','DOMAIN-020','DOMAIN-028']
class FixedRng:
    def __init__(self,values):self.values=list(values)
    def randint(self,a,b):
        v=self.values.pop(0)
        assert type(v) is int and a<=v<=b,(a,b,v)
        return v
class CombatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=Rules(str(ROOT))
        register_synthetic(cls.r,'test/category3-damage',name='category3 damage component',kind='entity:move')
    def setUp(self):
        self.e=Engine(self.r,seed=420)
        self.a=self.actor('A');self.t=self.actor('T')
        self.a.side='party';self.t.side='wild';self.e.everyone=[self.a,self.t]
    def actor(self,name,kind='pokemon'):
        # These synthetic combat fixtures occupy one observed Medium cell.
        return Combatant(self.r,{'name':name,'kind':kind,'size':'중형','level':30,'stats':{'hp':60,'atk':20,'def':10,'spa':20,'spd':15,'spe':5},'moves':['move/바다회오리','move/화염방사'],'skills':{'전투':'전문'},'movement':{'land':6}})
    def move(self,db=4,**changes):
        return dict({'id':'test/category3-damage','name':'damage component','class':'물리','type':'노말','ac':4,'damage_base':db},**changes)
    def apply(self,effect,target=None):
        c=target or self.t
        return FX.run_effects(self.e,self.a,c,[effect],{'hit':True,'attacker':self.a,'target':c,'engine':self.e},'category3 source effect')
    def test_source_scopes_match_exact_excerpts(self):
        register=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))
        for entry in register['entries']:
            if entry['id'] not in CLAUSES:continue
            source=entry['source_snapshot']
            for a in source.get('anchors',source.get('source_anchors',[])):
                lines=(ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines()
                actual='\n'.join(lines[a.get('start',a.get('start_line'))-1:a.get('end',a.get('end_line'))])
                self.assertEqual(actual,a['excerpt'],entry['id'])
    def test_hp_formulas_and_stat_evasion_sources(self):
        self.assertEqual(self.a.base_max_hp,220)
        self.assertEqual(self.actor('trainer','trainer').base_max_hp,250)
        self.assertEqual([self.t.evasion(k) for k in ('물리','특수','변화')],[2,3,1])
        self.t.stats['spe']=25
        self.assertEqual([self.t.evasion(k) for k in ('물리','특수','변화')],[5,5,5])
    def test_stat_cap_extra_cap_and_negative_evasion_floor(self):
        self.t.stats['def']=100
        self.assertEqual(self.t.evasion('물리'),6)
        self.apply({'type':'evasion_mod','value':9})
        self.assertEqual((self.t.evasion_mod,self.t.evasion('물리')),(6,9))
        self.apply({'type':'evasion_mod','value':-30})
        self.assertEqual((self.t.evasion_mod,self.t.evasion('물리')) ,(-6,0))
        self.t.stats['def']=0;self.t.stats['spe']=0
        self.assertEqual(self.t.evasion('물리'),0)
    def test_evasion_follows_targeted_defense_stat_for_actual_psyshock(self):
        self.t.stats.update({'def':30,'spd':5,'spe':0})
        move=self.r.move('move/사이코쇼크')
        self.assertFalse(self.e.accuracy_check(self.a,self.t,move,fixed_roll=move['ac']+5)[0])
        self.assertTrue(self.e.accuracy_check(self.a,self.t,move,fixed_roll=move['ac']+6)[0])
        self.t.stats.update({'def':5,'spd':30})
        self.assertTrue(self.e.accuracy_check(self.a,self.t,move,fixed_roll=move['ac']+1)[0])
    def test_accuracy_stage_limits_and_direct_addition(self):
        self.apply({'type':'accuracy_mod','value':20},self.a)
        self.assertEqual(self.a.accuracy_stage,6)
        self.assertTrue(self.e.accuracy_check(self.a,self.t,self.move(ac=8),fixed_roll=4)[0])
        self.apply({'type':'accuracy_mod','value':-50},self.a)
        self.assertEqual(self.a.accuracy_stage,-6)
        self.assertFalse(self.e.accuracy_check(self.a,self.t,self.move(),fixed_roll=10)[0])
    def test_unconscious_and_vulnerable_receive_no_evasion(self):
        self.t.evasion_mod=6;self.t.hp=0
        self.assertEqual(self.t.evasion('물리'),0)
        self.t.hp=100;self.e.apply_status(self.t,'취약')
        self.assertEqual(self.t.evasion('물리'),0)
        self.t.conditions.clear()
        for condition in ('실명','잠듦','기절','얼음','넘어짐'):
            self.t.conditions.add(condition)
            for category in ('물리','특수','변화'):
                self.assertEqual(self.t.evasion(category),0,condition)
            self.t.conditions.remove(condition)
            self.assertGreater(self.t.evasion('물리'),0,condition)
    def test_reset_stages_clears_accuracy_and_bonus_evasion(self):
        self.t.stages['atk']=4;self.t.accuracy_stage=3;self.t.evasion_mod=5
        self.apply({'type':'reset_stages'})
        self.assertEqual(sum(self.t.stages.values()),0)
        self.assertEqual((self.t.accuracy_stage,self.t.evasion_mod),(0,0))
    def test_stage_table_all_stats_and_bounds(self):
        self.assertNotIn('hp',self.t.stages)
        for stat in ('atk','def','spa','spd','spe'):
            self.t.stats[stat]=20
            for stage,mult in [(-6,.4),(-5,.5),(-4,.6),(-3,.7),(-2,.8),(-1,.9),(0,1),(1,1.2),(2,1.4),(3,1.6),(4,1.8),(5,2),(6,2.2)]:
                self.t.stages[stat]=stage
                self.assertEqual(self.t.staged(stat),round(20*mult))
            self.e.change_stage(self.t,stat,100);self.assertEqual(self.t.stages[stat],6)
            self.e.change_stage(self.t,stat,-100);self.assertEqual(self.t.stages[stat],-6)
    def test_speed_stage_movement_all_capabilities_and_lower_bound(self):
        self.e.gm.set_movement_capabilities(self.t,{'land':6,'sky':8},basis='current',reason='explicit current capability observation')
        self.t.stages['spe']=6;self.assertEqual(self.e.move_profile(self.t),(11,'공중/부유'))
        self.t.stages['spe']=-6;self.assertEqual(self.e.move_profile(self.t),(5,'공중/부유'))
        self.e.gm.set_movement_capabilities(self.t,{'land':4},basis='current',reason='explicit current capability observation');self.assertEqual(self.e.move_profile(self.t),(2,'육상'))
        self.t.stages['spe']=-1;self.assertEqual(self.e.move_profile(self.t),(3,'육상'))
    def test_all_movement_capabilities_apply_speed_stages_without_creating_absent_ones(self):
        self.e.gm.set_movement_capabilities(self.t,{'land':4,'sky':4,'levitate':4,'swim':4,'burrow':4,'teleport':4,'power':9},basis='current',reason='explicit current capability observation')
        for mode in ('land','sky','levitate','swim','burrow','teleport'):
            self.t.stages['spe']=6;self.assertEqual(self.e.move_profile(self.t,mode)[0],7)
            self.t.stages['spe']=-6;self.assertEqual(self.e.move_profile(self.t,mode)[0],2)
        self.t.spec['movement']['burrow']=0
        with self.assertRaises(ValueError):self.e.move_profile(self.t,'burrow')
        with self.assertRaises(ValueError):self.e.move_profile(self.t,'power')
    def test_selected_swim_speed_reaches_actual_movement_path(self):
        from grid import Grid,cheb
        self.a.spec['movement']={'land':2,'swim':6};self.a.stages['spe']=6
        self.e.grid=Grid(30,3);self.a.pos=(0,0);self.t.pos=(20,0)
        TURN.reset_budget(self.e,self.a)
        self.e.approach(self.a,self.t,movement_mode='swim')
        self.assertEqual(cheb((0,0),self.a.pos),9)
        self.assertEqual(self.a.budget['shift'],0)
    def test_unpossessed_movement_does_not_consume_shift_and_teleport_is_not_walking(self):
        from grid import Grid
        self.e.grid=Grid(30,3);self.a.pos=(0,0);self.t.pos=(20,0)
        TURN.reset_budget(self.e,self.a);budget=dict(self.a.budget)
        with self.assertRaises(ValueError):self.e.approach(self.a,self.t,movement_mode='burrow')
        self.assertEqual(self.a.budget,budget)
        self.a.spec['movement']['teleport']=4
        with self.assertRaises(ValueError):self.e.approach(self.a,self.t,movement_mode='teleport')
        self.assertEqual(self.a.budget,budget);self.assertEqual(self.a.pos,(0,0))
    def test_switch_effect_and_encounter_end_reset_stages(self):
        for actor in (self.a,self.t):
            actor.stages['atk']=3;actor.accuracy_stage=2;actor.evasion_mod=4
        self.apply({'type':'switch_out','target':'self'},self.a)
        self.assertFalse(self.a.on_field)
        self.assertEqual((self.a.stages['atk'],self.a.accuracy_stage,self.a.evasion_mod),(0,0,0))
        self.e.end_encounter([self.t])
        self.assertEqual((self.t.stages['atk'],self.t.accuracy_stage,self.t.evasion_mod),(0,0,0))
    def test_accuracy_below_equal_natural_one_and_twenty(self):
        mv=self.move(ac=4)
        self.assertFalse(self.e.accuracy_check(self.a,self.t,mv,fixed_roll=5)[0])
        self.assertTrue(self.e.accuracy_check(self.a,self.t,mv,fixed_roll=6)[0])
        self.assertFalse(self.e.accuracy_check(self.a,self.t,mv,fixed_roll=1,situational=100)[0])
        hit,nat,crit=self.e.accuracy_check(self.a,self.t,mv,fixed_roll=20,situational=-100)
        self.assertEqual((hit,nat,crit),(True,20,True))
    def test_evasion_waiver_still_requires_base_ac(self):
        self.assertFalse(self.e.accuracy_check(self.a,self.t,self.move(ac=6),waive=True,fixed_roll=5)[0])
        self.assertTrue(self.e.accuracy_check(self.a,self.t,self.move(ac=6),waive=True,fixed_roll=6)[0])
    def test_natural_face_not_modified_for_critical_or_effect_range(self):
        self.a.accuracy_stage=4
        self.assertFalse(self.e.accuracy_check(self.a,self.t,self.move(),fixed_roll=16)[2])
        self.a.modifiers.append({'type':'crit_range','min':16})
        self.assertTrue(self.e.accuracy_check(self.a,self.t,self.move(),fixed_roll=16)[2])
        self.e.rng=FixedRng([16])
        self.e.use_move(self.a,self.t,'move/화염방사',set_damage=True)
        self.assertNotIn('화상',self.t.conditions)
    def test_invalid_accuracy_face_rejected_before_random_or_state(self):
        before=self.e.rng.getstate()
        for face in (0,21,True,1.0,'20'):
            with self.assertRaises(ValueError):self.e.accuracy_check(self.a,self.t,self.move(),fixed_roll=face)
        self.assertEqual(before,self.e.rng.getstate())
    def test_damage_chart_exact_all_28_rows_and_both_execution_modes(self):
        text=(ROOT/'input/ch07-combat.md').read_text(encoding='utf-8').splitlines()
        chart=self.r.mech('combat/damage-chart')['by_damage_base'];self.t.stats['def']=1
        self.assertEqual(self.t.staged('def'),1)  # ch05:54 minimum; the table remains exact.
        seen=set()
        for line in text[335:349]:
            cells=[v.strip().replace('**','') for v in line.strip('|').split('|')]
            for di,vi,si,sv in [(0,1,4,5),(2,3,6,7)]:
                db=int(cells[di]);seen.add(db)
                self.assertEqual(cells[si],str(db))
                low,mid,high=map(int,cells[sv].split('/'))
                self.assertEqual(chart[str(db)],{'dice':cells[vi],'set':{'low':low,'mid':mid,'high':high}})
                n,faces,bonus=map(int,re.fullmatch(r'(\d+)d(\d+)\+(\d+)',cells[vi]).groups())
                mv=self.move(db)
                self.assertEqual(self.e.roll_damage(self.a,self.t,mv,set_damage=True),mid+20-1)
                self.assertEqual(self.e.roll_damage(self.a,self.t,mv,fixed_dice=[1]*n),low+20-1)
                self.assertEqual(self.e.roll_damage(self.a,self.t,mv,fixed_dice=[faces]*n),high+20-1)
                self.assertEqual(self.e.roll_damage(self.a,self.t,mv,crit=True,set_damage=True),2*mid+20-1)
        self.assertEqual(seen,set(range(1,29)))
    def test_fixed_damage_dice_validate_count_faces_and_critical_count(self):
        mv=self.move(6)
        for dice in ([1], [1,7], [True,1], [1.0,1], '11'):
            with self.assertRaises(ValueError):self.e.roll_damage(self.a,self.t,mv,fixed_dice=dice)
        with self.assertRaises(ValueError):self.e.roll_damage(self.a,self.t,mv,crit=True,fixed_dice=[1,1])
        self.assertEqual(self.e.roll_damage(self.a,self.t,mv,crit=True,fixed_dice=[1]*4),30)
    def test_ticks_use_true_max_hp_ignoring_injury_and_temporary_hp(self):
        self.t.injuries=3;self.t.temp_hp=999
        self.assertEqual(self.e.tick(self.t),22)
        self.assertEqual(self.t.base_max_hp,220)
    def test_vortex_applies_via_learned_native_move_and_frequency(self):
        self.e.rng=FixedRng([10])
        dealt=self.e.use_move(self.a,self.t,'move/바다회오리',set_damage=True)
        self.assertGreater(dealt,0)
        self.assertTrue({'조이기','둔화','수렁'}<=self.t.conditions)
        self.assertEqual(self.t.custom_conditions['vortex']['ends'],0)
        self.assertEqual(self.a.move_uses['move/바다회오리'],1)
        self.assertEqual(self.e.move_profile(self.t),(3,'육상'))
        result=EXT.h_switch_out(self.e,self.t,self.a,{}, {})
        self.assertIsNotNone(result);self.assertTrue(self.t.on_field)
    def test_vortex_strict_thresholds_and_fifth_turn_no_roll(self):
        self.e.apply_status(self.t,'조이기');hp=self.t.hp
        self.e.rng=FixedRng([20,14,8,2])
        for index in range(5):
            self.e.start_of_turn(self.t)
            self.assertEqual(self.t.hp,hp-(index+1)*22)
            self.e.end_of_turn(self.t)
            self.assertEqual('조이기' in self.t.conditions,index<4)
        self.assertEqual(self.e.rng.values,[])
        self.assertFalse({'조이기','둔화','수렁'}&self.t.conditions)
    def test_vortex_second_turn_above_threshold_escapes(self):
        self.e.apply_status(self.t,'조이기');self.e.rng=FixedRng([20,15])
        self.e.start_of_turn(self.t);self.e.end_of_turn(self.t)
        self.assertIn('조이기',self.t.conditions)
        self.e.start_of_turn(self.t);self.e.end_of_turn(self.t)
        self.assertNotIn('조이기',self.t.conditions)
    def test_vortex_cure_preserves_independent_conditions(self):
        self.e.apply_status(self.t,'둔화');self.e.apply_status(self.t,'조이기')
        self.e.apply_status(self.t,'수렁')
        self.e.cure_status(self.t,'조이기')
        self.assertTrue({'둔화','수렁'}<=self.t.conditions)
        self.assertNotIn('vortex',self.t.custom_conditions)
    def test_vortex_duplicate_does_not_reset_timer_and_ghost_trap_immunity(self):
        self.t.types=['고스트'];self.e.apply_status(self.t,'조이기')
        self.assertNotIn('수렁',self.t.conditions)
        self.t.custom_conditions['vortex']['ends']=2
        self.assertFalse(self.e.apply_status(self.t,'조이기'))
        self.assertEqual(self.t.custom_conditions['vortex']['ends'],2)
    def demoralizer(self):
        self.a=self.actor('Trainer','trainer');self.a.side='party'
        self.a.spec['edges']=['edge/사기저하'];self.a.spec['skills']['협박']='숙련'
        self.a.moves.append('move/째려보기')
        self.e.everyone=[self.a,self.t]
    def test_demoralize_status_19_critical_and_enemy_vulnerable(self):
        self.demoralizer();self.e.rng=FixedRng([19])
        self.e.use_move(self.a,self.t,'move/째려보기')
        self.assertIn('취약',self.t.conditions)
        self.assertEqual(self.a.move_uses['move/째려보기'],1)
    def test_demoralize_status_threshold_extends_critical_range(self):
        self.demoralizer();self.a.modifiers.append({'type':'crit_range','min':17})
        move=self.r.move('move/째려보기')
        self.assertFalse(self.e.accuracy_check(self.a,self.t,move,fixed_roll=15)[2])
        self.assertTrue(self.e.accuracy_check(self.a,self.t,move,fixed_roll=16)[2])
    def test_demoralize_without_owner_or_without_natural_roll_no_status_critical(self):
        self.demoralizer();self.a.spec['edges']=[]
        move=self.r.move('move/째려보기')
        self.assertFalse(self.e.accuracy_check(self.a,self.t,move,fixed_roll=20)[2])
        self.a.spec['edges']=['사기저하']
        self.assertFalse(EXT.crit_hook(self.e,self.a,self.t,move,True,False,natural=None))
    def test_demoralize_damaging_critical_and_friendly_target_exclusion(self):
        self.demoralizer();self.e.rng=FixedRng([20])
        self.e.use_move(self.a,self.t,'struggle',set_damage=True)
        self.assertIn('취약',self.t.conditions)
        self.e.cure_status(self.t,'취약');self.t.side='party'
        EXT.after_move(self.e,self.a,self.t,self.move(),{}, {'hit':True,'crit':True})
        self.assertNotIn('취약',self.t.conditions)
    def test_demoralize_miss_and_ordinary_hit_do_not_inflict_vulnerability(self):
        self.demoralizer();move=self.r.move('move/째려보기')
        self.assertFalse(self.e.accuracy_check(self.a,self.t,move,fixed_roll=1)[0])
        self.assertFalse(self.e.accuracy_check(self.a,self.t,move,fixed_roll=18)[2])
        EXT.after_move(self.e,self.a,self.t,move,{}, {'hit':False,'crit':True})
        self.assertNotIn('취약',self.t.conditions)
    def test_demoralize_prerequisite_rejected_before_cost_and_rng(self):
        self.demoralizer();self.a.spec['skills']['협박']='초보'
        TURN.reset_budget(self.e,self.a)
        before=(dict(self.a.budget),dict(self.a.move_uses),self.e.rng.getstate())
        with self.assertRaises(ValueError):self.e.use_move(self.a,self.t,'move/째려보기')
        self.assertEqual(before,(dict(self.a.budget),dict(self.a.move_uses),self.e.rng.getstate()))
    def test_double_strike_pending_before_any_cost_rng_or_damage(self):
        from test_book_martial_artist import MartialArtistTests
        fixture=MartialArtistTests();fixture.rules=self.r;fixture.setup()
        fixture.e.gm.set_move(fixture.a,'move/더블어택',reason='actual learned printed Double Strike Move')
        fixture.start();hp=fixture.t.hp
        fixture.use('더블어택',face=12)
        self.assertLess(fixture.t.hp,hp)
        self.assertEqual(fixture.a.move_uses['move/더블어택'],1)
        fixture.a.registry.append({'type':'gain_keyword','keyword':'이단타격'})
        before=(dict(fixture.a.budget),dict(fixture.a.move_uses),fixture.e.rng.getstate(),fixture.t.hp)
        with self.assertRaisesRegex(ValueError,'Double Strike combined damage'):
            fixture.e.use_move(fixture.a,fixture.t,'struggle',set_damage=True)
        self.assertEqual(before,(dict(fixture.a.budget),dict(fixture.a.move_uses),fixture.e.rng.getstate(),fixture.t.hp))
    def test_double_strike_pending_before_automatic_approach_cost(self):
        from test_book_martial_artist import MartialArtistTests
        fixture=MartialArtistTests();fixture.rules=self.r;fixture.setup();fixture.start()
        fixture.e.gm.set_position(fixture.t,(10,3),reason='actual remote target')
        fixture.a.registry.append({'type':'gain_keyword','keyword':'이단타격'})
        before=(fixture.a.pos,dict(fixture.a.budget),fixture.e.rng.getstate(),fixture.t.hp)
        with self.assertRaisesRegex(ValueError,'Double Strike combined damage'):
            fixture.e.use_move_on(fixture.a,fixture.t,'struggle',fixture.e.everyone)
        self.assertEqual(before,(fixture.a.pos,dict(fixture.a.budget),fixture.e.rng.getstate(),fixture.t.hp))
    def test_demoralize_selected_variant_cannot_inherit_core_policy(self):
        from unittest.mock import patch
        self.demoralizer()
        real=self.r._selected_rule
        def variant(uid,*a,**k):return 'edge/사기저하-다른판본' if uid=='edge/사기저하' else real(uid,*a,**k)
        before=self.e.rng.getstate()
        with patch.object(self.r,'_selected_rule',side_effect=variant):
            with self.assertRaises(ValueError):self.e.accuracy_check(self.a,self.t,self.r.move('move/째려보기'))
        self.assertEqual(self.e.rng.getstate(),before)
    def test_demoralize_requires_trainer_and_unique_ownership(self):
        self.demoralizer();self.a.kind='pokemon'
        with self.assertRaises(ValueError):EXT.validate_combat_edges(self.e,self.a)
        self.a.kind='trainer';self.a.spec['edges'].append('Demoralize')
        with self.assertRaises(ValueError):EXT.validate_combat_edges(self.e,self.a)
    def prepare_disengage(self):
        from grid import Grid
        self.e.grid=Grid(10,10);self.a.pos=(3,3);self.t.pos=(4,3)
        self.e.start_round([self.a,self.t]);self.e.start_of_turn(self.a)
    def test_disengage_spends_shift_moves_one_metre_without_opportunity_attack(self):
        self.prepare_disengage();hp=self.a.hp
        self.assertTrue(self.e.disengage(self.a,(2,3)))
        self.assertEqual(self.a.pos,(2,3));self.assertEqual(self.a.hp,hp)
        self.assertEqual(self.a.budget,{'standard':1,'shift':0,'swift':1})
        self.assertFalse(getattr(self.t,'aoo_used',False))
        self.assertFalse(any('[기회 공격]' in l for l in self.e.log_lines))
    def test_disengage_does_not_grant_a_second_movement_action(self):
        self.prepare_disengage();self.assertTrue(self.e.disengage(self.a,(2,3)))
        self.assertFalse(self.e.disengage(self.a,(1,3)))
        self.assertEqual(self.a.pos,(2,3));self.assertEqual(self.a.budget['standard'],1)
    def test_disengage_invalid_distance_blocked_occupied_no_cost(self):
        self.prepare_disengage();self.e.grid.blocking.add((2,3));before=dict(self.a.budget)
        for dest in [(0,3),(3,3),(2,3),(4,3),(True,3)]:
            with self.assertRaises(ValueError):self.e.disengage(self.a,dest)
        self.assertEqual(self.a.budget,before);self.assertEqual(self.a.pos,(3,3))
    def test_disengage_obeys_unconscious_and_movement_prohibitions(self):
        self.prepare_disengage();before=dict(self.a.budget)
        for status in ('구속','넘어짐'):
            self.e.apply_status(self.a,status)
            self.assertFalse(self.e.disengage(self.a,(2,3)))
            self.e.cure_status(self.a,status)
        self.a.hp=0;self.assertFalse(self.e.disengage(self.a,(2,3)))
        self.assertEqual(self.a.budget,before);self.assertEqual(self.a.pos,(3,3))
    def test_disengage_trainer_can_fund_shift_by_unused_standard_without_extra_move(self):
        self.a=self.actor('Trainer','trainer');self.a.side='party';self.e.everyone=[self.a,self.t]
        self.prepare_disengage();self.assertTrue(TURN.spend(self.e,self.a,'shift','nonmovement capability'))
        self.assertTrue(self.e.disengage(self.a,(2,3)))
        self.assertEqual(self.a.budget,{'standard':0,'shift':0,'swift':1})
    def test_disengage_reuses_terrain_and_alternating_diagonal_cost(self):
        self.prepare_disengage();self.e.grid.slow.add((2,3));before=dict(self.a.budget)
        with self.assertRaises(ValueError):self.e.disengage(self.a,(2,3))
        self.a._diagonal_steps=1
        with self.assertRaises(ValueError):self.e.disengage(self.a,(2,2))
        self.assertEqual(self.a.budget,before)
        self.a._diagonal_steps=0
        self.assertTrue(self.e.disengage(self.a,(2,2)))
        self.assertEqual(self.a._diagonal_steps,1)
    def test_temporary_hp_uses_highest_grant_without_refreshing_lower_value(self):
        self.apply({'type':'temp_hp','value':10})
        self.e.advance_time(100)
        self.apply({'type':'temp_hp','value':8})
        self.assertEqual(self.t.temp_hp,10)
        self.e.advance_time(199);self.assertEqual(self.t.temp_hp,10)
        self.e.advance_time(1);self.assertEqual(self.t.temp_hp,0)
        self.apply({'type':'temp_hp','value':10});self.e.advance_time(100)
        self.apply({'type':'temp_hp','value':15});self.e.advance_time(299)
        self.assertEqual(self.t.temp_hp,15)
        self.e.advance_time(1);self.assertEqual(self.t.temp_hp,0)
    def test_temporary_hp_absorbs_damage_and_ordinary_loss_before_real_hp(self):
        hp=self.t.hp
        self.apply({'type':'temp_hp','value':10})
        self.e.take_damage(self.t,7)
        self.assertEqual((self.t.hp,self.t.temp_hp),(hp,3))
        self.e.lose_hp(self.t,5)
        self.assertEqual((self.t.hp,self.t.temp_hp),(hp-2,0))
    def test_temporary_hp_does_not_change_real_max_percentage_or_restore_hp(self):
        self.t.hp=1;self.t.injuries=3
        self.apply({'type':'temp_hp','value':50})
        self.assertEqual((self.t.hp,self.t.base_max_hp,self.e.tick(self.t)),(1,220,22))
        self.apply({'type':'cure_all_status'})
        self.assertEqual(self.t.temp_hp,50)
        self.t.abilities=['맹화'];self.e.register_abilities(self.t)
        move=self.r.move('move/불꽃세례')
        low=self.e.roll_damage(self.t,self.a,move,set_damage=True)
        self.t.hp=self.t.base_max_hp
        high=self.e.roll_damage(self.t,self.a,move,set_damage=True)
        self.assertEqual(low-high,5)
    def test_temporary_hp_recall_clears_and_trapped_failed_recall_preserves(self):
        self.apply({'type':'temp_hp','value':20})
        self.e.apply_status(self.t,'수렁')
        EXT.h_switch_out(self.e,self.t,self.a,{}, {})
        self.assertEqual(self.t.temp_hp,20);self.assertTrue(self.t.on_field)
        self.e.cure_status(self.t,'수렁')
        EXT.h_switch_out(self.e,self.t,self.a,{}, {})
        self.assertEqual(self.t.temp_hp,0);self.assertFalse(self.t.on_field)
    def test_temporary_hp_unknown_combat_birth_does_not_age_outside_clock(self):
        self.e.start_round([self.a,self.t])
        self.apply({'type':'temp_hp','value':20})
        self.e.end_round();self.e.advance_time(600)
        self.assertEqual(self.t.temp_hp,20)
        self.e.take_damage(self.t,5);self.assertEqual(self.t.temp_hp,15)
        self.e.end_encounter();self.e.advance_time(299)
        self.assertEqual(self.t.temp_hp,15)
        self.e.advance_time(1);self.assertEqual(self.t.temp_hp,0)
    def test_temporary_hp_explicit_combat_timestamp_still_waits_for_outside_time(self):
        self.e.start_round([self.a,self.t])
        FX.run_effects(self.e,self.a,self.t,[{'type':'temp_hp','value':20}],
            {'hit':True,'attacker':self.a,'target':self.t,'engine':self.e,'round_offset_seconds':7},'test source effect')
        self.e.end_round();self.e.advance_time(600)
        self.assertEqual(self.t.temp_hp,20)
        self.e.end_encounter();self.e.advance_time(299)
        self.assertEqual(self.t.temp_hp,20)
        self.e.advance_time(1);self.assertEqual(self.t.temp_hp,0)
    def test_temporary_hp_unknown_final_combat_round_cannot_expire_outside_clock(self):
        self.apply({'type':'temp_hp','value':20})
        self.e.start_round([self.a,self.t]);self.e.end_encounter()
        self.e.advance_time(290);self.e.take_damage(self.t,5)
        self.assertEqual(self.t.temp_hp,15)
        self.e.advance_time(10);self.assertEqual(self.t.temp_hp,0)
    def test_temporary_hp_from_owned_native_ability_and_actual_move_expires(self):
        self.t.spec.setdefault('items',{})['초코바']=1
        self.e.use_item(self.t,'초코바',duration_minutes=1,duration_reason='actual food buff before theft')
        self.a.abilities=['꿀도둑'];self.a.spec['abilities']=['꿀도둑']
        self.a.moves.append('move/벌레먹기');self.e.register_abilities(self.a)
        self.e.start_round([self.a,self.t]);self.e.start_of_turn(self.a)
        self.e.rng=FixedRng([10]);self.e.use_move(self.a,self.t,'move/벌레먹기',set_damage=True)
        self.assertEqual(self.a.temp_hp,self.e.tick(self.a))
        self.assertEqual(self.a.move_uses['move/벌레먹기'],1)
        self.e.end_of_turn(self.a);self.e.end_round()
        self.e.advance_time(300);self.assertGreater(self.a.temp_hp,0)
        self.e.end_encounter();self.e.advance_time(300);self.assertEqual(self.a.temp_hp,0)
    def test_temporary_hp_outside_combat_expires_at_exact_five_minutes(self):
        self.apply({'type':'temp_hp','value':20})
        self.e.advance_time(299);self.assertEqual(self.t.temp_hp,20)
        state=self.t.custom_conditions['temporary_hp_lifetime']
        self.assertEqual(state['clock_basis'],'out_of_combat_seconds')
        self.assertEqual((state['minimum_seconds'],state['maximum_seconds']),(1,1))
        self.e.advance_time(1);self.assertEqual(self.t.temp_hp,0)
        self.assertNotIn('temporary_hp_lifetime',self.t.custom_conditions)
    def test_temporary_hp_gm_override_has_explicit_origin_and_optional_time(self):
        self.e.gm.set_temp_hp(self.t,9,reason='scenario setup')
        state=self.t.custom_conditions['temporary_hp_lifetime']
        self.assertEqual((state['kind'],state['expiry_policy']),('gm_override','explicit_unbounded'))
        self.e.advance_time(600);self.assertEqual(self.t.temp_hp,9)
        self.e.gm.set_temp_hp(self.t,5,duration_seconds=20)
        self.e.advance_time(19);self.assertEqual(self.t.temp_hp,5)
        self.e.advance_time(1);self.assertEqual(self.t.temp_hp,0)
        self.e.gm.set_temp_hp(self.t,7);self.e.gm.recall(self.t)
        self.assertEqual(self.t.temp_hp,0)
    def test_temporary_hp_pending_also_guards_heavy_direct_attack_and_action_paths(self):
        import heavy_injury_adapter as HEAVY
        import heavy_standard_adapter as STANDARD
        self.e.start_round([self.a,self.t]);self.apply({'type':'temp_hp','value':20})
        self.t.custom_conditions['temporary_hp_lifetime'].pop('clock_basis')
        self.t.custom_conditions['temporary_hp_lifetime'].pop('contributions')
        self.e.end_round();self.e.advance_time(290)
        move=self.r.move('struggle');mm,_=self.r.move_mech('struggle')
        before=(self.t.hp,self.t.temp_hp,self.t.injuries)
        with self.assertRaisesRegex(ValueError,'temporary HP expiry'):
            HEAVY.apply_attack_damage(self.e,self.a,self.t,5,move,producer=HEAVY.Producer.SECOND_HIT,remainder='test')
        with self.assertRaisesRegex(ValueError,'temporary HP expiry'):
            STANDARD.diagnose(self.e,self.a,self.t,move,mm,True)
        self.assertEqual(before,(self.t.hp,self.t.temp_hp,self.t.injuries))
    def prepare_disarm(self, trainer_target=False):
        from grid import Grid
        if trainer_target:self.t=self.actor('Trainer target','trainer');self.t.side='wild'
        self.e.everyone=[self.a,self.t];self.e.grid=Grid(5,5)
        self.a.pos=(1,1);self.t.pos=(2,1)
        self.e.start_round([self.a,self.t]);self.e.start_of_turn(self.a)
    def disarm_success_options(self, **extra):
        return dict(attacker_skill='전투',defender_skill='전투',fixed_accuracy=20,
            challenger_options={'fixed':[6]*5},defender_options={'fixed':[1]*5},**extra)
    def test_disarm_actual_pokemon_held_item_drops_after_standard_accuracy_opposed(self):
        self.prepare_disarm();self.t.item='오랭열매'
        self.assertTrue(self.e.disarm(self.a,self.t,**self.disarm_success_options()))
        self.assertIsNone(self.t.item);self.assertEqual(self.a.budget['standard'],0)
        self.assertEqual(self.e.ground_items[-1]['item'],'오랭열매')
        self.assertEqual(self.e.ground_items[-1]['position'],self.t.pos)
        self.assertEqual(self.a.move_uses,{})
    def test_disarm_registered_item_preserves_name_and_physical_identity(self):
        import items as ITEMS,world_entities as WORLD
        self.prepare_disarm()
        WORLD.register_object(self.e,'actual-disarmed-claw',location={'kind':'unknown'},reason='actual physical equipment',kind='item_instance',item_rule_id='item/선제공격손톱',owner_id=self.t.entity_id)
        ITEMS.equip_held(self.e,self.t,'선제공격손톱',source_instance_id='actual-disarmed-claw')
        self.assertTrue(self.e.disarm(self.a,self.t,**self.disarm_success_options()))
        row=self.e.ground_items[-1]
        self.assertEqual((row['item'],row['instance_id']),('선제공격손톱','actual-disarmed-claw'))
        obj=self.e._physical_objects['actual-disarmed-claw']
        self.assertIsNone(obj.get('equipped_by'));self.assertEqual(obj['location'],WORLD.location_of(self.t))
    def test_disarm_miss_spends_standard_but_no_opposed_rng_or_drop(self):
        self.prepare_disarm();self.t.item='오랭열매';before=self.e.rng.getstate()
        opts=self.disarm_success_options();opts['fixed_accuracy']=1
        self.assertFalse(self.e.disarm(self.a,self.t,**opts))
        self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.t.item,'오랭열매')
        self.assertEqual(self.e.rng.getstate(),before)
    def test_disarm_defender_wins_tie_and_each_side_selects_combat_or_stealth(self):
        self.prepare_disarm();self.t.item='오랭열매'
        self.a.spec['skills']['은신']='미숙';self.t.spec['skills']['은신']='미숙'
        self.assertFalse(self.e.disarm(self.a,self.t,attacker_skill='은신',defender_skill='은신',fixed_accuracy=20,
            challenger_options={'fixed':[3,3]},defender_options={'fixed':[3,3]}))
        self.assertEqual(self.t.item,'오랭열매');self.assertEqual(self.a.budget['standard'],0)
    def test_disarm_invalid_skill_range_item_or_roll_has_no_cost(self):
        self.prepare_disarm();self.t.item='오랭열매'
        before=(dict(self.a.budget),self.e.rng.getstate())
        for changed in ({'attacker_skill':'곡예'},{'item_name':'없는 도구'},{'fixed_accuracy':True}):
            opts=self.disarm_success_options();opts.update(changed)
            with self.assertRaises(ValueError):self.e.disarm(self.a,self.t,**opts)
        self.t.pos=(4,4)
        with self.assertRaises(ValueError):self.e.disarm(self.a,self.t,**self.disarm_success_options())
        self.assertEqual(before,(dict(self.a.budget),self.e.rng.getstate()))
    def test_disarm_trainer_hand_item_loses_its_passive_and_body_item_ineligible(self):
        import items
        self.prepare_disarm(trainer_target=True)
        self.t.item='소형 방패';items.register_item(self.e,self.t)
        self.assertEqual(self.t.evasion_mod,1)
        self.assertTrue(self.e.disarm(self.a,self.t,**self.disarm_success_options()))
        self.assertEqual(self.t.evasion_mod,0);self.assertFalse(self.t._item_reg)
        self.assertEqual(self.e.ground_items[-1]['item'],'소형 방패')
    def test_disarm_weapon_removes_only_granted_moves_and_snapshot_restores(self):
        self.prepare_disarm(trainer_target=True)
        self.t.moves.append('move/강타!') if 'move/강타!' in self.r.moves else None
        self.t.spec['skills']['전투']='달인'
        mid=TURN.equip_weapon(self.e,self.t,{'name':'검증 봉','kind':'대형 근접무기','grade':'좋음','moves':['백스윙','강타']})
        record=self.t.custom_conditions['equipped_weapons'][mid]
        learned=next(m for m in record['available_moves'] if m!=mid)
        self.e.gm.set_move(self.t,learned,True,'independently acquired after equip')
        self.e.gm.snapshot('before-disarm')
        opts=self.disarm_success_options(item_name='검증 봉');opts['defender_options']['fixed']=[1]*6
        self.assertTrue(self.e.disarm(self.a,self.t,**opts))
        self.assertNotIn(mid,self.t.moves);self.assertIn(learned,self.t.moves)
        self.assertIsNone(self.t.weapon);self.assertEqual(len(self.e.ground_items),1)
        self.e.gm.restore('before-disarm')
        self.assertIn(mid,self.t.moves);self.assertEqual(self.t.weapon['name'],'검증 봉')
        self.assertFalse(hasattr(self.e,'ground_items'))
    def test_weapon_slot_occupancy_and_rank_grants_are_real(self):
        import items
        tr=self.actor('weapon-owner','trainer');tr.spec['skills']['전투']='숙련'
        mid=TURN.equip_weapon(self.e,tr,{'name':'숙련 봉','kind':'대형 근접무기','grade':'좋음','moves':['백스윙','강타']})
        ledger=tr.custom_conditions['equipped_weapons']
        self.assertEqual(ledger[mid]['slots'],['주요손','반대손'])
        self.assertEqual(len(ledger[mid]['available_moves']),2)
        before=list(tr.moves)
        with self.assertRaises(ValueError):TURN.equip_weapon(self.e,tr,{'name':'겹친 칼','kind':'소형 근접무기','grade':'조잡'})
        self.assertEqual(tr.moves,before)
        self.assertEqual(items.register_item(self.e,tr,'소형 방패'),0)
        TURN.unequip_weapon(self.e,tr,mid)
        self.assertGreater(items.register_item(self.e,tr,'소형 방패'),0)
    def test_weapon_shared_grant_retained_until_last_physical_weapon_removed(self):
        tr=self.actor('dual-owner','trainer');tr.spec['skills']['전투']='숙련'
        first=TURN.equip_weapon(self.e,tr,{'name':'첫 도끼','kind':'소형 근접무기','grade':'간단','moves':['강타']})
        second=TURN.equip_weapon(self.e,tr,{'name':'둘째 도끼','kind':'소형 근접무기','grade':'간단','slot':'반대손','moves':['강타']})
        move=next(m for m in tr.custom_conditions['equipped_weapons'][first]['available_moves'] if m!=first)
        TURN.unequip_weapon(self.e,tr,first);self.assertIn(move,tr.moves)
        TURN.unequip_weapon(self.e,tr,second);self.assertNotIn(move,tr.moves)
    def test_disarm_accuracy_six_includes_speed_evasion_boundary(self):
        self.prepare_disarm();self.t.item='오랭열매'
        self.t.stats['spe']=10;self.t.evasion_mod=0
        opts=self.disarm_success_options();opts['fixed_accuracy']=7
        self.assertFalse(self.e.disarm(self.a,self.t,**opts));self.assertEqual(self.t.item,'오랭열매')
        self.e.end_of_turn(self.a);self.e.end_round();self.prepare_disarm();self.t.item='오랭열매';opts['fixed_accuracy']=8
        self.assertTrue(self.e.disarm(self.a,self.t,**opts))
    def test_disarm_trainer_body_equipment_is_not_a_held_hand_item(self):
        import items
        self.prepare_disarm(trainer_target=True)
        self.t.item='경갑';self.assertGreater(items.register_item(self.e,self.t),0)
        before=(dict(self.a.budget),self.e.rng.getstate(),self.t.damage_reduction)
        with self.assertRaisesRegex(ValueError,'held-item selection'):
            self.e.disarm(self.a,self.t,**self.disarm_success_options())
        self.assertEqual(before,(dict(self.a.budget),self.e.rng.getstate(),self.t.damage_reduction))
        self.assertEqual(self.t.item,'경갑')
    def test_disarm_one_selected_hand_preserves_the_other_weapon(self):
        self.prepare_disarm(trainer_target=True)
        first=TURN.equip_weapon(self.e,self.t,{'name':'첫 검','kind':'소형 근접무기','grade':'조잡'})
        second=TURN.equip_weapon(self.e,self.t,{'name':'둘째 검','kind':'소형 근접무기','grade':'조잡','slot':'반대손'})
        before=dict(self.a.budget)
        with self.assertRaisesRegex(ValueError,'held-item selection'):
            self.e.disarm(self.a,self.t,**self.disarm_success_options())
        self.assertEqual(self.a.budget,before)
        self.assertTrue(self.e.disarm(self.a,self.t,**self.disarm_success_options(item_name='둘째 검')))
        self.assertIn(first,self.t.moves);self.assertNotIn(second,self.t.moves)
        self.assertEqual(list(self.t.custom_conditions['equipped_weapons']),[first])
    def test_disarm_generator_faces_preserved_and_two_sides_choose_different_skills(self):
        self.prepare_disarm();self.t.item='오랭열매';self.t.spec['skills']['은신']='미숙'
        self.assertTrue(self.e.disarm(self.a,self.t,attacker_skill='전투',defender_skill='은신',fixed_accuracy=20,
            challenger_options={'fixed':(6 for _ in range(5))},defender_options={'fixed':(1 for _ in range(2))}))
    def test_disarm_cannot_spend_another_actors_turn_or_a_used_standard(self):
        self.prepare_disarm();self.t.item='오랭열매';self.a.budget['standard']=0
        self.assertFalse(self.e.disarm(self.a,self.t,**self.disarm_success_options()))
        self.assertEqual(self.t.item,'오랭열매')
        self.a.budget['standard']=1;self.e._active_turn_actor=self.t
        self.assertFalse(self.e.disarm(self.a,self.t,**self.disarm_success_options()))
        self.assertEqual(self.a.budget['standard'],1)
    def test_disarm_provokes_other_adjacent_enemy_but_not_its_target(self):
        self.prepare_disarm();self.t.item='오랭열매'
        other=self.actor('other enemy');other.side='wild';other.pos=(1,2)
        self.e.everyone.append(other)
        self.assertTrue(self.e.disarm(self.a,self.t,**self.disarm_success_options()))
        self.assertTrue(other.aoo_used);self.assertFalse(self.t.aoo_used)
        self.assertTrue(any('[기회 공격]' in x and 'other enemy' in x for x in self.e.log_lines))
    def test_disarm_exception_compositions_hold_without_spending_or_rng(self):
        self.prepare_disarm();self.t.item='오랭열매'
        before=(dict(self.a.budget),self.e.rng.getstate())
        self.t.spec['edges']=['선택한 무기']
        with self.assertRaisesRegex(ValueError,'Weapon of Choice'):
            self.e.disarm(self.a,self.t,**self.disarm_success_options())
        self.t.spec['edges']=[];self.a.injuries=5
        with self.assertRaisesRegex(ValueError,'heavy Standard'):
            self.e.disarm(self.a,self.t,**self.disarm_success_options())
        self.assertEqual(before,(dict(self.a.budget),self.e.rng.getstate()))
    def test_weapon_struggle_actual_attack_and_no_stab(self):
        self.a=self.actor('weapon-user','trainer');self.a.side='party';self.prepare_disarm()
        self.a.types=['노말'];mid=TURN.equip_weapon(self.e,self.a,{'name':'공격 검','kind':'소형 근접무기','grade':'조잡'})
        self.assertEqual(self.e.damage_base(self.a,self.r.move(mid)),5)
        self.e.rng=FixedRng([10]);before=self.t.hp
        self.assertGreater(self.e.use_move(self.a,self.t,mid,set_damage=True),0)
        self.assertLess(self.t.hp,before);self.assertEqual(self.a.budget['standard'],0)
        self.assertFalse(any('자속보정' in x for x in self.e.log_lines))
    def test_weapon_granted_move_wr_ac_db_and_original_frequency(self):
        self.a=self.actor('ranged-user','trainer');self.a.side='party';self.prepare_disarm();self.e.at_initiative_count(20)
        self.a.types=['노말'];mid=TURN.equip_weapon(self.e,self.a,{'name':'활','kind':'장거리 사격무기','grade':'간단','moves':['강타']})
        self.t.pos=(1,7);self.e.grid=None;self.e.rng=FixedRng([10])
        self.assertEqual(self.e.damage_base(self.a,self.r.move('move/강타')),8)
        self.assertGreater(self.e.use_move(self.a,self.t,'move/강타',set_damage=True),0)
        self.assertEqual(self.a.move_uses['move/강타'],1);self.assertNotIn(mid,self.a.move_uses)
        self.assertTrue(any('AC 3' in x for x in self.e.log_lines))
    def test_weapon_offhand_penalty_and_explicit_shared_move_selection(self):
        import weapon_actions as WEAPONS
        tr=self.actor('dual-test','trainer');tr.types=['노말']
        self.e.gm.add_combatant(tr,reason='actual dual-weapon test participant')
        main=TURN.equip_weapon(self.e,tr,{'name':'주 도끼','kind':'소형 근접무기','grade':'간단','moves':['강타']})
        off=TURN.equip_weapon(self.e,tr,{'name':'보조 도끼','kind':'소형 근접무기','grade':'간단','moves':['강타'],'slot':'반대손'})
        self.t.stats['def']=0;self.t.stats['spe']=0
        with self.assertRaisesRegex(ValueError,'explicit weapon_id'):self.e.use_move(tr,self.t,'move/강타',set_damage=True)
        main_move=WEAPONS.prepare(self.e,tr,self.r.move('move/강타'),main)
        off_move=WEAPONS.prepare(self.e,tr,self.r.move('move/강타'),off)
        self.assertTrue(self.e.accuracy_check(tr,self.t,main_move,fixed_roll=2)[0])
        self.assertFalse(self.e.accuracy_check(tr,self.t,off_move,fixed_roll=2)[0])
        self.assertTrue(self.e.accuracy_check(tr,self.t,off_move,fixed_roll=4)[0])
        self.assertEqual((self.e.damage_base(tr,main_move),self.e.damage_base(tr,off_move)),(8,8))
    def test_weapon_wr_actual_grid_entry_preserves_shift_and_base_frequency(self):
        self.a=self.actor('grid-weapon-user','trainer');self.a.side='party';self.prepare_disarm();self.e.at_initiative_count(20)
        main=TURN.equip_weapon(self.e,self.a,{'name':'주 투척','kind':'단거리 사격무기','grade':'간단','moves':['강타']})
        off=TURN.equip_weapon(self.e,self.a,{'name':'보조 투척','kind':'단거리 사격무기','grade':'간단','moves':['강타'],'slot':'반대손'})
        self.t.pos=(1,4);before=self.a.pos
        self.assertGreaterEqual(self.e.use_move_on(self.a,self.t,'move/강타',[self.a,self.t],weapon_id=off),0)
        self.assertEqual(self.a.pos,before);self.assertEqual(self.a.budget['shift'],1)
        self.assertEqual(self.a.move_uses['move/강타'],1)
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round([self.a,self.t]);self.e.start_of_turn(self.a,initiative_count=20)
        self.assertEqual(self.e.use_move(self.a,self.t,'move/강타',weapon_id=main),0)
        self.assertEqual(self.a.move_uses['move/강타'],1)
        self.assertEqual(self.a.budget['standard'],1)
    def test_weapon_range_minimum_and_maximum_rejected_before_cost(self):
        self.a=self.actor('range-user','trainer');self.a.side='party';self.prepare_disarm()
        mid=TURN.equip_weapon(self.e,self.a,{'name':'긴 활','kind':'장거리 사격무기','grade':'간단','moves':['강타']})
        before=(dict(self.a.budget),self.e.rng.getstate(),dict(self.a.move_uses))
        with self.assertRaisesRegex(ValueError,'within four'):self.e.use_move(self.a,self.t,mid)
        self.t.pos=(1,14)
        with self.assertRaisesRegex(ValueError,'outside selected weapon'):self.e.use_move(self.a,self.t,'move/강타')
        self.assertEqual(before,(dict(self.a.budget),self.e.rng.getstate(),dict(self.a.move_uses)))
    def test_weapon_kind_grade_and_skill_restrictions_precede_equipment_mutation(self):
        tr=self.actor('restricted','trainer');tr.spec['skills']['전투']='숙련';before=list(tr.moves)
        for weapon in [
            {'name':'불법','kind':'소형 근접무기','grade':'간단','moves':['백스윙']},
            {'name':'불법','kind':'대형 근접무기','grade':'좋음','moves':['출혈']},
            {'name':'불법','kind':'대형 근접무기','grade':'간단','moves':['화염방사']}]:
            with self.assertRaises(ValueError):TURN.equip_weapon(self.e,tr,weapon)
        self.assertEqual(tr.moves,before);self.assertNotIn('equipped_weapons',tr.custom_conditions)
    def test_weapon_grant_is_unavailable_after_drop_but_independent_record_retained(self):
        tr=self.actor('drop-user','trainer')
        key=TURN.equip_weapon(self.e,tr,{'name':'봉','kind':'대형 근접무기','grade':'간단','moves':['백스윙']})
        self.e.gm.set_move(tr,'move/백스윙',True)
        TURN.unequip_weapon(self.e,tr,key)
        self.assertIn('move/백스윙',tr.moves)
        with self.assertRaisesRegex(ValueError,'equipped granting weapon'):self.e.use_move(tr,self.t,'move/백스윙')
    def prepare_weapon_choice(self):
        self.prepare_disarm(trainer_target=True)
        self.t.spec.update(edges=['선택한 무기'],edge_choices={'선택한 무기':'소형 근접무기'},feats=['독극 무기'],classes=['닌자'])
        self.t.spec['skills']['은신']='숙련'
        return TURN.equip_weapon(self.e,self.t,{'name':'방어 검','kind':'소형 근접무기','grade':'조잡'})
    def test_weapon_choice_bonus_changes_actual_opposed_outcome_without_ap(self):
        key=self.prepare_weapon_choice()
        from unittest.mock import patch
        import composition_derive as COMPOSITION
        with patch.object(COMPOSITION,'derive',wraps=COMPOSITION.derive) as common:
            self.assertFalse(self.e.disarm(self.a,self.t,attacker_skill='전투',defender_skill='전투',fixed_accuracy=20,
                challenger_options={'fixed':[5,3,3,3,3]},defender_options={'fixed':[3]*5},prevent_with_ap=False))
        self.assertTrue(any(any(row['source']=='edge/선택한-무기' for row in call.args[1]) for call in common.call_args_list))
        self.assertIn(key,self.t.moves);self.assertEqual(self.t.spec.get('ap_spent',0),0)
        self.assertTrue(any('17 vs' in x and '17' in x for x in self.e.log_lines))
    def test_weapon_choice_explicit_ap_paid_only_after_actual_defeat(self):
        key=self.prepare_weapon_choice()
        self.assertFalse(self.e.disarm(self.a,self.t,**self.disarm_success_options(prevent_with_ap=True)))
        self.assertIn(key,self.t.moves);self.assertEqual(self.t.spec['ap_spent'],1)
        self.assertEqual(self.t.spec.get('ap_removed',0),0);self.assertFalse(getattr(self.e,'ground_items',[]))
        self.assertEqual(self.a.budget['standard'],0)
    def test_weapon_choice_opt_out_drops_and_costs_no_ap(self):
        key=self.prepare_weapon_choice()
        self.assertTrue(self.e.disarm(self.a,self.t,**self.disarm_success_options(prevent_with_ap=False)))
        self.assertNotIn(key,self.t.moves);self.assertEqual(self.t.spec.get('ap_spent',0),0)
    def test_weapon_choice_missed_accuracy_never_pays_conditional_ap(self):
        key=self.prepare_weapon_choice();opts=self.disarm_success_options(prevent_with_ap=True);opts['fixed_accuracy']=1
        self.assertFalse(self.e.disarm(self.a,self.t,**opts))
        self.assertIn(key,self.t.moves);self.assertEqual(self.t.spec.get('ap_spent',0),0)
    def test_weapon_choice_won_defense_never_pays_conditional_ap(self):
        key=self.prepare_weapon_choice();opts=self.disarm_success_options(prevent_with_ap=True)
        opts['challenger_options']['fixed']=[1]*5;opts['defender_options']['fixed']=[6]*5
        self.assertFalse(self.e.disarm(self.a,self.t,**opts))
        self.assertIn(key,self.t.moves);self.assertEqual(self.t.spec.get('ap_spent',0),0)
    def test_weapon_choice_explicit_selection_prerequisite_and_ap_before_cost(self):
        import action_points as AP
        self.prepare_weapon_choice();before=(dict(self.a.budget),self.e.rng.getstate())
        with self.assertRaisesRegex(ValueError,'explicit conditional'):self.e.disarm(self.a,self.t,**self.disarm_success_options())
        self.t.spec['feats']=[]
        with self.assertRaisesRegex(ValueError,'acquired'):self.e.disarm(self.a,self.t,**self.disarm_success_options(prevent_with_ap=True))
        self.t.spec['feats']=['독극 무기'];self.t.spec['edge_choices']={}
        with self.assertRaisesRegex(ValueError,'explicit weapon type'):self.e.disarm(self.a,self.t,**self.disarm_success_options(prevent_with_ap=True))
        self.t.spec['edge_choices']={'선택한 무기':'소형 근접무기'};self.t.spec['ap_bound']={'existing':AP.maximum(self.t)}
        with self.assertRaisesRegex(ValueError,'available AP'):self.e.disarm(self.a,self.t,**self.disarm_success_options(prevent_with_ap=True))
        self.assertEqual(before,(dict(self.a.budget),self.e.rng.getstate()))
    def test_weapon_choice_nonmatching_equipment_gets_no_bonus_or_ap_prevention(self):
        self.prepare_weapon_choice();self.t.spec['edge_choices']['선택한 무기']='대형 근접무기'
        before=dict(self.a.budget)
        with self.assertRaisesRegex(ValueError,'not currently equipped'):
            self.e.disarm(self.a,self.t,**self.disarm_success_options(prevent_with_ap=True))
        self.assertEqual(self.a.budget,before)
        self.assertTrue(self.e.disarm(self.a,self.t,attacker_skill='전투',defender_skill='전투',fixed_accuracy=20,
            challenger_options={'fixed':[5,3,3,3,3]},defender_options={'fixed':[3]*5},prevent_with_ap=False))
        self.assertEqual(self.t.spec.get('ap_spent',0),0)
    def test_csv_weapon_choice_name_uses_same_real_ap_prevention(self):
        key=self.prepare_weapon_choice()
        self.t.spec['edges']=['무기 선택'];self.t.spec['edge_choices']={'무기 선택':'소형 근접무기'}
        self.assertFalse(self.e.disarm(self.a,self.t,**self.disarm_success_options(prevent_with_ap=True)))
        self.assertIn(key,self.t.moves);self.assertEqual(self.t.spec['ap_spent'],1)

    def test_weapon_choice_owner_aliases_duplicates_and_variant_gate(self):
        self.prepare_weapon_choice();before=(dict(self.a.budget),self.e.rng.getstate())
        self.t.spec['edges']=[]
        with self.assertRaisesRegex(ValueError,'acquired edge'):self.e.disarm(self.a,self.t,**self.disarm_success_options(prevent_with_ap=True))
        self.t.spec['edges']=['선택한 무기','Weapon of Choice']
        with self.assertRaisesRegex(ValueError,'one trainer-owned'):self.e.disarm(self.a,self.t,**self.disarm_success_options(prevent_with_ap=True))
        self.t.spec['edges']=['Weapon of Choice'];self.t.spec['edge_choices']={'Weapon of Choice':'소형 근접무기'}
        original=self.r._selected_rule
        self.addCleanup(setattr,self.r,'_selected_rule',original)
        self.r._selected_rule=lambda uid,*a,**k:'edge/variant' if uid=='edge/선택한-무기' else original(uid,*a,**k)
        with self.assertRaisesRegex(ValueError,'variant'):self.e.disarm(self.a,self.t,**self.disarm_success_options(prevent_with_ap=True))
        self.assertEqual(before,(dict(self.a.budget),self.e.rng.getstate()))
    def prepare_dirty_trick(self):
        self.prepare_disarm()
        for c in (self.a,self.t):c.spec['skills'].update({'육상':'전문','은신':'전문','곡예':'전문'})
        self.e.at_initiative_count(12)
    def trick_options(self, **extras):
        return dict(fixed_accuracy=20,challenger_options={'fixed':[6]*5},defender_options={'fixed':[1]*5},**extras)
    def test_dirty_hinder_actual_move_skill_penalty_and_exact_next_count(self):
        self.prepare_dirty_trick()
        self.assertTrue(self.e.dirty_trick(self.a,self.t,'hinder',**self.trick_options()))
        self.assertEqual(self.t.custom_conditions['combat_timed_effects'][0]['duration_origin'],'source_comparison_ptk_ptu241')
        self.assertEqual(self.e.move_profile(self.t)[0],3)
        self.assertEqual(self.e.skill_roll(self.t,'전투',fixed=[3]*5).total,13)
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round([self.a,self.t]);self.e.at_initiative_count(13)
        self.assertIn('둔화',self.t.conditions);self.assertEqual(self.e.skill_roll(self.t,'전투',fixed=[3]*5).total,13)
        self.e.at_initiative_count(12)
        self.assertNotIn('둔화',self.t.conditions);self.assertEqual(self.e.skill_roll(self.t,'전투',fixed=[3]*5).total,15)
    def test_dirty_hinder_split_duration_policy_preserves_status(self):
        self.prepare_dirty_trick()
        self.assertTrue(self.e.dirty_trick(self.a,self.t,'hinder',**self.trick_options(duration_policy='split',policy_reason='explicit split alternative')))
        self.assertEqual(self.t.custom_conditions['combat_timed_effects'][0]['duration_origin'],'gm_override')
        self.assertTrue(any('GM 기간 대체재정 split: explicit split alternative' in line for line in self.e.log_lines))
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round([self.a,self.t]);self.e.at_initiative_count(12)
        self.assertIn('둔화',self.t.conditions);self.assertEqual(self.e.skill_roll(self.t,'전투',fixed=[3]*5).total,15)
    def test_dirty_blind_actual_accuracy_penalty_and_expiry(self):
        self.prepare_dirty_trick();self.assertTrue(self.e.dirty_trick(self.a,self.t,'blind',**self.trick_options()))
        self.assertFalse(self.e.accuracy_check(self.t,self.a,self.r.move('struggle'),fixed_roll=10)[0])
        self.assertEqual(self.t.evasion('물리'),0)
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round([self.a,self.t]);self.e.at_initiative_count(12)
        self.assertNotIn('실명',self.t.conditions)
        self.assertTrue(self.e.accuracy_check(self.t,self.a,self.r.move('struggle'),fixed_roll=10)[0])
    def test_dirty_timed_status_does_not_erase_independent_reapplication(self):
        self.prepare_dirty_trick();self.assertTrue(self.e.dirty_trick(self.a,self.t,'blind',**self.trick_options()))
        self.e.apply_status(self.t,'실명')
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round([self.a,self.t]);self.e.at_initiative_count(12)
        self.assertIn('실명',self.t.conditions)
    def test_dirty_low_blow_waits_for_casters_next_turn_end(self):
        self.prepare_dirty_trick();self.t.initiative_override=7
        self.assertTrue(self.e.dirty_trick(self.a,self.t,'low_blow',**self.trick_options()))
        self.assertEqual(self.t.initiative_override,0);self.assertEqual(self.t.evasion('물리'),0)
        self.e.end_of_turn(self.a);self.assertEqual(self.t.initiative_override,0)
        self.e.start_of_turn(self.t);self.e.end_of_turn(self.t);self.assertEqual(self.t.initiative_override,0)
        self.e.end_round();self.e.start_round([self.a,self.t]);self.e.start_of_turn(self.a)
        self.assertEqual(self.t.initiative_override,0);self.e.end_of_turn(self.a)
        self.assertEqual(self.t.initiative_override,7);self.assertNotIn('취약',self.t.conditions)
    def test_dirty_low_blow_preserves_later_explicit_gm_override(self):
        self.prepare_dirty_trick()
        self.e.dirty_trick(self.a,self.t,'low_blow',**self.trick_options(duration_policy='combined',policy_reason='explicit shared scope'))
        self.e.gm.set_initiative(self.t,0,'independent scripted zero')
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round([self.a,self.t]);self.e.start_of_turn(self.a);self.e.end_of_turn(self.a)
        self.assertEqual(self.t.initiative_override,0)
    def test_dirty_invalid_policy_or_missing_count_holds_before_cost_rng(self):
        self.prepare_dirty_trick();before=(dict(self.a.budget),self.e.rng.getstate())
        for policy,reason in [('unknown','reason'),('split',None),('split','')]:
            with self.assertRaisesRegex(ValueError,'duration'):
                self.e.dirty_trick(self.a,self.t,'hinder',**self.trick_options(duration_policy=policy,policy_reason=reason))
        del self.e._initiative_cursor
        with self.assertRaisesRegex(ValueError,'explicit initiative count'):
            self.e.dirty_trick(self.a,self.t,'blind',**self.trick_options())
        self.assertEqual(before,(dict(self.a.budget),self.e.rng.getstate()))
    def test_dirty_miss_consumes_type_target_scene_attempt_but_no_status(self):
        self.prepare_dirty_trick();opts=self.trick_options();opts['fixed_accuracy']=1
        self.assertFalse(self.e.dirty_trick(self.a,self.t,'blind',**opts))
        self.assertEqual(self.a.budget['standard'],0);self.assertNotIn('실명',self.t.conditions)
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round([self.a,self.t]);self.e.start_of_turn(self.a);self.e.at_initiative_count(12)
        before=dict(self.a.budget)
        with self.assertRaisesRegex(ValueError,'already been used'):
            self.e.dirty_trick(self.a,self.t,'blind',**self.trick_options())
        self.assertEqual(self.a.budget,before)
        self.assertTrue(self.e.dirty_trick(self.a,self.t,'low_blow',**self.trick_options(duration_policy='combined',policy_reason='explicit shared scope')))
    def test_dirty_different_target_separate_attempt_and_scene_refresh(self):
        self.prepare_dirty_trick();opts=self.trick_options();opts['fixed_accuracy']=1
        self.assertFalse(self.e.dirty_trick(self.a,self.t,'blind',**opts));self.e.end_of_turn(self.a);self.e.end_round()
        other=self.actor('other target');other.pos=self.t.pos;other.side='wild';other.spec['skills']['은신']='전문'
        self.e.start_round([self.a,self.t,other]);self.e.start_of_turn(self.a);self.e.at_initiative_count(12)
        self.assertFalse(self.e.dirty_trick(self.a,other,'blind',**opts));self.e.end_of_turn(self.a);self.e.end_round();self.e.end_scene()
        self.assertNotIn('dirty_trick_uses',self.a.custom_conditions)
    def test_initiative_cursor_rejects_backward_count_and_unknown_successor_turn(self):
        self.prepare_dirty_trick();self.e.dirty_trick(self.a,self.t,'blind',**self.trick_options())
        with self.assertRaisesRegex(ValueError,'backward'):self.e.at_initiative_count(13)
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round([self.a,self.t])
        with self.assertRaisesRegex(ValueError,'explicit initiative count'):self.e.start_of_turn(self.a)
        self.assertIsNone(self.e._active_turn_actor)
        self.e.start_of_turn(self.a,initiative_count=12);self.assertNotIn('실명',self.t.conditions)
    def test_dirty_timers_and_cursor_restore_with_actual_actor_references(self):
        self.prepare_dirty_trick();self.e.dirty_trick(self.a,self.t,'blind',**self.trick_options());self.e.gm.snapshot('timed')
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round([self.a,self.t]);self.e.at_initiative_count(12)
        self.assertNotIn('실명',self.t.conditions);self.e.gm.restore('timed')
        self.assertIn('실명',self.t.conditions);self.assertEqual(self.e._initiative_cursor['round'],1)
        self.assertIs(self.a.custom_conditions['dirty_trick_uses'][0][1],self.t)
    def ap_payer(self):
        # ch06:85, Core 1.05 p.221: a trainer's AP bonus reaches only its own current, registered Pokemon.
        payer=self.actor('AP trainer','trainer');self.e.everyone.append(payer);self.t.spec['trainer_id']=payer.entity_id
        return payer
    def precision_setup(self):
        for c in (self.a,self.t):c.spec['skills'].update({'생존':'전문','집중':'숙련'})
        self.e.start_round([self.a,self.t]);self.e.start_of_turn(self.a)
    def precise(self, *, task=None, focus=None, **options):
        return self.e.common_action(self.t,'생존',14,mode='precise',
            context={'delicate':True,'activity':'ordinary_task','purpose':'carefully harvest fragile flower'},
            task_options=task or {'fixed':[3]*5},focus_options=focus or {},**options)
    def precision_attack(self, *, hit=True):
        self.e.rng.seed(5 if hit else 31)
        return self.e.use_move(self.a,self.t,'struggle',set_damage=True)
    def test_precision_missed_attack_still_focus_and_failure_step_boundaries(self):
        self.precision_setup();self.precision_attack(hit=False)
        for faces,penalty in [([4]*4,0),([4,4,4,3],-1),([3]*4,-2),([2]*4,-3),([1]*4,-4)]:
            out=self.precise(focus={'fixed':faces})
            self.assertEqual(out.basis['ordinary_roll'].total,15)
            self.assertEqual(out.basis['focus_penalty'],penalty)
            self.assertEqual(out.basis['hit_penalty'],0)
            self.assertEqual(out.check.total,15+penalty)
            self.assertEqual(out.basis['focus_roll'].faces,tuple(faces))
    def test_precision_hit_automatic_penalty_is_single_not_per_attack(self):
        self.precision_setup();self.precision_attack()
        out=self.precise(focus={'fixed':[4]*4});self.assertEqual(out.check.total,13)
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round([self.a,self.t]);self.e.start_of_turn(self.a)
        self.precision_attack()
        out=self.precise(focus={'fixed':[4]*4});self.assertEqual(out.basis['hit_penalty'],-2)
    def test_precision_defense_floor_and_temporary_absorption_still_hit(self):
        for reduction,temp in [(999,0),(0,999)]:
            self.setUp();self.precision_setup();self.t.damage_reduction=reduction
            if temp:self.e.gm.set_temp_hp(self.t,temp,'explicit test barrier')
            before=self.t.hp;self.precision_attack();self.assertEqual(self.t.hp,before-(1 if reduction else 0))
            out=self.precise(focus={'fixed':[4]*4});self.assertEqual(out.basis['hit_penalty'],-2)
    def test_native_defense_and_damage_reduction_floor_precedes_type_multiplier(self):
        move=self.move()
        for defense,reduction in [(999,0),(0,999),(20,20)]:
            self.t.stats['def']=defense;self.t.damage_reduction=reduction;self.t.types=[]
            self.assertEqual(self.e.roll_damage(self.a,self.t,move,set_damage=True),1)
            self.t.types=['바위']
            self.assertEqual(self.e.roll_damage(self.a,self.t,move,set_damage=True),0)
            self.t.types=['고스트']
            self.assertEqual(self.e.roll_damage(self.a,self.t,move,set_damage=True),0)
    def test_explicit_ability_immunity_still_zero_after_defense_floor(self):
        self.e.gm.set_ability(self.t,'부유',reason='owned source ability')
        self.t.stats['def']=999;self.t.types=[]
        self.assertEqual(self.e.roll_damage(self.a,self.t,self.move(type='땅'),set_damage=True),0)

    def test_precision_injuries_count_acquired_not_current_or_net(self):
        self.precision_setup();self.e.gm.set_injuries(self.t,delta=2,reason='two fresh injuries')
        self.e.gm.set_injuries(self.t,delta=-2,reason='later healing')
        out=self.precise();self.assertIsNone(out.basis['focus_roll']);self.assertEqual(out.basis['injury_penalty'],-4)
        self.assertEqual(out.check.total,11)
    def test_precision_massive_and_marker_injuries_observed_once_each(self):
        self.precision_setup();self.e.take_damage(self.t,110)
        out=self.precise();self.assertEqual(self.t.injuries,2)
        self.assertEqual(out.basis['injury_penalty'],-4);self.assertEqual(out.basis['hit_penalty'],0)
    def test_precision_effect_injury_and_hp_loss_marker_are_native_events(self):
        self.precision_setup();self.apply({'type':'injury','value':1})
        self.e.lose_hp(self.t,110,source='nonattack environmental loss')
        out=self.precise();self.assertEqual(out.basis['injury_penalty'],-4);self.assertIsNone(out.basis['focus_roll'])
    def test_precision_current_previous_round_then_expires_without_resetting_injuries(self):
        self.precision_setup();self.precision_attack(hit=False);self.e.gm.set_injuries(self.t,delta=1)
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round([self.a,self.t])
        out=self.precise(focus={'fixed':[4]*4});self.assertEqual(out.basis['injury_penalty'],-2)
        self.e.end_round();self.e.start_round([self.a,self.t]);out=self.precise()
        self.assertIsNone(out.basis['focus_roll']);self.assertEqual(out.check.total,15);self.assertEqual(self.t.injuries,1)
    def test_precision_ordinary_skill_and_maneuver_rolls_do_not_receive_penalty(self):
        self.precision_setup();self.precision_attack()
        self.assertEqual(self.e.skill_roll(self.t,'생존',fixed=[3]*5).total,15)
        out=self.e.common_action(self.t,'생존',14,mode='skill',fixed=[3]*5)
        self.assertEqual(out.check.total,15)
    def test_precision_context_is_explicit_and_invalid_focus_is_transactional(self):
        self.precision_setup();self.precision_attack(hit=False);before=(self.e.rng.getstate(),len(self.e.log_lines))
        out=self.e.common_action(self.t,'생존',14,mode='precise',context={'delicate':True,'activity':'feature','purpose':'activate feature'})
        self.assertIsNone(out.check)
        with self.assertRaises(ValueError):self.precise(focus={'fixed':[7]*4})
        self.assertEqual(before,(self.e.rng.getstate(),len(self.e.log_lines)))
    def test_precision_roll_id_separation_prevents_two_checks_consuming_one_ap(self):
        payer=self.ap_payer()
        self.e.boost_roll(payer,self.t,roll_id='precision-task',kind='skill')
        self.precision_setup();self.precision_attack(hit=False)
        with self.assertRaisesRegex(ValueError,'distinct'):
            self.precise(task={'fixed':[3]*5,'roll_id':'precision-task'},focus={'fixed':[4]*4,'roll_id':'precision-task'})
        self.assertEqual(self.e._ap_rolls['precision-task']['state'],'prepared')
    def test_precision_type_immunity_is_successful_hit_with_zero_damage(self):
        self.precision_setup();self.t.types=['고스트'];before=self.t.hp;self.precision_attack()
        out=self.precise(focus={'fixed':[4]*4})
        self.assertEqual(self.t.hp,before);self.assertEqual(out.basis['hit_penalty'],-2)
        self.assertEqual(self.e._precision_events[0]['nullification'],'type_immunity')
    def test_precision_native_ability_immunity_and_absorption_are_still_successful_hits(self):
        for ability,move,kind in [('부유','move/지진','ability_immunity'),('축전','move/전기쇼크','ability_absorption')]:
            self.setUp();self.precision_setup();self.e.gm.set_ability(self.t,ability,reason='actual owned core ability')
            before=self.t.hp;self.e.rng.seed(5);self.e.use_move(self.a,self.t,move,set_damage=True)
            out=self.precise(focus={'fixed':[4]*4});self.assertEqual(out.basis['hit_penalty'],-2)
            self.assertGreaterEqual(self.t.hp,before);self.assertEqual(self.e._precision_events[0]['nullification'],kind)
    def wonder_guard(self):
        self.t.types=['노말'];self.e.gm.set_ability(self.t,'불가사의부적',reason='actual owned core ability')
    def test_precision_wonder_guard_blocks_actual_hit_even_natural20_and_needs_focus_only(self):
        self.precision_setup();self.wonder_guard();before=self.t.hp
        self.e.rng.seed(5);self.assertEqual(self.e.use_move(self.a,self.t,'struggle',set_damage=True),0)
        self.assertEqual(self.t.hp,before);out=self.precise(focus={'fixed':[4]*4})
        self.assertEqual((out.basis['hit_penalty'],out.basis['focus_roll'].total),(0,16))
        self.assertEqual(self.e._precision_events[0]['result'],'miss')
        self.assertEqual(self.a.budget['standard'],0)
        self.assertEqual(self.e.accuracy_check(self.a,self.t,self.move(),fixed_roll=20),(False,20,False))
    def test_wonder_guard_super_effective_attack_and_status_move_can_hit(self):
        self.wonder_guard()
        self.assertTrue(self.e.accuracy_check(self.a,self.t,self.r.move('move/깨트리기'),fixed_roll=20)[0])
        self.assertTrue(self.e.accuracy_check(self.a,self.t,self.r.move('move/째려보기'),fixed_roll=20)[0])
        self.assertGreater(self.e.roll_damage(self.a,self.t,self.r.move('move/깨트리기'),set_damage=True),0)
    def test_wonder_guard_suppression_and_absence_of_any_natural_weakness_disable_it(self):
        self.wonder_guard();self.t.abilities_suppressed=True
        self.assertTrue(self.e.accuracy_check(self.a,self.t,self.move(),fixed_roll=20)[0])
        self.t.abilities_suppressed=False;self.t.types=[]
        self.assertTrue(self.e.accuracy_check(self.a,self.t,self.move(),fixed_roll=20)[0])
        self.assertGreater(self.e.roll_damage(self.a,self.t,self.move(),set_damage=True),0)
    def test_wonder_guard_previews_actual_type_override_without_consuming_it_twice(self):
        self.precision_setup();self.wonder_guard();self.t.types=['풀'];self.a.type_override_next='불꽃'
        move=self.r.move('struggle')
        self.assertTrue(self.e.accuracy_check(self.a,self.t,move,fixed_roll=20)[0])
        self.assertEqual(self.a.type_override_next,'불꽃')
        before=self.t.hp;self.e.rng.seed(5);self.e.use_move(self.a,self.t,'struggle',set_damage=True)
        self.assertLess(self.t.hp,before);self.assertIsNone(self.a.type_override_next)
        self.assertEqual(self.precise(focus={'fixed':[4]*4}).basis['hit_penalty'],-2)
    def test_wonder_guard_effectiveness_blessing_is_previewed_then_consumed_only_once(self):
        self.precision_setup();self.wonder_guard()
        self.a.blessings=[{'name':'single effectiveness','left':1,'on':'physical attack','effect':'effectiveness'}]
        self.assertTrue(self.e.accuracy_check(self.a,self.t,self.r.move('struggle'),fixed_roll=20)[0])
        self.assertEqual(self.a.blessings[0]['left'],1)
        self.e.rng.seed(5);before=self.t.hp;self.e.use_move(self.a,self.t,'struggle',set_damage=True)
        self.assertLess(self.t.hp,before);self.assertEqual(self.a.blessings[0]['left'],0)
    def test_precision_direct_and_delayed_no_hit_cannot_emit_damage_or_heavy_event(self):
        self.precision_setup();self.wonder_guard();before=self.t.hp
        self.assertEqual(self.e.resolve_attack_damage(self.a,self.t,self.r.move('struggle'),set_damage=True),0)
        self.assertEqual(self.t.hp,before);self.assertFalse(self.e._heavy_events)
        self.assertEqual(self.precise(focus={'fixed':[4]*4}).basis['hit_penalty'],0)
        self.e.use_move(self.a,self.t,'move/미래예지')
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.t);self.e.end_of_turn(self.t)
        self.assertEqual(self.t.hp,before);self.assertFalse(self.e._heavy_events)
        self.assertEqual(self.e._precision_events[-1]['result'],'hit_prevented')
    def test_wonder_guard_removed_ability_does_not_leave_stale_immunity(self):
        self.wonder_guard();self.e.gm.set_ability(self.t,'불가사의부적',add=False,reason='actual ability removal')
        self.assertTrue(self.e.accuracy_check(self.a,self.t,self.r.move('struggle'),fixed_roll=20)[0])
    def test_wonder_guard_blocks_actual_move_secondary_status(self):
        self.precision_setup();self.wonder_guard();self.a.moves.append('move/불꽃세례')
        self.e.rng.seed(5);before=self.t.hp;self.e.use_move(self.a,self.t,'move/불꽃세례',set_damage=True)
        self.assertEqual(self.t.hp,before);self.assertNotIn('화상',self.t.conditions)
        self.assertEqual(self.precise(focus={'fixed':[4]*4}).basis['hit_penalty'],0)
    def test_wonder_guard_consumable_defensive_resistance_loop_holds_before_cost(self):
        self.precision_setup();self.wonder_guard();self.a.moves.append('move/깨트리기')
        self.t.blessings=[{'name':'single resistance','left':1,'on':'physical attack','effect':'resistance'}]
        before=(dict(self.a.budget),dict(self.a.move_uses),self.e.rng.getstate(),self.t.hp)
        with self.assertRaisesRegex(ValueError,'activation-order'):
            self.e.use_move(self.a,self.t,'move/깨트리기')
        self.assertEqual(before,(dict(self.a.budget),dict(self.a.move_uses),self.e.rng.getstate(),self.t.hp))
        self.assertEqual(self.t.blessings[0]['left'],1)

    def test_wonder_guard_variant_and_unknown_type_condition_hold_before_cost_or_rng(self):
        self.precision_setup();self.wonder_guard();before=(dict(self.a.budget),dict(self.a.move_uses),self.e.rng.getstate(),self.t.hp)
        original=self.r._selected_rule
        self.r._selected_rule=lambda uid,*a,**kw: uid+'-variant' if uid=='ability/불가사의부적' else original(uid,*a,**kw)
        try:
            with self.assertRaisesRegex(ValueError,'variant'):self.e.use_move(self.a,self.t,'struggle')
        finally:self.r._selected_rule=original
        self.assertEqual(before,(dict(self.a.budget),dict(self.a.move_uses),self.e.rng.getstate(),self.t.hp))
        self.a.registry.append({'type':'type_effectiveness_override','steps':1,'if':'unspecified world condition'})
        with self.assertRaisesRegex(ValueError,'unresolved conditional'):self.e.use_move(self.a,self.t,'struggle')
        self.assertEqual(before,(dict(self.a.budget),dict(self.a.move_uses),self.e.rng.getstate(),self.t.hp))
    def test_precision_snapshot_restores_live_evidence_and_encounter_clears_it(self):
        self.precision_setup();self.precision_attack(hit=False);self.e.gm.snapshot('precision')
        self.e.end_of_turn(self.a);self.e.end_encounter();self.assertFalse(self.e._precision_events)
        self.e.gm.restore('precision');self.assertIs(self.e._precision_events[0]['target'],self.t)
        out=self.precise(focus={'fixed':[4]*4});self.assertEqual(out.check.total,15)
    def test_precision_completed_task_finalizes_both_actual_roll_ids(self):
        import skill_feature_actions as SF
        payer=self.ap_payer();self.e.boost_roll(payer,self.t,roll_id='ordinary',kind='skill')
        self.precision_setup();self.precision_attack(hit=False)
        out=self.precise(task={'fixed':[3]*5,'roll_id':'ordinary'},focus={'fixed':[4]*4,'roll_id':'supplement'})
        self.assertEqual(out.basis['ordinary_roll'].total,16)
        self.assertEqual(out.basis['focus_roll'].total,16)
        for rid in ('ordinary','supplement'):self.assertEqual(SF.event(self.e,self.t,rid).state,'final')
    def test_precision_attacked_other_actor_and_self_buff_do_not_trigger(self):
        self.precision_setup();self.e.use_move(self.a,self.a,'move/칼춤')
        out=self.precise();self.assertIsNone(out.basis['focus_roll'])
        self.assertFalse(self.e._precision_events)
    def test_precision_native_disarm_miss_counts_attack_without_damage(self):
        self.prepare_disarm();self.t.spec['skills'].update({'생존':'전문','집중':'숙련'});self.t.item='상처약'
        self.e.disarm(self.a,self.t,attacker_skill='전투',defender_skill='전투',fixed_accuracy=1,
            challenger_options={'fixed':[3]*5},defender_options={'fixed':[3]*5})
        out=self.precise(focus={'fixed':[4]*4});self.assertTrue(out.basis['evidence']['attacked'])
        self.assertEqual(out.basis['hit_penalty'],0)
    def test_precision_native_delayed_hit_recorded_at_impact(self):
        self.precision_setup();self.e.use_move(self.a,self.t,'move/미래예지')
        self.assertFalse(self.e._precision_events)
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.t);self.e.end_of_turn(self.t)
        out=self.precise(focus={'fixed':[4]*4});self.assertEqual(out.basis['hit_penalty'],-2)
        self.assertEqual(self.e._precision_events[0]['producer'],'effects_ext.delayed_attack')
    def test_precision_type_nullification_is_irrelevant_after_another_confirmed_hit(self):
        self.precision_setup();self.t.types=['고스트'];self.precision_attack()
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round([self.a,self.t]);self.e.start_of_turn(self.a)
        self.t.types=[];self.precision_attack()
        out=self.precise(focus={'fixed':[4]*4});self.assertEqual(out.basis['hit_penalty'],-2)
    def test_precision_task_for_trainer_uses_owned_modifiers_once_on_each_actual_skill(self):
        self.t=self.actor('working trainer','trainer');self.t.side='wild';self.e.everyone=[self.a,self.t]
        self.precision_setup();self.precision_attack(hit=False)
        out=self.precise(task={'fixed':[3]*5,'mods':2},focus={'fixed':[3]*4,'mods':1})
        self.assertEqual(out.basis['ordinary_roll'].total,17);self.assertEqual(out.basis['focus_roll'].total,13)
        self.assertEqual(out.check.total,16)
    def test_precision_native_area_attack_records_each_actual_target(self):
        from grid import Grid
        import precise_actions as P
        other=self.actor('area other');other.side='wild'
        self.a.pos=(3,3);self.t.pos=(4,3);other.pos=(3,4)
        self.e.grid=Grid(7,7);self.e.everyone=[self.a,self.t,other]
        self.precision_setup();self.e.time_actors([other]);self.e.rng.seed(5)
        self.e.use_move_on(self.a,self.t,'move/꽃보라',[self.a,self.t,other])
        self.assertTrue(P.evidence(self.e,self.t)['damaging_hit'])
        self.assertTrue(P.evidence(self.e,other)['damaging_hit'])
        self.assertFalse(P.evidence(self.e,self.a)['attacked'])
        self.assertEqual(self.precise(focus={'fixed':[4]*4}).basis['hit_penalty'],-2)
    def test_precision_selected_variant_cannot_inherit_fixed_rule(self):
        self.precision_setup();original=self.r._selected_rule
        self.r._selected_rule=lambda uid,*a,**kw: uid+'-variant' if uid.endswith('/정밀-스킬-체크') else original(uid,*a,**kw)
        try:
            with self.assertRaisesRegex(ValueError,'variant'):self.precise()
        finally:self.r._selected_rule=original
    def test_maneuver_invalid_feature_declaration_holds_before_action_frequency_rng(self):
        self.prepare_disarm();self.t.item='상처약'
        before=(dict(self.a.budget),self.e.rng.getstate(),dict(self.a.move_uses))
        with self.assertRaises(ValueError):
            self.e.disarm(self.a,self.t,attacker_skill='전투',defender_skill='전투',
                challenger_options={'feature':'feat/팔방미인','roll_id':'disarm-feature'})
        self.assertEqual(before,(dict(self.a.budget),self.e.rng.getstate(),dict(self.a.move_uses)))
        self.e.at_initiative_count(12)
        with self.assertRaises(ValueError):
            self.e.dirty_trick(self.a,self.t,'blind',challenger_options={'feature':'feat/팔방미인','roll_id':'dirty-feature'})
        self.assertNotIn('dirty_trick_uses',self.a.custom_conditions)
        self.assertEqual(before,(dict(self.a.budget),self.e.rng.getstate(),dict(self.a.move_uses)))
    def test_confusion_prevents_attack_of_opportunity(self):
        self.t.conditions.add('혼란');self.assertFalse(TURN.can_aoo(self.e,self.t))
        self.t.conditions.clear();self.assertTrue(TURN.can_aoo(self.e,self.t))
if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
        def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(CombatTests))
    files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/researcher_features.py','engine/downtime.py','engine/environmental_effects.py','engine/injury_recovery.py','engine/trainer_capabilities.py','engine/wild_equipment.py','engine/common_action_checks.py','engine/skill_feature_actions.py','engine/precise_actions.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','data/context-check-policy.json','data/cultivation-policy.json','engine/crafting_activities.py','engine/contest_features.py','data/planter-policy.json','engine/engine.py','engine/effects.py','engine/effects_ext.py','engine/turn.py','engine/life.py','engine/action_lifecycle.py','engine/action_points.py','engine/frequency.py','engine/common_checks.py','engine/ruleset.py','engine/rulings.py','engine/gm_state.py','engine/items.py','engine/temporary_hp.py','engine/weapon_actions.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/weapon-policy.json','engine/heavy_injury_adapter.py','engine/heavy_standard_adapter.py','engine/capability_actions.py','engine/movement_actions.py','engine/bandages.py','engine/physical_limits.py','data/capability-policy.json','data/core-rules.json','data/lookup-tables.json','data/conditions.json','data/rulesets.json','data/moves-hand.json','data/moves-mech.json','data/moves-llm.json','output/ruleunits.jsonl','input/ch07-combat.md','input/ch09-equipment.md','input/ch03-skills-edges-feats.md','input/ch10-index-reference.md','engine/skill_modifiers.py','data/skill-check-policy.json','tools/synthetic_rule_fixture.py','tools/test_category3_combat_next.py']
    files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
    files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
    files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

    files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

    files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':CLAUSES,'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
    (ROOT/'output/category3-combat-next-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
