"""Native source/cost/result regressions for C3-EX-022/039/041."""
import copy, hashlib, json, sys, unittest
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules, Engine, Combatant
import combat_precision_features as CPF
import action_points as AP
import items as ITEMS
import effects as FX
import effect_contracts as EC

class FixedRng:
    def __init__(self,values):self.values=list(values)
    def randint(self,a,b):
        n=self.values.pop(0);assert a<=n<=b,(a,b,n);return n

class CombatPrecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT))
    def setUp(self):
        self.e=Engine(self.r,seed=881)
        self.a=self.actor('trainer');self.p=self.actor('partner','pokemon');self.t=self.actor('foe')
        self.a.side=self.p.side='party';self.t.side='wild';self.p.spec.update(trainer=self.a.name,trainer_id=self.a.entity_id)
        self.a.spec['feats']=[CPF.PRECISION]
        self.e.everyone=[self.a,self.p,self.t];self.e.gm.everyone=self.e.everyone[:]
        self.e.time_actors(self.e.everyone)
        self.e.gm.observe_sensory_environment(self.a,self.p,paths={"auditory":True},present=True,reason="actual Order delivery")
    def actor(self,name,kind='trainer'):
        return Combatant(self.r,dict(name=name,kind=kind,level=20,
            stats={"hp":80,"atk":20,"def":15,"spa":20,"spd":15,"spe":5},
            skills={'협박':'숙련','곡예':'전문','은신':'전문','명령':'전문','통찰':'미숙'},
            moves=['move/몸통박치기','move/불꽃세례','move/전기쇼크','move/째려보기','move/칼춤','move/스피드스타'],
            movement={'land':6}))
    def begin(self,actor=None):
        self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.a)
    def bind(self):
        self.begin();self.assertEqual(self.e.manual_feat(self.a,CPF.PINPOINT,self.p),(1,0))
    def pokemon_turn(self):
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.p)
    def move(self,actor,target,mid,face):
        self.e.rng=FixedRng([face]);result=self.e.use_move(actor,target,mid,set_damage=True)
        self.assertFalse(self.e.rng.values);return result
    def accuracy(self,actor,target,mid,face):
        return self.e.accuracy_check(actor,target,self.r.move(mid),fixed_roll=face)
    def blur(self):
        self.t.spec['feats']=[CPF.BLUR]
        self.t.spec['feature_stat_imports']={CPF.BLUR:{'mode':'apply','base_stat':self.t.stats['spe']}}
        ITEMS.register_feats(self.e,self.t)
    def demoralize(self):self.a.spec['edges']=[CPF.DEMORALIZE]
    def state(self):
        return (copy.deepcopy(getattr(self.a,"budget",None)),copy.deepcopy(self.a.spec),copy.deepcopy(self.p.conditions),self.e.rng.getstate())

    def test_sources_full_fixed_scopes_and_inherited_headers(self):
        ledger=json.loads((ROOT/'data/verification/category3-register.json').read_text('utf-8'))
        for uid in ('C3-EX-022','C3-EX-039','C3-EX-041'):
            row=next(x for x in ledger['entries'] if x['id']==uid)
            for a in row['source_snapshot']['source_anchors']:
                lines=(ROOT/a['file']).read_text('utf-8-sig').splitlines()
                self.assertEqual('\n'.join(lines[a['start_line']-1:a['end_line']]),a['excerpt'])
        lines=(ROOT/'input/ch03-skills-edges-feats.md').read_text('utf-8').splitlines()
        for n,text in [(431,'숙련 협박'),(623,'하나의 [책략]'),(806,'전문 명령 혹은 통찰'),(812,'2 AP 지속 - 기본 행동'),(813,'자신의 포켓몬'),(827,'전문 곡예, 전문 은신'),(605,'+1')]:self.assertIn(text,lines[n-1])

    def test_demoralize_native_status_nineteen_and_expanded_eighteen(self):
        for face,expanded,expected in [(18,False,False),(19,False,True),(18,True,True),(17,True,False)]:
            self.setUp();self.demoralize();ITEMS.register_feats(self.e,self.a)
            if expanded:self.a.modifiers.append({'type':'crit_range','min':19})
            self.begin();self.move(self.a,self.t,'move/째려보기',face)
            self.assertEqual('취약' in self.t.conditions,expected)
            self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.t.stages['def'],-1)

    def test_demoralize_native_physical_crit_and_friend_exclusion(self):
        for side,expected in [('wild',True),('party',False)]:
            self.setUp();self.demoralize();self.t.side=side;self.begin()
            self.move(self.a,self.t,'move/몸통박치기',20)
            self.assertEqual('취약' in self.t.conditions,expected)

    def test_demoralize_no_ac_status_cannot_crit_from_incidental_face(self):
        self.demoralize()
        # Actual no-AC status entry, even through the standalone accuracy facade.
        self.assertIsNone(self.r.move('move/칼춤')['ac'])
        self.assertFalse(self.accuracy(self.a,self.t,'move/칼춤',20)[2])
        self.begin();self.e.rng=FixedRng([]);self.e.use_move(self.a,self.a,'move/칼춤')
        self.assertFalse(self.e.rng.values);self.assertNotIn('취약',self.a.conditions)

    def test_demoralize_unowned_prerequisite_and_duplicate_pre_cost(self):
        self.begin();self.move(self.a,self.t,'move/째려보기',20);self.assertNotIn('취약',self.t.conditions)
        for bad in ('rank','duplicate','pokemon'):
            self.setUp();self.demoralize()
            if bad=='rank':self.a.spec['skills']['협박']='초보'
            elif bad=='duplicate':self.a.spec['edges'].append('Demoralize')
            else:self.a.kind='pokemon'
            self.begin();before=self.state()
            with self.assertRaises(ValueError):self.e.use_move(self.a,self.t,'move/째려보기')
            self.assertEqual(before,self.state())

    def test_demoralize_missing_foe_relation_refuses_before_cost(self):
        self.demoralize();self.t.side=None;self.begin();before=self.state()
        with self.assertRaisesRegex(ValueError,'friend/foe'):self.e.use_move(self.a,self.t,'move/째려보기')
        self.assertEqual(before,self.state())

    def test_demoralize_miss_is_not_a_critical_hit(self):
        self.demoralize();self.begin();self.move(self.a,self.t,'move/째려보기',1)
        self.assertNotIn('취약',self.t.conditions);self.assertEqual(self.t.stages['def'],0)

    def test_blur_native_never_miss_now_rolls_ac_two(self):
        for face,expected in [(1,False),(2,False),(3,True),(20,True)]:
            self.setUp();self.blur();ITEMS.register_feats(self.e,self.t);self.begin(self.p)
            before=self.t.hp;self.move(self.p,self.t,'move/스피드스타',face)
            self.assertEqual(self.t.hp<before,expected);self.assertEqual(self.p.budget['standard'],0)

    def test_blur_half_evasion_rounds_down_and_keeps_ordinary_full_evasion(self):
        self.blur();self.t.stats['spd']=30;self.t.evasion_mod=3 # capped total 9 -> half 4
        self.assertFalse(self.accuracy(self.p,self.t,'move/스피드스타',5)[0])
        self.assertTrue(self.accuracy(self.p,self.t,'move/스피드스타',6)[0])
        self.assertFalse(self.accuracy(self.p,self.t,'move/불꽃세례',10)[0])
        self.assertTrue(self.accuracy(self.p,self.t,'move/불꽃세례',11)[0])

    def test_blur_unowned_does_not_change_never_miss(self):
        self.assertTrue(self.accuracy(self.p,self.t,'move/스피드스타',1)[0])

    def test_blur_vulnerable_has_zero_half_evasion(self):
        self.blur();self.e.apply_status(self.t,'취약')
        self.assertTrue(self.accuracy(self.p,self.t,'move/스피드스타',2)[0])

    def test_blur_self_target_no_accuracy_move_uses_real_roll(self):
        self.a.spec['feats']=[CPF.BLUR]
        self.a.spec['feature_stat_imports']={CPF.BLUR:{'mode':'apply','base_stat':self.a.stats['spe']}}
        ITEMS.register_feats(self.e,self.a);self.begin()
        self.move(self.a,self.a,'move/칼춤',1);self.assertEqual(self.a.stages['atk'],0)

    def test_blur_both_prerequisites_and_selected_source_before_cost(self):
        for skill in ('곡예','은신'):
            self.setUp();self.blur();self.t.spec['skills'][skill]='숙련';self.begin(self.p)
            before=(dict(self.p.budget),dict(self.p.move_uses),self.e.rng.getstate())
            with self.assertRaisesRegex(ValueError,'Expert Acrobatics and Expert Stealth'):self.e.use_move(self.p,self.t,'move/스피드스타')
            self.assertEqual(before,(dict(self.p.budget),dict(self.p.move_uses),self.e.rng.getstate()))
        self.setUp();self.blur();original=self.r._selected_rule
        self.r._selected_rule=lambda uid,**kwargs: uid+'-other' if uid==CPF.BLUR else original(uid,**kwargs)
        try:
            with self.assertRaisesRegex(ValueError,'selected feature'):self.accuracy(self.p,self.t,'move/스피드스타',10)
        finally:self.r._selected_rule=original

    def test_pinpoint_native_manual_activation_binds_two_ap_and_standard_once(self):
        ITEMS.register_feats(self.e,self.a);self.bind()
        self.assertEqual(self.a.budget['standard'],0);self.assertEqual(AP.available(self.a),AP.maximum(self.a)-2)
        self.assertIs(CPF.binding(self.e,self.p)['owner'],self.a)
        self.assertEqual(self.a.spec.get('ap_spent',0),0)

    def test_pinpoint_ownership_and_prerequisites_reject_without_cost(self):
        for mode in ('unowned','rank','foreign','self','not_live','outside'):
            self.setUp();target=self.p
            if mode=='unowned':self.a.spec['feats']=[]
            if mode=='rank':self.a.spec['skills']['명령']='숙련'
            if mode=='foreign':self.p.spec['trainer']='someone else'
            if mode=='self':target=self.a
            if mode=='not_live':target=self.actor('clone','pokemon');target.spec['trainer']=self.a.name
            if mode!='outside':self.begin()
            before=self.state()
            with self.assertRaises(ValueError):self.e.manual_feat(self.a,CPF.PINPOINT,target)
            self.assertEqual(before,self.state());self.assertNotIn(CPF.KEY,self.p.custom_conditions)

    def test_pinpoint_perception_alternative_and_child_ownership_requires_parent(self):
        self.a.spec['skills']['명령']='미숙';self.a.spec['skills']['통찰']='전문';self.bind()
        self.setUp();self.a.spec['feats']=[CPF.PINPOINT]
        with self.assertRaisesRegex(ValueError,'acquired Precision Orders'):ITEMS.register_feats(self.e,self.a)

    def test_pinpoint_insufficient_ap_and_duplicate_preserve_state(self):
        self.begin();self.a.spec['ap_spent']=AP.maximum(self.a)-1;before=self.state()
        with self.assertRaisesRegex(ValueError,'two available AP'):self.e.manual_feat(self.a,CPF.PINPOINT,self.p)
        self.assertEqual(before,self.state())
        self.setUp();self.bind();before=dict(self.a.spec['ap_bound'])
        with self.assertRaisesRegex(ValueError,'only one Stratagem'):self.e.manual_feat(self.a,CPF.PINPOINT,self.p)
        self.assertEqual(before,self.a.spec['ap_bound'])

    def test_pinpoint_damaging_accuracy_plus_two_no_status_accuracy_bonus(self):
        self.bind()
        self.assertTrue(self.accuracy(self.p,self.t,'move/불꽃세례',3)[0]) # 3+2 == AC2+eva3
        self.assertFalse(self.accuracy(self.p,self.t,'move/째려보기',2)[0])
        self.assertFalse(self.accuracy(self.a,self.t,'move/불꽃세례',3)[0])
        self.assertFalse(self.accuracy(self.p,self.t,'move/불꽃세례',1)[0])

    def test_pinpoint_legacy_secondary_effect_native_ember_at_sixteen(self):
        self.bind();self.pokemon_turn();self.move(self.p,self.t,'move/불꽃세례',16)
        self.assertIn('화상',self.t.conditions)
        self.setUp();self.begin(self.p);self.move(self.p,self.t,'move/불꽃세례',16)
        self.assertNotIn('화상',self.t.conditions)

    def test_pinpoint_dispatch_secondary_native_thundershock_at_fifteen(self):
        self.bind();self.pokemon_turn();self.move(self.p,self.t,'move/전기쇼크',15)
        self.assertIn('마비',self.t.conditions)

    def test_pinpoint_secondary_bonus_never_changes_critical_or_even_face(self):
        self.bind();self.assertFalse(self.accuracy(self.p,self.t,'move/불꽃세례',18)[2])
        ctx=dict(attacker=self.p,target=self.t,move=self.r.move('move/불꽃세례'),nat=15,hit=True)
        eff={'type':'apply_status','status':'화상','on_natural_roll_min':17}
        self.assertTrue(FX.cond_ok(self.e,eff,ctx)[0]);self.assertEqual(EC.condition(self.e,eff,ctx).truth,EC.ROOT.Truth.TRUE)
        self.assertFalse(FX.cond_ok(self.e,dict(type='apply_status',status='화상',on_natural_roll='even'),ctx)[0])
        self.assertEqual(ctx['nat'],15)

    def test_pinpoint_damage_penalty_precedes_weakness_resistance_and_floor(self):
        self.bind();move=self.r.move('move/불꽃세례')
        self.t.types=[];neutral=self.e.roll_damage(self.p,self.t,move,set_damage=True)
        self.t.types=['풀'];weak=self.e.roll_damage(self.p,self.t,move,set_damage=True)
        self.t.types=['물'];resist=self.e.roll_damage(self.p,self.t,move,set_damage=True)
        self.assertEqual(weak,int(neutral*1.5));self.assertEqual(resist,int(neutral*.5))
        row=CPF.binding(self.e,self.p);CPF._unbind(self.e,self.p,row)
        self.t.types=[];plain=self.e.roll_damage(self.p,self.t,move,set_damage=True)
        self.assertEqual(neutral,plain-5)
        self.setUp();self.bind();self.t.stats['spd']=999;self.t.types=[]
        self.assertEqual(self.e.roll_damage(self.p,self.t,move,set_damage=True),1)

    def test_pinpoint_free_release_requires_owner_turn_and_releases_exact_binding(self):
        self.bind();self.a.spec['ap_bound']['other-source']=1
        self.assertEqual(self.e.release_pinpoint_strike(self.a,self.p),(1,0))
        self.assertEqual(self.a.spec['ap_bound'],{'other-source':1});self.assertNotIn(CPF.KEY,self.p.custom_conditions)
        self.assertIn('free',self.a._action_history)
        with self.assertRaises(ValueError):self.e.release_pinpoint_strike(self.a,self.p)

    def test_pinpoint_offturn_release_fails_without_refund(self):
        self.bind();self.pokemon_turn();before=dict(self.a.spec['ap_bound'])
        self.assertEqual(self.e.release_pinpoint_strike(self.a,self.p),(0,1))
        self.assertEqual(self.a.spec['ap_bound'],before);self.assertIn(CPF.KEY,self.p.custom_conditions)

    def test_pinpoint_snapshot_keeps_actual_trainer_and_target(self):
        self.bind();self.e.gm.snapshot('precision');self.e.release_pinpoint_strike(self.a,self.p)
        self.e.gm.restore('precision');row=CPF.binding(self.e,self.p)
        self.assertIs(row['owner'],self.a);self.assertIs(row['target'],self.p)
        self.assertEqual(CPF.accuracy_bonus(self.e,self.p,self.r.move('move/불꽃세례')),2)

    def test_pinpoint_encounter_end_unbinds_without_refreshing_other_ap(self):
        self.bind();self.a.spec['ap_spent']=1;self.a.spec['ap_bound']['other-source']=1
        self.e.end_encounter()
        self.assertNotIn(CPF.KEY,self.p.custom_conditions);self.assertEqual(self.a.spec['ap_bound'],{'other-source':1})
        self.assertEqual(self.a.spec['ap_spent'],1)

    def test_pinpoint_multiple_pokemon_have_separate_costs_and_release(self):
        q=self.actor('second','pokemon');q.spec.update(trainer=self.a.name,trainer_id=self.a.entity_id);q.side='party'
        self.e.gm.add_combatant(q,reason='actual second owned Pinpoint partner')
        self.e.gm.observe_sensory_environment(self.a,q,paths={'auditory':True},present=True,reason='actual second partner Order delivery')
        self.bind()
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
        self.assertEqual(self.e.manual_feat(self.a,CPF.PINPOINT,q),(1,0));self.assertEqual(sum(self.a.spec['ap_bound'].values()),4)
        self.e.release_pinpoint_strike(self.a,self.p);self.assertEqual(sum(self.a.spec['ap_bound'].values()),2)
        self.assertIsNotNone(CPF.binding(self.e,q))

    def test_pinpoint_corrupt_binding_and_source_change_prevent_attack_before_cost(self):
        self.bind();self.pokemon_turn();row=CPF.binding(self.e,self.p)
        self.a.spec['ap_bound'][row['instance']]=1;before=(dict(self.p.budget),self.e.rng.getstate())
        with self.assertRaisesRegex(ValueError,'matching two AP'):self.e.use_move(self.p,self.t,'move/불꽃세례')
        self.assertEqual(before,(dict(self.p.budget),self.e.rng.getstate()))

    def test_pinpoint_actual_id_owner_and_same_name_foreign_id_rejected(self):
        self.p.spec.pop('trainer');self.p.spec['trainer_id']=self.a.entity_id
        self.bind();self.assertIs(CPF.binding(self.e,self.p)['owner'],self.a)
        self.setUp();other=self.actor(self.a.name)
        self.e.gm.add_combatant(other,reason='actual distinct same-name foreign Trainer')
        self.p.spec['trainer_id']=other.entity_id;self.begin()
        before=self.state()
        with self.assertRaisesRegex(ValueError,'different trainer identity'):self.e.manual_feat(self.a,CPF.PINPOINT,self.p)
        self.assertEqual(before,self.state())

    def test_pinpoint_conflicting_owner_fields_and_ambiguous_names_rejected(self):
        self.p.spec.update(trainer_id=self.a.entity_id,trainer='contradictory');self.begin()
        with self.assertRaisesRegex(ValueError,'conflicting'):self.e.manual_feat(self.a,CPF.PINPOINT,self.p)
        self.setUp();self.p.spec.pop('trainer_id');other=self.actor(self.a.name);self.e.everyone.append(other);self.begin()
        with self.assertRaisesRegex(ValueError,'unambiguous'):self.e.manual_feat(self.a,CPF.PINPOINT,self.p)

    def test_pinpoint_encounter_subset_end_clears_off_field_bound_target(self):
        self.bind();self.p.on_field=False
        self.e.end_encounter(combatants=[self.a])
        self.assertFalse(self.e.encounter_active);self.assertNotIn(CPF.KEY,self.p.custom_conditions)
        self.assertEqual(self.a.spec['ap_bound'],{})

    def test_blur_speed_tag_apply_once_and_included_import_never_double_add(self):
        self.blur();self.assertEqual(self.t.stats['spe'],6);self.assertEqual(self.t.spec['stats']['spe'],6)
        ITEMS.register_feats(self.e,self.t);self.assertEqual(self.t.stats['spe'],6)
        receipt=self.t.custom_conditions['_feature_stat_receipts'][CPF.BLUR]
        self.assertEqual((receipt['source'],receipt['before'],receipt['delta'],receipt['after']),(CPF.BLUR,5,1,6))
        self.setUp();self.t.spec['feats']=[CPF.BLUR]
        self.t.spec['feature_stat_imports']={CPF.BLUR:{'mode':'included','base_stat':4}}
        ITEMS.register_feats(self.e,self.t);self.assertEqual(self.t.stats['spe'],5)
        ITEMS.register_feats(self.e,self.t);self.assertEqual(self.t.stats['spe'],5)

    def test_blur_bare_owned_feature_missing_stat_receipt_cannot_bypass(self):
        self.t.spec['feats']=[CPF.BLUR];self.begin(self.p)
        before=(dict(self.p.budget),self.e.rng.getstate(),self.t.stats['spe'])
        with self.assertRaisesRegex(ValueError,'explicit apply or included'):self.e.use_move(self.p,self.t,'move/스피드스타')
        self.assertEqual(before,(dict(self.p.budget),self.e.rng.getstate(),self.t.stats['spe']))
        self.t.spec['feature_stat_imports']={CPF.BLUR:{'mode':'apply','base_stat':5}}
        with self.assertRaisesRegex(ValueError,'registered acquisition receipt'):self.e.use_move(self.p,self.t,'move/스피드스타')
        self.assertEqual(before,(dict(self.p.budget),self.e.rng.getstate(),self.t.stats['spe']))

    def test_blur_import_rejects_mismatched_original_stat_without_change(self):
        self.t.spec['feats']=[CPF.BLUR]
        for mode,base in [('included',5),('apply',4),('apply',True)]:
            self.t.spec['feature_stat_imports']={CPF.BLUR:{'mode':mode,'base_stat':base}}
            with self.assertRaises(ValueError):ITEMS.register_feats(self.e,self.t)
            self.assertEqual(self.t.stats['spe'],5);self.assertNotIn('_feature_stat_receipts',self.t.custom_conditions)

    def test_blur_acquired_speed_changes_native_speed_evasion_and_snapshot_once(self):
        self.t.stats['spe']=9;self.t.spec['stats']['spe']=9;self.blur()
        self.assertEqual(self.t.evasion('변화'),2)
        self.e.gm.snapshot('blur');self.t.stats['spe']=88;self.t.custom_conditions.clear()
        self.e.gm.restore('blur');ITEMS.register_feats(self.e,self.t)
        self.assertEqual(self.t.stats['spe'],10);self.assertEqual(self.t.evasion('변화'),2)

    def test_pinpoint_native_capture_id_is_accepted_without_name_owner(self):
        self.a.spec['items']={'몬스터볼':1};self.a.pos=(0,0);self.p.pos=(1,0)
        self.p.spec.pop('trainer');self.p.spec.pop('trainer_id');self.p.side='wild';self.p.hp=1
        self.assertTrue(self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=20))
        self.assertEqual(self.p.spec['trainer_id'],self.a.spec['id']);self.assertNotIn('trainer',self.p.spec)
        # The captured Pokemon is deployed in the next encounter, preserving the
        # actual ownership record emitted by throw_ball.
        self.p.captured=False;self.p.on_field=True;self.p.side='party'
        self.e.gm.observe_sensory_environment(self.a,self.p,paths={'auditory':True},present=True,
            reason='actual newly deployed captured Pokemon hears the current Pinpoint Order at its new position')
        self.bind();self.assertIs(CPF.binding(self.e,self.p)['owner'],self.a)

    def test_pinpoint_critical_damage_reduction_is_five_not_ten(self):
        self.bind();move=self.r.move('move/불꽃세례')
        modified=self.e.roll_damage(self.p,self.t,move,crit=True,set_damage=True)
        CPF._unbind(self.e,self.p,CPF.binding(self.e,self.p))
        ordinary=self.e.roll_damage(self.p,self.t,move,crit=True,set_damage=True)
        self.assertEqual(ordinary-modified,5)

    def test_pinpoint_active_selected_source_change_blocks_before_cost(self):
        self.bind();self.pokemon_turn();before=(dict(self.p.budget),self.e.rng.getstate())
        original=self.r._selected_rule
        self.r._selected_rule=lambda uid,**kwargs: uid+'-variant' if uid==CPF.PINPOINT else original(uid,**kwargs)
        try:
            with self.assertRaisesRegex(ValueError,'selected rule changed'):self.e.use_move(self.p,self.t,'move/불꽃세례')
            self.assertEqual(before,(dict(self.p.budget),self.e.rng.getstate()))
        finally:self.r._selected_rule=original

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(CombatPrecisionTests)
    names=[x.id().split('.')[-1] for x in suite]
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    failed={x.id().split('.')[-1]:tb for x,tb in result.failures+result.errors}
    paths=['engine/'+p.name for p in (ROOT/'engine').glob('*.py')] + ['tools/test_category3_combat_precision.py','input/ch03-skills-edges-feats.md','data/feats-mech.json','data/edges-llm.json','data/core-rules.json','data/conditions.json','data/skill-check-policy.json','data/rulesets.json','output/source-audit/2026-10-10/ptu-core-1.05.pdf']
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),
            'scope':['C3-EX-022','C3-EX-039','C3-EX-041'],
            'results':[{'id':n,'status':'fail' if n in failed else 'pass'} for n in names],
            'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
            'tested':result.testsRun,
            'passed':result.testsRun-len(failed),'failed':len(failed),
            'tests':[{'name':n,'status':'FAIL' if n in failed else 'PASS',**({'error':failed[n]} if n in failed else {})} for n in names]}
    (ROOT/'output/category3-combat-precision-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    sys.exit(not result.wasSuccessful())
