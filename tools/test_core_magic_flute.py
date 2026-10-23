"""Actual C09-082 instrument activation, ownership, native cures and persistence."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import unittest

import test_category2_dream_mist as FIX
from grid import Grid
import body_state as BODY
import common_checks as C
import equipment_item_contracts as CONTRACTS
import frequency as FREQ
import items as ITEMS
import magic_flute as FLUTE
import state_codec as CODEC
import source_context
import world_entities as W


class Tests(unittest.TestCase):
    setUpClass=classmethod(FIX.Tests.setUpClass.__func__)
    add=FIX.Tests.add
    pokemon=FIX.Tests.pokemon
    restored=FIX.Tests.restored
    begin=FIX.Tests.begin

    def setUp(self):
        FIX.Tests.setUp(self)
        self.e.grid=Grid(50,15)
        for c in self.e.everyone:c.spec['size']='중형'
        self.a.pos=(1,3);self.p.pos=(3,3);self.t.pos=(7,3)

    def make(self,actor=None,uid='flute',source='item/마법피리-1',condition='화상',available=True,observe=True):
        actor=actor or self.a
        W.register_object(self.e,uid,location={'kind':'unknown'},reason='observed actual manufactured instrument',
                          kind='item_instance',item_rule_id=source,owner_id=actor.entity_id)
        if observe:
            self.e.gm.observe_magic_flute(uid,manufactured_condition=condition,calendar_owner=self.a,
                day=self.a.spec.get('frequency_state',{}).get('day',0),available=available,
                reason='GM verified original manufacture choice and current charge')
        ITEMS.equip_held(self.e,actor,source,source_instance_id=uid)
        return uid

    def use(self,actor=None,uid='flute',source='item/마법피리-1',**options):
        return self.e.use_item(actor or self.a,source,held_selection=uid,**options)

    def snapshot(self):
        return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),[vars(x) for x in self.e.gm.everyone],
                         self.e._physical_objects,self.e.log_lines,self.e.rulings.log),{id(self.r):self.r})

    def afflicted(self,*actors,condition='화상',**kwargs):
        for c in actors:self.e.apply_status(c,condition,force=True,source='fixture:actual-condition',**kwargs)

    def test_catalog_reuses_native_selection_and_freshness_still_rejects_before_cost(self):
        with patch.object(self.r,'_selected_rule',wraps=self.r._selected_rule) as selected, \
                patch.object(source_context,'verified_source',wraps=source_context.verified_source) as verified:
            header=CONTRACTS.selected_item(self.r,'item/마법피리')
        self.assertEqual(header['id'],'item/마법피리')
        self.assertEqual(sum(call.args[0]=='item/마법피리' for call in selected.call_args_list),1)
        chapter=[call.args[1] for call in verified.call_args_list
                 if call.args[1]['file']=='input/ch09-equipment.md']
        self.assertEqual(len(chapter),2)
        self.assertTrue(all(ref['sha256']==FLUTE.SOURCE_SHA256 for ref in chapter))
        self.make();self.begin(self.a);before=self.snapshot();native=Path.read_bytes
        def changed(path):
            return native(path)+(b'changed' if path.name=='ch09-equipment.md' else b'')
        with patch.object(Path,'read_bytes',changed):
            with self.assertRaisesRegex(ValueError,'changed'):self.use()
        self.assertEqual(self.snapshot(),before)

    def test_native_entry_cures_all_radial_kinds_sides_self_and_body_boundary(self):
        from builder import build_trainer
        enemy=self.add(build_trainer(self.r,'opponent',10,dict.fromkeys(('hp','atk','def','spa','spd','spe'),8)))
        enemy.spec['size']='중형';enemy.pos=(10,4);enemy.side='enemy';self.t.side='enemy'
        boundary=self.pokemon(size='대형');boundary.pos=(22,3)
        BODY.observe(self.e,boundary,[(-1,0),(0,0)],reason='observed body extends into radius20')
        far=self.pokemon(size='중형');far.pos=(22,6)
        self.make();self.begin(self.a)
        self.afflicted(self.a,self.p,self.t,enemy,boundary,far)
        self.e.apply_status(self.p,'독',force=True,source='fixture:unrelated')
        inventory=deepcopy(self.a.spec['items']);rng=self.e.rng.getstate()
        out=self.use(accepted=False)
        expected={c.entity_id for c in (self.a,self.p,self.t,enemy,boundary)}
        self.assertEqual(set(out['recipients']),expected);self.assertEqual(set(out['cured']),expected)
        self.assertIn('화상',far.conditions);self.assertIn('독',self.p.conditions)
        self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a.spec['items'],inventory)
        self.assertEqual(self.e.rng.getstate(),rng);self.assertNotIn('consumed',self.e._physical_objects['flute'])
        self.assertEqual(self.r.item_effects('item/마법피리-1')[1]['price'],4000)
        self.assertTrue(self.e.validate_state()['valid'])

    def test_both_exact_sources_and_actor_kinds_use_native_condition_end_consumers(self):
        import condition_instances as INSTANCES,dream_state as DREAM
        for actor_kind,source,condition in [('trainer','item/마법피리','잠듦'),
                ('pokemon','item/마법피리-1','사슬묶기')]:
            with self.subTest(actor_kind=actor_kind,source=source):
                self.setUp();actor=self.a if actor_kind=='trainer' else self.p
                self.make(actor,source=source,condition=condition);self.begin(actor)
                kwargs={'parameters':{'move_id':'move/튀어오르기'}} if condition=='사슬묶기' else {}
                self.afflicted(self.t,condition=condition,**kwargs)
                if condition=='잠듦':self.assertIsNotNone(self.t.spec[DREAM.KEY]['active'])
                else:self.assertTrue(INSTANCES.records(self.t,condition))
                known=list(actor.moves);out=self.use(actor,source=source)
                self.assertIn(self.t.entity_id,out['cured']);self.assertNotIn(condition,self.t.conditions)
                self.assertFalse(INSTANCES.records(self.t,condition));self.assertEqual(actor.moves,known)
                if condition=='잠듦':self.assertIsNone(self.t.spec[DREAM.KEY].get('active'))
                self.assertEqual(actor.budget['standard'],0)

    def test_unknown_manufacture_quantity_and_geometry_stay_pending_without_cost(self):
        self.a.spec['items']['item/마법피리-1']=3;self.begin(self.a)
        before=self.snapshot();self.assertIsInstance(self.e.use_item(self.a,'item/마법피리-1'),C.PendingDecision)
        self.assertEqual(self.snapshot(),before)
        self.make(observe=False);before=self.snapshot()
        result=self.use();self.assertIsInstance(result,C.PendingDecision)
        self.assertIn('manufacture',result.required);self.assertEqual(self.snapshot(),before)
        self.e.gm.observe_magic_flute('flute',manufactured_condition='화상',calendar_owner=self.a,
            day=0,available=True,reason='actual imported flute choice and charge observed')
        self.t.spec.pop('size');before=self.snapshot()
        self.assertIsInstance(self.use(),C.PendingDecision);self.assertEqual(self.snapshot(),before)
        BODY.observe(self.e,self.t,[(0,0)],reason='GM observes unknown body before flute')
        self.e.grid=None;before=self.snapshot()
        self.assertIsInstance(self.use(),C.PendingDecision);self.assertEqual(self.snapshot(),before)

    def test_observed_choice_is_fixed_and_imported_spent_tool_stays_spent(self):
        self.make(available=False);self.begin(self.a);before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'already used'):self.use()
        self.assertEqual(self.snapshot(),before)
        for change in ({'manufactured_condition':'独'},{'manufactured_condition':'독'},
                       {'available':True},{'day':1},{'calendar_owner':self.p}):
            declaration=dict(manufactured_condition='화상',calendar_owner=self.a,day=0,available=False,
                             reason='GM verified original manufacture choice and current charge')
            declaration.update(change)
            with self.assertRaises(ValueError):self.e.gm.observe_magic_flute('flute',**declaration)
            self.assertEqual(self.snapshot(),before)
        self.e.gm.observe_magic_flute('flute',manufactured_condition='화상',calendar_owner=self.a,
            day=0,available=False,reason='GM verified original manufacture choice and current charge')
        self.assertEqual(self.snapshot(),before)
        FREQ.new_day(self.a);self.afflicted(self.t);self.assertIn(self.t.entity_id,self.use()['cured'])

    def test_other_conditions_cannot_be_manufacture_choices_or_saved_cure_authority(self):
        self.make(observe=False)
        for condition in ('기절','사망','실명','완전-실명','둔화','구속','수렁','넘어짐','취약','임시-체력'):
            with self.subTest(condition=condition):
                before=self.snapshot()
                with self.assertRaisesRegex(ValueError,'ordinary curable condition'):
                    self.e.gm.observe_magic_flute('flute',manufactured_condition=condition,
                        calendar_owner=self.a,day=0,available=True,reason='invalid imported choice')
                self.assertEqual(self.snapshot(),before)
        self.e.gm.observe_magic_flute('flute',manufactured_condition='화상',calendar_owner=self.a,
            day=0,available=True,reason='actual status affliction manufacture choice')
        # The domain validator must reject an Other Condition even if an
        # externally edited profile has a matching structural fingerprint.
        import resolution_transaction as TX
        obj=self.e._physical_objects['flute'];saved=deepcopy(obj[FLUTE.PROFILE])
        obj[FLUTE.PROFILE]['condition']='취약'
        profile=obj[FLUTE.PROFILE]
        profile['sha256']=TX.request_fingerprint({k:v for k,v in profile.items() if k!='sha256'})
        with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
        with self.assertRaises(ValueError):self.e.gm.snapshot('invalid-other-condition')
        obj[FLUTE.PROFILE]=saved
        self.begin(self.a);self.afflicted(self.t)
        self.e.apply_status(self.t,'취약',force=True,source='fixture:unrelated-other-condition')
        result=self.use()
        self.assertIn(self.t.entity_id,result['cured']);self.assertIn('취약',self.t.conditions)

    def test_transfer_reregister_and_holder_day_cannot_refresh_physical_daily_identity(self):
        self.make();self.begin(self.a);self.use();original=deepcopy(self.e._physical_objects['flute'])
        ITEMS.transfer_equipment(self.e,self.a,self.p,'flute')
        FREQ.new_day(self.p);self.begin(self.p);before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'already used'):self.use(self.p)
        self.assertEqual(self.snapshot(),before)
        ITEMS.drop_equipment(self.e,self.p,['flute'],slots=('held',),consent_by=(self.p,))
        W.register_object(self.e,'flute',location={'kind':'unknown'},reason='observed sale of same real instrument',
            kind='item_instance',item_rule_id='item/마법피리-1',owner_id=self.p.entity_id)
        ITEMS.equip_held(self.e,self.p,'item/마법피리-1',source_instance_id='flute')
        self.assertEqual(self.e._physical_objects['flute'][FLUTE.PROFILE],original[FLUTE.PROFILE])
        self.assertEqual(self.e._physical_objects['flute']['frequency_state'],original['frequency_state'])
        with self.assertRaisesRegex(ValueError,'already used'):self.use(self.p)
        FREQ.new_day(self.a);self.afflicted(self.t);self.assertIn(self.t.entity_id,self.use(self.p)['cured'])
        self.assertTrue(self.e.validate_state()['valid'])

    def test_separate_tools_remain_independent_and_scene_and_elapsed_time_do_not_reset(self):
        self.make();self.make(self.p,uid='other');self.begin(self.a);self.use()
        self.begin(self.p);self.assertEqual(self.use(self.p,uid='other')['frequency']['used'],1)
        self.e.end_of_turn(self.p);self.e.end_scene();self.e.advance_time(86400)
        self.begin(self.a)
        with self.assertRaisesRegex(ValueError,'already used'):self.use()
        FREQ.new_day(self.a);self.assertEqual(self.use()['frequency']['period'],1)
        self.begin(self.p);self.assertEqual(self.use(self.p,uid='other')['frequency']['period'],1)

    def test_cost_options_source_and_unusable_body_reject_without_changing_any_state(self):
        self.make();self.begin(self.a)
        for options in ({'free':True},{'count':2},{'selected_move':'move/튀어오르기'},
                        {'food_policy':'custom'},{'aim':[(1,1)]},{'fixed_accuracy':20},
                        {'duration_minutes':1},{'resumable':True}):
            before=self.snapshot()
            with self.assertRaises(ValueError):self.use(**options)
            self.assertEqual(self.snapshot(),before)
        before=self.snapshot()
        with self.assertRaises(ValueError):self.e.use_item(self.a,'item/마법피리-1',self.t,held_selection='flute')
        self.assertEqual(self.snapshot(),before)
        original=self.r._selected_rule
        with patch.object(self.r,'_selected_rule',side_effect=lambda uid,*a,**k:'custom/changed' if uid=='item/마법피리-1' else original(uid,*a,**k)):
            with self.assertRaises(ValueError):self.use()
        self.assertEqual(self.snapshot(),before)
        self.a.injuries=5;before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'heavy-injury'):self.use()
        self.assertEqual(self.snapshot(),before);self.a.injuries=0
        self.e._physical_objects['flute']['disabled']=True;before=self.snapshot()
        with self.assertRaises(ValueError):self.use()
        self.assertEqual(self.snapshot(),before)

    def test_insufficient_action_and_failures_after_quota_or_partial_cure_are_atomic(self):
        self.make();self.begin(self.a);self.afflicted(self.p,self.t)
        self.a.budget['standard']=0;before=self.snapshot();self.assertEqual(self.use(),(0,0))
        self.assertEqual(self.snapshot()[:4],before[:4]);self.begin(self.a)
        before=self.snapshot();original=type(self.e).cure_status
        def fail_after_cure(e,target,condition):
            original(e,target,condition)
            if target.entity_id==self.p.entity_id:raise RuntimeError('injected after partial radial cure')
        with patch.object(type(self.e),'cure_status',fail_after_cure):
            with self.assertRaisesRegex(RuntimeError,'partial radial'):self.use()
        self.assertEqual(self.snapshot(),before)
        original_quota=FREQ.consume_physical_activation
        def quota_failure(e,obj,key,frequency):
            original_quota(e,obj,key,frequency);e.rng.randint(1,20)
            raise RuntimeError('injected after physical quota debit')
        with patch.object(FREQ,'consume_physical_activation',quota_failure):
            with self.assertRaisesRegex(RuntimeError,'physical quota'):self.use()
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(set(self.use()['cured']),{self.p.entity_id,self.t.entity_id})

    def test_both_restore_boundaries_keep_spent_tool_and_reject_fixed_choice_or_quota_tampering(self):
        self.make();self.begin(self.a);self.afflicted(self.t);self.use();self.e.gm.snapshot('spent')
        restored=self.restored();index=W.actor_index(restored);actor=index[self.a.entity_id]
        self.assertEqual(restored._physical_objects,self.e._physical_objects)
        with self.assertRaisesRegex(ValueError,'already used'):
            restored.use_item(actor,'item/마법피리-1',held_selection='flute')
        FREQ.new_day(self.a);self.e.gm.restore('spent')
        with self.assertRaisesRegex(ValueError,'already used'):self.use()
        self.assertNotIn('화상',self.t.conditions)
        for field,value in [('condition','독'),('source','item/마법피리'),('calendar_owner_id',self.p.entity_id)]:
            old=deepcopy(self.e._physical_objects['flute']);before=self.snapshot()
            self.e._physical_objects['flute'][FLUTE.PROFILE][field]=value
            with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
            with self.assertRaises(ValueError):self.e.gm.snapshot('invalid')
            self.e._physical_objects['flute']=old;self.assertEqual(self.snapshot(),before)
        snap=self.e.gm.snapshots['spent'];saved=deepcopy(snap['engine']['_physical_objects'])
        snap['engine']['_physical_objects']['flute']['frequency_state']['activations']['item/마법피리-1']['used']=0
        before=self.snapshot()
        with self.assertRaises(ValueError):self.e.gm.restore('spent')
        self.assertEqual(self.snapshot(),before);snap['engine']['_physical_objects']=saved
        payload=self.e.export_state()
        # State codec nodes preserve this plain native activation row verbatim.
        changed=False
        for node in payload['nodes'].values():
            if node.get('kind')=='dict' and ['kind','daily'] in node.get('items',[]) and ['used',1] in node.get('items',[]):
                node['items']=[['used',0] if pair==['used',1] else pair for pair in node['items']];changed=True;break
        self.assertTrue(changed)
        with self.assertRaises(CODEC.StateCodecError):type(self.e).import_state(self.r,payload)

    def test_selected_session_policy_reuses_native_reference_calendar_and_adoption_preserves_charge(self):
        self.make();self.begin(self.a);self.use();self.e.end_of_turn(self.a);self.e.end_encounter(self.e.everyone)
        # Adopting the existing optional campaign policy is not a refill.
        self.e.session_frequency=True;self.e.defer_session_refresh=False
        self.assertEqual(self.e.begin_session('first',self.e.everyone),'initialized')
        self.begin(self.a)
        with self.assertRaisesRegex(ValueError,'already used'):self.use()
        FREQ.new_day(self.a)
        with self.assertRaisesRegex(ValueError,'already used'):self.use()
        self.e.end_of_turn(self.a);self.e.end_encounter(self.e.everyone)
        self.assertEqual(self.e.begin_session('second',self.e.everyone),'refreshed');self.begin(self.a)
        self.assertEqual(self.use()['frequency']['period'],['session',1])
        self.assertTrue(self.restored().validate_state()['valid'])
        self.begin(self.a);before=self.snapshot();obj=self.e._physical_objects['flute']
        for frequency in ('장면','임의',{'kind':'one_time','uses':1}):
            with self.assertRaises(ValueError):FREQ.physical_activation_allowed(self.e,obj,'item/마법피리-1',frequency)
            with self.assertRaises(ValueError):FREQ.consume_physical_activation(self.e,obj,'item/마법피리-1',frequency)
            self.assertEqual(self.snapshot(),before)


if __name__=='__main__':unittest.main()
