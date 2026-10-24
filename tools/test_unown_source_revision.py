"""C10-068/069: real permanent joins, complete source choices and native move slots."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Combatant
from builder import build_pokemon
import test_core_prime_unown as FIXTURE
from native_scenario_fixture import assert_rejected_unchanged
import special_entities as S
import state_grants as G
import move_state as MOVES
import growth_stats as GROWTH
import world_entities as WORLD
import state_codec as CODEC
import turn as TURN


from engine import Engine

class UnownSourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    fixture=FIXTURE.CorePrimeUnownTests.fixture
    observe=FIXTURE.CorePrimeUnownTests.observe
    begin=FIXTURE.CorePrimeUnownTests.begin
    valid=FIXTURE.CorePrimeUnownTests.valid

    def setUp(self):
        old=self.r.rulings;self.r.rulings=deepcopy(old)
        self.addCleanup(setattr,self.r,'rulings',old)

    def source_row(self,row,variant='english_optional_normal_limit'):
        row=deepcopy(row);pending=S.prime_source_choices(self.r)
        row['hidden_power_source_choice']={'value':variant,'reason':'actual reviewed complete Letter Press source',
                                          'scope':pending['decision_scope']}
        if variant=='english_optional_normal_limit':
            for part in row['joined']:
                part['hidden_powers']=[{'move_id':part['hidden_power_id'],
                    'type':part.get('hidden_power_type',self.r.move(part['hidden_power_id'])['type']),
                    'damage_class':part['damage_class']}]
                for key in ('hidden_power_id','hidden_power_type','damage_class'):part.pop(key,None)
        return row

    def add_member(self,e,*,kind='물',number=5):
        mid='move/잠재파워-'+kind
        member=Combatant(self.r,build_pokemon(self.r,'안농',20,name='actual additional Unown '+str(number),
            moves=[mid],wild=True,pos=(2+number,3)))
        member.side='party';member.on_field=False;e.everyone.append(member)
        return member,{'member_id':member.entity_id,'boosted_stat':None,'hidden_power_id':mid,'damage_class':'special'}

    def originals(self,h,*,count=6):
        moves=['move/잠재파워-불꽃','move/몸통박치기','move/전광석화','move/할퀴기','move/물대포','move/울음소리'][:count]
        G.set_baseline(h,'moves',moves);return moves

    def member_two_powers(self,member):
        G.set_baseline(member,'moves',['move/잠재파워-불꽃','move/잠재파워-물'])
        return [{'move_id':'move/잠재파워-불꽃','type':'불꽃','damage_class':'physical'},
                {'move_id':'move/잠재파워-물','type':'물','damage_class':'special'}]

    def restore(self,e,host):
        loaded=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(e),ensure_ascii=False)))
        self.valid(loaded);return loaded,WORLD.actor_index(loaded)[host.entity_id]

    def test_fifth_and_sixth_joins_keep_four_bonuses_and_real_member_move_sources(self):
        e,a,h,m,t,row=self.fixture();self.observe(e,row)
        stats=deepcopy(h.stats);investment=deepcopy(GROWTH.source_permanent(h)['investment'])
        migrations=len(h.spec['allocation_migrations']);hp=h.hp;originals=list(h.moves)
        for number,kind in ((5,'물'),(6,'풀')):
            member,part=self.add_member(e,kind=kind,number=number)
            prior=deepcopy(member.spec);uses=deepcopy(member.move_uses)
            row['joined'].append(part);out=self.observe(e,row)
            self.assertEqual(len(out['entity']['joined']),number)
            self.assertEqual(sum(out['state_view']['base_stat_bonuses'].values()),20)
            self.assertEqual(h.stats,stats);self.assertEqual(h.hp,hp)
            self.assertEqual(GROWTH.source_permanent(h)['investment'],investment)
            self.assertEqual(len(h.spec['allocation_migrations']),migrations)
            self.assertEqual(member.spec,{**prior,S.PRIME_MEMBER:{'record_id':row['id'],'host_id':h.entity_id}})
            self.assertEqual(member.move_uses,uses)
            with self.assertRaisesRegex(ValueError,'Prime Unown'):TURN.can_act(e,member)
        self.assertTrue(set(originals)<=set(h.moves))
        newest=S.prime_moves(self.r,h.spec[S.PRIME_KEY])[-1]
        self.assertEqual(self.r.move(newest)['type'],'풀');self.assertEqual(self.r.move(newest)['class'],'특수')
        self.begin(e,h);before=t.hp
        e.use_move(h,t,newest,situational=100,set_damage=True)
        self.assertLess(t.hp,before);self.assertEqual(h.move_uses[newest],1)
        self.restore(e,h);self.valid(e)

    def test_english_full_original_list_can_retain_none_without_forcing_member_powers(self):
        e,a,h,m,t,row=self.fixture(1);originals=self.originals(h)
        self.member_two_powers(m[0]);row=self.source_row(row);row['joined'][0]['hidden_powers']=[]
        member=deepcopy(m[0].spec);self.observe(e,row)
        self.assertEqual(h.moves,originals);self.assertEqual(S.prime_moves(self.r,h.spec[S.PRIME_KEY]),[])
        self.assertEqual(MOVES.describe(self.r,h.spec,moves=h.moves)['slot_count'],6)
        self.assertEqual(m[0].spec,{**member,S.PRIME_MEMBER:{'record_id':row['id'],'host_id':h.entity_id}})
        forged=S.prime_instance_id(row,row['joined'][0],{'move_id':'move/잠재파워-물','type':'물','damage_class':'special'})
        assert_rejected_unchanged(e,lambda:e.use_move(h,t,forged),reason_pattern='owned|ownership|known')
        e.gm.snapshot('optional-none');e.gm.set_hp(h,h.hp-1,reason='actual later damage')
        e.gm.restore('optional-none',reason='actual optional retention restore')
        self.assertEqual(h.moves,originals);self.restore(e,h)

    def test_english_subset_occupies_a_normal_slot_and_drives_the_native_move(self):
        e,a,h,m,t,row=self.fixture(1);originals=self.originals(h,count=5)
        powers=self.member_two_powers(m[0]);row=self.source_row(row);row['joined'][0]['hidden_powers']=powers[1:]
        prior=deepcopy(m[0].spec);self.observe(e,row)
        self.assertEqual(m[0].spec,{**prior,S.PRIME_MEMBER:{'record_id':row['id'],'host_id':h.entity_id}})
        ids=S.prime_moves(self.r,h.spec[S.PRIME_KEY]);self.assertEqual(len(ids),1)
        self.assertEqual(MOVES.describe(self.r,h.spec,moves=h.moves)['slot_count'],6)
        self.assertEqual(set(h.moves),set(originals+[ids[0]]))
        self.assertEqual((self.r.move(ids[0])['type'],self.r.move(ids[0])['class']),('물','특수'))
        self.begin(e,h);before=t.hp;member_before_attack=deepcopy(m[0].spec)
        with patch.object(Engine,'d20',return_value=18), patch.object(Engine,'roll_damage',autospec=True,side_effect=Engine.roll_damage) as damage:
            e.use_move(h,t,ids[0],situational=100,set_damage=True)
        self.assertLess(t.hp,before);self.assertEqual(h.budget['standard'],0)
        self.assertEqual(damage.call_args.args[3]['id'],ids[0]);self.assertEqual(h.move_uses[ids[0]],1)
        self.assertEqual(m[0].spec,member_before_attack)
        self.restore(e,h);self.valid(e)

    def test_english_overcapacity_rolls_back_the_whole_join_after_a_possible_first_grant(self):
        e,a,h,m,t,row=self.fixture(1);self.originals(h,count=5)
        powers=self.member_two_powers(m[0]);row=self.source_row(row);row['joined'][0]['hidden_powers']=powers
        assert_rejected_unchanged(e,lambda:self.observe(e,row),reason_pattern='capacity')
        self.assertNotIn(S.PRIME_KEY,h.spec);self.assertNotIn(S.PRIME_MEMBER,m[0].spec)
        row['joined'][0]['hidden_powers']=powers[:1];self.observe(e,row)
        self.assertEqual(MOVES.describe(self.r,h.spec,moves=h.moves)['slot_count'],6)
        self.restore(e,h);self.valid(e)

    def test_explicit_korean_requires_all_additional_powers_and_preserves_its_exemption(self):
        e,a,h,m,t,row=self.fixture(1);originals=self.originals(h);powers=self.member_two_powers(m[0])
        row=self.source_row(row,'korean_all_additional');row['joined'][0]['hidden_powers']=powers[:1]
        assert_rejected_unchanged(e,lambda:self.observe(e,row),reason_pattern='all prior')
        row['joined'][0]['hidden_powers']=powers;self.observe(e,row)
        self.assertEqual(len(h.moves),8);self.assertTrue(set(originals)<=set(h.moves))
        self.assertEqual(MOVES.describe(self.r,h.spec,moves=h.moves)['slot_count'],6)
        changed=deepcopy(row);changed['hidden_power_source_choice']=self.source_row(row)['hidden_power_source_choice']
        assert_rejected_unchanged(e,lambda:self.observe(e,changed),reason_pattern='permanent')
        self.restore(e,h);self.valid(e)

    def test_english_skipped_powers_and_retained_class_choices_are_permanent_when_appending(self):
        e,a,h,m,t,row=self.fixture(1);row=self.source_row(row);row['joined'][0]['hidden_powers']=[]
        self.observe(e,row);member,part=self.add_member(e,number=2)
        part={'member_id':member.entity_id,'boosted_stat':'atk','hidden_powers':[
            {'move_id':part['hidden_power_id'],'type':'물','damage_class':'physical'}]}
        row['joined'].append(part);self.observe(e,row)
        for change in ('skipped','class','split'):
            proposed=deepcopy(row)
            if change=='skipped':proposed['joined'][0]['hidden_powers']=[{'move_id':'move/잠재파워-불꽃','type':'불꽃','damage_class':'special'}]
            elif change=='class':proposed['joined'][1]['hidden_powers'][0]['damage_class']='special'
            else:proposed['joined']=proposed['joined'][:1]
            assert_rejected_unchanged(e,lambda:self.observe(e,proposed),reason_pattern='permanent')
        self.restore(e,h);self.valid(e)

    def test_english_native_grant_loss_is_not_silently_restored_by_observation_or_later_join(self):
        e,a,h,m,t,row=self.fixture(1);row=self.source_row(row);self.observe(e,row)
        mid=S.prime_moves(self.r,h.spec[S.PRIME_KEY])[0];e.gm.snapshot('retained-power')
        def forget(se,actor):
            G.revoke(actor,S.PRIME_PREFIX+mid,engine=se)
            return S.validate_prime_world(se)
        G.transition(e,h,forget)
        self.assertNotIn(mid,h.moves);self.assertIn(mid,S.prime_moves(self.r,h.spec[S.PRIME_KEY]))
        self.observe(e,row);self.assertNotIn(mid,h.moves)
        member,part=self.add_member(e,number=2)
        row['joined'].append({'member_id':member.entity_id,'boosted_stat':'atk','hidden_powers':[]})
        self.observe(e,row);self.assertNotIn(mid,h.moves)
        loaded,actual=self.restore(e,h);self.assertNotIn(mid,actual.moves)
        self.assertEqual(S.prime_moves(self.r,actual.spec[S.PRIME_KEY]),[mid])
        assert_rejected_unchanged(loaded,lambda:loaded.use_move(actual,WORLD.actor_index(loaded)[t.entity_id],mid),reason_pattern='owned|ownership|known')
        e.gm.restore('retained-power',reason='actual same pre-loss source snapshot')
        self.assertIn(mid,h.moves);self.assertEqual(len(h.spec[S.PRIME_KEY]['joined']),1)
        self.restore(e,h);self.valid(e)

    def test_ordinary_non_unown_move_capacity_remains_six_and_seventh_is_atomic(self):
        e,a,h,m,t,row=self.fixture(1)
        originals=['move/몸통박치기','move/전광석화','move/할퀴기','move/물대포','move/울음소리','move/꼬리흔들기']
        actor=Combatant(self.r,build_pokemon(self.r,'피카츄',20,name='actual ordinary Pokemon',moves=originals,wild=True))
        actor.on_field=False;e.everyone.append(actor)
        known_before=list(actor.moves)
        self.assertEqual(known_before,originals+['struggle'])
        self.assertEqual(MOVES.describe(self.r,actor.spec,moves=actor.moves)['slot_count'],6)
        assert_rejected_unchanged(e,lambda:e.gm.set_move(actor,'move/전기쇼크',reason='actual seventh known Move'),reason_pattern='capacity')
        self.assertEqual(actor.moves,known_before);self.restore(e,h)

    def test_source_scope_receipt_and_forged_projection_changes_are_rejected(self):
        e,a,h,m,t,row=self.fixture(1);row=self.source_row(row)
        wrong=deepcopy(row);wrong['hidden_power_source_choice']['scope']['definition_hash']='changed'
        assert_rejected_unchanged(e,lambda:self.observe(e,wrong),reason_pattern='scope')
        wrong=deepcopy(row);wrong['hidden_power_source_policy']={'status':'PolicyValuesReady'}
        assert_rejected_unchanged(e,lambda:self.observe(e,wrong),reason_pattern='receipt')
        self.observe(e,row);self.restore(e,h);e.gm.snapshot('reviewed-source')
        e._physical_objects[row['id']]['hidden_power_source_policy']['values']['definitions']['english_optional_normal_limit']['hidden_powers']='all_additional'
        self.assertFalse(e.validate_state()['valid'])
        with self.assertRaises(ValueError):CODEC.dump_engine(e)
        e.gm.restore('reviewed-source',reason='restore the complete reviewed source')
        self.valid(e)


if __name__=='__main__':unittest.main()
