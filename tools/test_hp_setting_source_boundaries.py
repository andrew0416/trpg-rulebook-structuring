"""Actual selected Sturdy sources, self-setting, forced faint and public sacrifice Moves."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from ruleset import RuleFilter,UnresolvedRuleSelection
from grid import Grid
import effects as FX
import effects_ext as EXT
import temporary_hp as TEMP
import world_entities as WORLD
import items as ITEMS
import keep_fighting as KEEP
import attack_damage_history as HISTORY
from native_scenario_fixture import prepare_body

SOURCES={'homebrew':'ability/옹골참-홈브류','playtest':'ability/옹골참-playtest','core':'ability/옹골참'}

class HPSettingSourceTests(unittest.TestCase):
    @classmethod
    def make_rules(cls,variant):
        rules=Rules(str(ROOT),ruleset='core')
        if variant!='core':
            rules.ruleset=RuleFilter({'sources':['core'],'variants':['홈브류' if variant=='homebrew' else 'playtest'],
                'variant_replaces_core':True,'variant_choices':{'ability/옹골참':SOURCES[variant]}},
                name='hp-setting-'+variant)
            rules._apply_ruleset()
        return rules

    @classmethod
    def setUpClass(cls):
        cls.profiles={variant:cls.make_rules(variant) for variant in SOURCES}

    def world(self,variant='homebrew',*,hp_stat=24,fresh=False,owned=False):
        rules=self.make_rules(variant) if fresh else self.profiles[variant]
        e=Engine(rules,seed=192480);e.grid=Grid(10,10)
        def add(uid,kind,hp_stat,pos,side,**extra):
            spec=dict(id=uid,name=uid,kind=kind,level=1,stats=dict(hp=hp_stat,atk=10,**{'def':10},spa=10,spd=10,spe=10),
                types=['노말'],skills={'육상':6,'명령':6,'집중':6},moves=[],abilities=[],movement={'land':6},items={})
            spec.update(extra);actor=Combatant(rules,spec)
            e.gm.add_combatant(actor,pos=pos,side=side,reason='actual HP-source regression world')
            prepare_body(e,actor,size='중형' if kind=='trainer' else '소형',offsets=[(0,0)],
                         reason='observed one-cell HP-source fixture body')
            return actor
        owner=add('hp-cap/owner','trainer',23,(8,8),'party') if owned else None
        actor=add('hp-cap/user','pokemon',hp_stat,(2,2),'party',wild=not owned,
                  **({'trainer_id':owner.entity_id} if owner else {}))
        target=add('hp-cap/target','pokemon',197,(3,2),'enemy',wild=True)
        e.gm.set_ability(actor,'옹골참',True,reason='explicit selected Sturdy profile')
        if variant!='core':
            self.assertEqual(actor.damage_cap['_rule_id'],SOURCES[variant])
            self.assertEqual(actor.damage_cap['applies_to'],'damage and hp loss')
        else:self.assertIsNone(actor.damage_cap)
        return e,actor,target,owner

    def start(self,e,actor,target,move,*,hit=True):
        e.gm.set_move(actor,move,True,reason='actual selected public Move')
        e.start_round([actor,target]);e.start_of_turn(actor,initiative_count=e.initiative_value(actor).value)
        e.d20=lambda:10 if hit else 1

    def temp(self,e,actor,value):
        e.gm.set_temp_hp(actor,value,reason='actual observed temporary HP source',duration_seconds=300)

    def restored(self,e,variant):
        # The fixture's fixed accuracy callback is not saved gameplay state.
        vars(e).pop('d20',None)
        state=json.loads(json.dumps(e.export_state(),ensure_ascii=False))
        return Engine.import_state(self.make_rules(variant),state)

    def test_selected_damage_and_all_HP_loss_kinds_share_the_correct_rounding(self):
        for variant,limit in [('homebrew',42),('playtest',41)]:
            for kind in ['damage','loss','percentage','hp_setting']:
                with self.subTest(variant=variant,kind=kind):
                    e,actor,_,_=self.world(variant)
                    self.assertEqual(actor.base_max_hp,83)
                    if kind=='damage':e.take_damage(actor,100)
                    else:e.lose_hp(actor,100,loss_kind=kind)
                    self.assertEqual(actor.hp,83-limit)
                    self.assertFalse(actor.fainted)

    def test_nontrue_flags_keep_selected_loss_cap_and_setting_does_not_consume_temp_HP(self):
        for flag in [None,False,'true',1]:
            with self.subTest(flag=flag):
                e,actor,_,_=self.world(hp_stat=23);e.gm.set_hp(actor,20,reason='known current HP')
                self.temp(e,actor,100);effect={'self_hp':'-50% max'}
                if flag is not None:effect['unpreventable']=flag
                FX.h_self_hp_set(e,actor,actor,effect,{})
                self.assertEqual((actor.hp,actor.temp_hp),(-20,100))
                self.assertTrue(actor.fainted)
                self.assertEqual(actor.injuries,1)
        # The public primitive is stricter than the effect parser: no truthiness.
        for invalid in [None,1,'true',0,[]]:
            e,actor,_,_=self.world(hp_stat=23)
            before=(actor.hp,actor.temp_hp,actor.injuries)
            with self.assertRaisesRegex(ValueError,'explicit boolean'):
                e.lose_hp(actor,60,unpreventable=invalid,loss_kind='hp_setting')
            self.assertEqual((actor.hp,actor.temp_hp,actor.injuries),before)

    def test_explicit_true_bypasses_cap_and_replacement_but_keeps_markers_and_faint(self):
        e,actor,_,_=self.world(hp_stat=23);e.gm.set_hp(actor,20,reason='known current HP')
        self.temp(e,actor,100)
        with patch.object(KEEP,'replace_hp',side_effect=AssertionError('unpreventable loss reached prevention')):
            FX.h_self_hp_set(e,actor,actor,{'self_hp':'-50% max','unpreventable':True},{})
        self.assertEqual((actor.hp,actor.temp_hp,actor.injuries),(-40,100,2))
        self.assertTrue(actor.fainted);self.assertFalse(actor.dead)

    def test_damage_only_cap_does_not_reduce_HP_setting_and_unknown_scope_is_atomic(self):
        e,actor,_,_=self.world('core',hp_stat=23)
        actor.damage_cap={'value':1,'applies_to':'damage'}
        e.lose_hp(actor,20,loss_kind='hp_setting')
        self.assertEqual(actor.hp,60)
        actor.damage_cap={'value':1,'applies_to':'unknown'};before=(actor.hp,actor.temp_hp,actor.injuries)
        with self.assertRaisesRegex(ValueError,'unsupported damage-cap scope'):e.lose_hp(actor,20,loss_kind='hp_setting')
        self.assertEqual((actor.hp,actor.temp_hp,actor.injuries),before)

    def test_actual_single_attack_caps_damage_while_core_sturdy_does_not_cap_self_setting(self):
        e,actor,target,_=self.world(hp_stat=23)
        e.gm.set_ability(target,'옹골참',True,reason='same selected cap on actual recipient')
        before=target.hp;limit=(target.base_max_hp+1)//2
        self.start(e,actor,target,'move/몸통박치기')
        with patch.object(e,'roll_damage',return_value=target.base_max_hp):
            e.use_move(actor,target,'move/몸통박치기',set_damage=True)
        self.assertEqual(target.hp,before-limit)
        self.assertEqual(actor.move_uses['move/몸통박치기'],1)
        core,c,_,_=self.world('core',hp_stat=23)
        FX.h_self_hp_set(core,c,c,{'self_hp':0},{})
        self.assertEqual(c.hp,0);self.assertTrue(c.fainted)

    def gambit(self,e,actor,target):
        self.temp(e,actor,17)
        self.start(e,actor,target,'move/목숨걸기')
        before=target.hp
        result=e.use_move(actor,target,'move/목숨걸기',set_damage=True)
        self.assertEqual(actor.hp,41)
        self.assertEqual(actor.temp_hp,17)
        self.assertTrue(actor.fainted)
        self.assertEqual(actor.injuries,1)
        self.assertEqual(target.hp,before-42)
        self.assertEqual(result,42)
        self.assertEqual(actor.move_uses['move/목숨걸기'],1)
        self.assertEqual(actor.budget['standard'],0)
        last=HISTORY.records(target)[-1]
        self.assertEqual(last.get('application_kind','damage'),'damage')
        self.assertEqual(last['receipt']['requested'],42)
        self.assertEqual(last['receipt']['source'],'move/목숨걸기')
        self.assertEqual(HISTORY.current_round(e,target),42)
        completion=next(r for r in e._move_completions.values() if r['move_id']=='move/목숨걸기')
        self.assertEqual(completion['phase'],'complete')
        return (actor.hp,actor.temp_hp,actor.injuries,actor.fainted,target.hp,actor.budget['standard'],actor.move_uses['move/목숨걸기'])

    def test_public_final_gambit_separates_capped_HP_loss_positive_faint_and_actual_damage(self):
        e,actor,target,_=self.world()
        self.gambit(e,actor,target)
        loaded=self.restored(e,'homebrew');index=WORLD.actor_index(loaded)
        restored=index[actor.entity_id]
        self.assertEqual((restored.hp,restored.temp_hp,restored.fainted),(41,17,True))
        self.assertEqual(HISTORY.records(index[target.entity_id]),HISTORY.records(target))
        before=deepcopy(loaded.export_state())
        before_logs=list(loaded.log_lines)
        self.assertFalse(getattr(loaded,'_execution_trace_enabled',False))
        with patch.object(loaded,'d20',side_effect=AssertionError('fainted actor must not roll accuracy')) as roller:
            self.assertEqual(loaded.use_move(restored,index[target.entity_id],'move/목숨걸기'),0)
        roller.assert_not_called()
        self.assertEqual(loaded.log_lines,before_logs+[
            f"  {restored.name}: 체력 {restored.hp} 의식불명 → 동작 불가  => [combat/hit-points]"])
        # Refusal logs are saved state; every other saved field, including
        # HP/faint, target state, actions, frequency, RNG, effects and trace, stays unchanged.
        with patch.object(loaded,'log_lines',before_logs):
            self.assertEqual(loaded.export_state(),before)

    def test_original_cold_factory_and_adapted_warm_cache_use_independent_native_worlds(self):
        cold=self.world(fresh=True);warm=self.world()
        self.assertIsNot(cold[0],warm[0]);self.assertIsNot(cold[0].r,warm[0].r)
        self.assertEqual(self.gambit(*cold[:3]),self.gambit(*warm[:3]))

    def test_public_final_gambit_does_not_activate_an_actual_held_item(self):
        def equip(e,target,suffix):
            uid='hp-cap/helmet-'+suffix
            WORLD.register_object(e,uid,kind='item_instance',item_rule_id='item/울퉁불퉁멧',owner_id=target.entity_id,
                                  location={'kind':'unknown'},reason='actual held reaction boundary')
            ITEMS.register_item(e,target,'item/울퉁불퉁멧',source_instance_id=uid,as_held=True)
            return uid
        ordinary,user,holder,_=self.world('core');normal_id=equip(ordinary,holder,'ordinary')
        self.start(ordinary,user,holder,'move/드래곤클로');before=user.hp
        ordinary.d20=lambda:20
        self.assertGreater(ordinary.use_move(user,holder,'move/드래곤클로',set_damage=True),0)
        self.assertEqual(user.hp,before-ordinary.tick(user))
        self.assertEqual(holder.spec['held_item_reaction_history'][-1]['instance_id'],normal_id)
        e,actor,target,_=self.world();uid=equip(e,target,'gambit')
        history=deepcopy(target.spec.get('held_item_reaction_history',[]))
        self.gambit(e,actor,target)
        self.assertEqual(target.spec.get('held_item_reaction_history',[]),history)
        self.assertEqual((actor.hp,actor.temp_hp),(41,17))
        self.assertEqual(e._physical_objects[uid]['equipped_by'],target.entity_id)

    def test_public_explosions_pay_one_unpreventable_self_cost_after_all_hits_or_misses(self):
        for move in ['move/대폭발','move/자폭']:
            for hit in [True,False]:
                with self.subTest(move=move,hit=hit):
                    e,actor,target,_=self.world(hp_stat=24);self.temp(e,actor,100)
                    other=Combatant(e.r,dict(id='hp-cap/other',name='Other',kind='pokemon',wild=True,level=1,
                        stats=dict(hp=197,atk=10,**{'def':10},spa=10,spd=10,spe=10),types=['노말'],moves=[],abilities=[],movement={'land':6}))
                    e.gm.add_combatant(other,pos=(2,3),side='enemy',reason='second actual area recipient')
                    prepare_body(e,other,size='소형',offsets=[(0,0)],reason='observed second one-cell area recipient')
                    self.start(e,actor,target,move,hit=hit)
                    e.use_move_on(actor,target,move,[actor,target,other],set_damage=True)
                    self.assertEqual(actor.base_max_hp,83)
                    self.assertEqual((actor.hp,actor.temp_hp,actor.injuries),(-42,100,3))
                    self.assertTrue(actor.fainted)
                    self.assertEqual(actor.move_uses[move],1)
                    rows=[r for r in e._effect_dispatch_receipts.values() if r['source_id']==move and r['effect'].get('type')=='self_hp_set']
                    self.assertEqual(len(rows),1);self.assertEqual(rows[0]['status'],'completed')

    def test_owned_sacrifice_requires_GM_loyalty_magnitude_before_cost_and_applies_once(self):
        e,actor,target,owner=self.world(hp_stat=23,owned=True)
        e.gm.observe_loyalty(actor,3,reason='actual current trainer relationship')
        self.start(e,actor,target,'move/자폭')
        before=deepcopy((actor.spec,actor.hp,actor.temp_hp,actor.budget,actor.move_uses,e.rng.getstate()))
        with self.assertRaisesRegex(ValueError,'explicit GM loyalty'):e.use_move_on(actor,target,'move/자폭',[actor,target],set_damage=True)
        self.assertEqual((actor.spec,actor.hp,actor.temp_hp,actor.budget,actor.move_uses,e.rng.getstate()),before)
        revision=actor.spec['loyalty_revision']
        choices=[]
        def provider(prompt):
            if prompt.get('type')!='sacrifice_loyalty':return None
            choices.append(deepcopy(prompt))
            return {'after':2,'reason':'GM resolved the source-mandated decrease'} if len(choices)==1 else None
        e.rulings.provider=provider
        e.use_move_on(actor,target,'move/자폭',[actor,target],set_damage=True)
        self.assertEqual(len(choices),1)
        self.assertEqual(actor.spec['loyalty'],2);self.assertEqual(actor.spec['loyalty_revision'],revision+1)
        setting=next(r for r in e._effect_dispatch_receipts.values() if r['source_id']=='move/자폭' and r['effect'].get('type')=='self_hp_set')
        self.assertEqual(setting['hp_setting']['prepared_loyalty']['after'],2)
        e.rulings.provider=None
        loaded=self.restored(e,'homebrew');again=WORLD.actor_index(loaded)[actor.entity_id]
        self.assertEqual((again.hp,again.spec['loyalty'],again.spec['loyalty_revision']),(-40,2,revision+1))

    def test_prepared_sacrifice_choice_survives_native_target_wait_restore_and_tamper_rejection(self):
        import hp_setting_moves as SETTING
        import passive_events as PASSIVE
        e,actor,target,_=self.world(owned=True)
        e.gm.observe_loyalty(actor,3,reason='actual current trainer relationship')
        self.temp(e,actor,100)
        self.start(e,actor,target,'move/자폭')
        source='input/'+e.r.selection.units['combat/struggle']['source']['file']
        document={'schema':1,'id':'event/hp-setting-wait','variants':[{
            'rule_id':'combat/struggle','source':{'file':source,'sha256':sha256((ROOT/source).read_bytes()).hexdigest()},
            'inputs':{'hit':{'authority':'context','type':'boolean','question':'Actual native hit'},
                      'choice':{'authority':'gm','type':'boolean','question':'Actual application wait'}},
            'when':{'op':'eq','left':{'$input':'hit'},'right':True},
            'values':{'effects':[{'type':'stage_change','stat':'atk','delta':0,'target':'self'}]}}]}
        listener=e.subscribe_source_policy(actor,'hp-setting-wait',document,inputs={'hit':'hit'})
        prompts=[]
        def provider(prompt):
            if prompt.get('type')!='sacrifice_loyalty':return None
            prompts.append(deepcopy(prompt))
            return {'after':2,'reason':'one prepared GM decrease'} if len(prompts)==1 else None
        e.rulings.provider=provider
        with self.assertRaises(PASSIVE.PassiveEventPending):
            e.use_move_on(actor,target,'move/자폭',[actor,target],set_damage=True)
        self.assertIsNone(SETTING._PREPARED.get())
        row=next(r for r in e._move_completions.values() if r['move_id']=='move/자폭')
        self.assertEqual((row['phase'],row['hp_setting_prepared']['choice']['after']),('targets',2))
        self.assertEqual((actor.hp,actor.spec['loyalty'],actor.move_uses['move/자폭']),(83,3,1))
        event=e._passive_pending;token=row['id'];e.rulings.provider=None
        loaded=self.restored(e,'homebrew');index=WORLD.actor_index(loaded)
        again=index[actor.entity_id];row=loaded._move_completions[token]
        original=deepcopy(row['hp_setting_prepared'])
        row['hp_setting_prepared']['choice']['after']=1
        with self.assertRaisesRegex(ValueError,'prepared sacrifice completion binding changed'):
            loaded.export_state()
        row['hp_setting_prepared']=original
        with patch.object(loaded.rulings,'decide',side_effect=AssertionError('paid sacrifice must not requery GM')):
            loaded.choose_passive_event(event,again,listener,
                {'decisions':{'choice':{'value':True,'reason':'resume actual native target return'}}})
        self.assertEqual(len(prompts),1)
        self.assertEqual((again.hp,again.temp_hp,again.spec['loyalty'],again.move_uses['move/자폭']),(-42,100,2,1))
        self.assertEqual(loaded._move_completions[token]['phase'],'complete')
        # The saved prior observation is historical after completion, not a lock.
        loaded.gm.observe_loyalty(again,1,reason='later legitimate relationship observation')
        final=self.restored(loaded,'homebrew')
        self.assertEqual(WORLD.actor_index(final)[again.entity_id].spec['loyalty'],1)

    def test_selected_cap_corruption_and_conflicting_R492_reject_before_resources(self):
        e,actor,_,_=self.world();actor.damage_cap['round']='down'
        before=(actor.hp,actor.temp_hp,actor.injuries)
        with self.assertRaisesRegex(ValueError,'Sturdy cap declaration changed'):e.lose_hp(actor,100,loss_kind='hp_setting')
        self.assertEqual((actor.hp,actor.temp_hp,actor.injuries),before)
        actor.damage_cap['_rule_id']='ability/옹골참-홈브류-2'
        with self.assertRaises(ValueError):e.lose_hp(actor,100,loss_kind='hp_setting')
        self.assertEqual((actor.hp,actor.temp_hp,actor.injuries),before)
        rules=Rules(str(ROOT),ruleset='all')
        with self.assertRaises(UnresolvedRuleSelection):rules.selection.resolve('ability/옹골참-홈브류-2')

    def test_unknown_as_damage_and_truthy_faint_fields_are_rejected_before_action(self):
        e,actor,target,_=self.world()
        for effect,source in [({'type':'hp_loss','value':5,'as':'other'},'move/목숨걸기'),
                              ({'type':'hp_loss','value':5,'as':'damage'},'move/몸통박치기'),
                              ({'type':'self_hp_set','self_hp':0,'faint':1},'move/목숨걸기')]:
            before=deepcopy((actor.spec,actor.hp,target.hp,e.rng.getstate()))
            with self.assertRaises(ValueError):FX.preflight_effects(e,actor,target,[effect],source)
            self.assertEqual((actor.spec,actor.hp,target.hp,e.rng.getstate()),before)

    def test_misty_explosion_selected_negative_half_uses_signed_floor_and_same_marker_boundary(self):
        e,actor,_,_=self.world();self.temp(e,actor,100)
        effect=next(x for x in e.r.move_mech('move/미스트버스트')[0]['effects_exec'] if x['type']=='self_hp_set')
        self.assertIs(effect['unpreventable'],True)
        FX.h_self_hp_set(e,actor,actor,effect,{'source_id':'move/미스트버스트'})
        self.assertEqual((actor.hp,actor.temp_hp,actor.injuries),(-42,100,3))
        self.assertTrue(actor.fainted)

    def test_public_misty_explosion_pays_self_cost_after_actual_hit_or_miss(self):
        for hit in (True,False):
            with self.subTest(hit=hit):
                e,actor,target,_=self.world();self.temp(e,actor,100)
                self.start(e,actor,target,'move/미스트버스트',hit=hit)
                e.use_move_on(actor,target,'move/미스트버스트',[actor,target],set_damage=True)
                self.assertEqual((actor.hp,actor.temp_hp,actor.injuries),(-42,100,3))
                self.assertTrue(actor.fainted)
                self.assertEqual(actor.move_uses['move/미스트버스트'],1)
                rows=[row for row in e._effect_dispatch_receipts.values()
                      if row['source_id']=='move/미스트버스트' and row['effect'].get('type')=='self_hp_set']
                self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]['status'],'completed')

    def test_public_final_gambit_keeps_self_cost_when_substitute_receives_target_damage(self):
        import substitute as SUB
        e,actor,target,_=self.world()
        e.gm.set_move(target,'move/대타출동',True,reason='actual source-owned substitute')
        e.gm.set_move(actor,'move/목숨걸기',True,reason='actual source-bound fixed damage')
        e.start_round([target,actor]);e.start_of_turn(target,initiative_count=e.initiative_value(target).value)
        e.use_move(target,target,'move/대타출동')
        coat=SUB.live(target)[0];before=(target.hp,coat['hp'])
        e.end_of_turn(target);e.start_of_turn(actor,initiative_count=e.initiative_value(actor).value)
        e.d20=lambda:10
        # The public scalar is creature damage; the coat's actual damage is separate.
        self.assertEqual(e.use_move(actor,target,'move/목숨걸기'),0)
        self.assertEqual((actor.hp,actor.fainted),(41,True))
        self.assertEqual((target.hp,SUB.live(target)[0]['hp']),(before[0],before[1]-42))
        receipts=[row['substitute_hp_loss'] for row in e._effect_dispatch_receipts.values()
                  if row['source_id']=='move/목숨걸기' and 'substitute_hp_loss' in row]
        self.assertEqual(receipts,[{'coat_id':coat['id'],'damage':42,'remaining_hp':before[1]-42}])

if __name__=='__main__':unittest.main()
