"""Q42/C09-087: complete source choices on actual native burn/Focus receipts."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from builder import build_pokemon
from engine import Combatant,Rules
import cleanse_tag_burn as B
import cleanse_tags as TAG
import invisibility_state as INVISIBILITY
import native_scenario_fixture as NATIVE
import skill_feature_actions as SKILLS
import state_codec as CODEC
import state_grants as G
import world_entities as WORLD
import test_category2_cleanse_burn as FIXTURE


class CleanseBurnSourceRevisionTests(unittest.TestCase):
    actor=FIXTURE.BurnTests.actor
    craft=FIXTURE.BurnTests.craft
    place=FIXTURE.BurnTests.place

    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

    def setUp(self):
        FIXTURE.BurnTests.setUp(self)
        self.p.spec['capabilities']=[];self.q.spec['capabilities']=[]
        self.both=self.add('고오스',(3,2))
        self.invisible=self.add('깜까미',(4,2))
        self.phasing=self.add('포트데스',(5,2))
        self.subjects=(self.both,self.invisible,self.phasing)
        for c in self.subjects:c.spec['skills']['집중']=4

    def add(self,species,pos):
        c=Combatant(self.e.r,build_pokemon(self.e.r,species,30,moves=[],abilities=[],wild=True))
        self.e.gm.add_combatant(c,pos=pos,side='foe',reason='actual catalog Cleanse Tag capability holder')
        NATIVE.prepare_body(self.e,c,size=c.spec['size'],offsets=[(0,0)],reason='complete observed actual holder body')
        return c

    def choice(self,variant='english_both_inclusive',engine=None):
        return dict(value=variant,reason='GM explicitly selects this complete printed Cleanse Tag definition',
                    scope=B.source_choices(engine or self.e)['decision_scope'])

    def burn(self,checks,*,choice=None,engine=None,actor=None,tag='tag:one',event='source-burn'):
        return (engine or self.e).gm.observe_cleanse_burn(actor or self.b,tag,event_id=event,
            reason='GM observed this actual original tag burned now',checks=checks,source_choice=choice)

    def checks(self,faces=(2,2,3,3),subjects=None):
        return {c.entity_id:{'fixed':list(faces)} for c in (self.subjects if subjects is None else subjects)}

    def dump(self,e=None):return CODEC.dump_engine(e or self.e)

    def test_authored_korean_default_targets_either_and_uses_strict_native_focus(self):
        for faces,lost in (((2,2,2,2),True),((2,2,3,3),False),((3,3,3,3),False)):
            self.setUp();before={c.entity_id:G.effective_capabilities(c) for c in self.subjects}
            self.assertIn('투명',before[self.invisible.entity_id]);self.assertNotIn('페이징',before[self.invisible.entity_id])
            self.assertIn('페이징',before[self.phasing.entity_id]);self.assertNotIn('투명',before[self.phasing.entity_id])
            row=self.burn(self.checks(faces))
            self.assertEqual((row['policy_variant'],row['source_choice'],row['power']),('korean_either_strict',None,10))
            self.assertEqual(set(row['targets']),{c.entity_id for c in self.subjects})
            for c in self.subjects:
                target=row['targets'][c.entity_id]
                self.assertEqual(target['result'],dict(total=sum(faces),lost=lost))
                event=SKILLS.event(self.e,c,target['skill_options']['roll_id'])
                self.assertEqual((event.state,event.final.total),('final',sum(faces)))
                expected=[v for v in before[c.entity_id] if v not in B.LOST] if lost else before[c.entity_id]
                self.assertEqual(G.effective_capabilities(c),expected)
            self.assertNotIn(self.q.entity_id,row['targets']);self.dump()

    def test_scoped_english_requires_both_and_keeps_inclusive_tie_as_one_definition(self):
        for faces,lost in (((2,2,2,2),True),((2,2,3,3),True),((3,3,3,3),False)):
            self.setUp();choice=self.choice()
            untouched={c.entity_id:G.effective_capabilities(c) for c in (self.invisible,self.phasing)}
            row=self.burn(self.checks(faces,subjects=(self.both,)),choice=choice)
            self.assertEqual((row['policy_variant'],row['source_choice']),('english_both_inclusive',choice))
            self.assertEqual(row['policy'],B.POLICY)
            self.assertEqual(set(row['targets']),{self.both.entity_id})
            self.assertEqual(row['targets'][self.both.entity_id]['result'],dict(total=sum(faces),lost=lost))
            for c in (self.invisible,self.phasing):self.assertEqual(G.effective_capabilities(c),untouched[c.entity_id])
            self.dump()

    def test_wrong_choice_source_and_unregistered_actor_refuse_before_actual_burn(self):
        choice=self.choice();wrong=deepcopy(choice);wrong['scope']['profile_hash']='other-profile'
        invalid=deepcopy(choice);invalid['value']='either_inclusive_mixed'
        unregistered=self.actor('unregistered-expert','trainer');unregistered.spec['skills']['오컬트학']=7
        for options in ({'choice':'english_both_inclusive'},{'choice':wrong},{'choice':invalid},{'actor':unregistered}):
            before=self.dump()
            with self.assertRaises(ValueError):self.burn(self.checks(subjects=(self.both,)),**options)
            self.assertEqual(self.dump(),before)
        before=self.dump();selected=self.rules._selected_rule
        with patch.object(self.rules,'_selected_rule',side_effect=lambda uid,**kw:'other' if uid==TAG.ITEM else selected(uid,**kw)):
            with self.assertRaises(ValueError):self.burn(self.checks(),choice=choice)
        self.assertEqual(self.dump(),before);self.assertNotIn('destroyed',self.e._physical_objects['tag:one'])
        self.assertEqual(self.burn(self.checks())['policy_variant'],'korean_either_strict')

    def test_seven_rank_real_craft_and_burn_keep_policy_loss_and_visibility_through_both_restores(self):
        self.a.spec['skills']['오컬트학']=7;self.b.spec['skills']['오컬트학']=7
        self.craft('seven',skill_options={'fixed':[2]*7});self.place('tag:seven')
        self.e.change_invisibility(self.both,True,reason='actual catalog holder becomes invisible')
        self.e.advance_time(17)
        row=self.burn(self.checks(subjects=(self.both,)),choice=self.choice(),tag='tag:seven',event='rank-seven-burn')
        body=self.e._physical_objects['tag:seven'];self.assertEqual(body[TAG.PROFILE]['rank_at_creation'],7)
        self.assertEqual((row['rank_at_burn'],row['power']),(7,14))
        self.assertEqual(self.both.spec[INVISIBILITY.KEY]['ended_elapsed'],17)
        self.assertFalse(self.e.invisibility_state(self.both)['active'])
        loss=G.capability_losses(self.both)[B._source_id(row,self.both.entity_id)]
        self.assertEqual((loss['duration'],loss['clock_anchor']),(300,row['resolved_at']))
        self.e.gm.snapshot('actual-seven-burn');saved=self.dump()
        expected=deepcopy((body,G.capability_losses(self.both),self.both.spec[INVISIBILITY.KEY],self.e.elapsed_seconds,self.e.rng.getstate()))
        e=CODEC.load_engine(Rules(ROOT,ruleset='core'),json.loads(json.dumps(saved)))
        p=WORLD.actor_index(e)[self.both.entity_id]
        self.assertEqual(e._physical_objects['tag:seven'],body)
        self.assertEqual(G.capability_losses(p),G.capability_losses(self.both))
        e.advance_time(299);self.assertNotIn('투명',G.effective_capabilities(p))
        e.advance_time(1);self.assertIn('투명',G.effective_capabilities(p));self.assertIn('페이징',G.effective_capabilities(p))
        self.assertFalse(e.invisibility_state(p)['active']);self.dump(e)
        self.e.advance_time(300);self.e.gm.restore('actual-seven-burn')
        self.assertEqual((self.e._physical_objects['tag:seven'],G.capability_losses(self.both),
            self.both.spec[INVISIBILITY.KEY],self.e.elapsed_seconds,self.e.rng.getstate()),expected)
        self.assertEqual(self.e._physical_objects['tag:seven'][B.KEY]['source_choice'],row['source_choice'])
        self.dump()

    def test_pending_focus_restores_and_resumes_only_original_policy_at_actual_resolution_time(self):
        q=self.actor('z-focus-target','trainer');q.pos=(4,1)
        q.spec.update(size='Medium',movement={'land':6},capabilities=['Phasing'],feats=[SKILLS.MONKEY])
        q.spec['skills'].update({'집중':4,'전투':4,'육상':4})
        self.e.everyone.append(q)
        checks=self.checks();checks[q.entity_id]=dict(fixed=[2]*4,feature=SKILLS.MONKEY,
            feature_options={'decision':lambda first:None})
        with self.assertRaisesRegex(ValueError,'boolean'):self.burn(checks)
        original=deepcopy(self.e._physical_objects['tag:one'][B.KEY])
        self.assertEqual((original['status'],original['policy_variant'],original['source_choice']),('pending','korean_either_strict',None))
        first=SKILLS.event(self.e,self.both,original['targets'][self.both.entity_id]['skill_options']['roll_id'])
        e=CODEC.load_engine(Rules(ROOT,ruleset='core'),json.loads(json.dumps(self.dump())))
        index=WORLD.actor_index(e);e.advance_time(17);rng=e.rng.getstate()
        checks[q.entity_id]['feature_options']={'decision':lambda first:False}
        with self.assertRaisesRegex(ValueError,'producing'):self.burn(checks,engine=e,actor=index[self.b.entity_id],choice=self.choice(engine=e))
        self.assertEqual(e.rng.getstate(),rng)
        self.assertEqual(e._physical_objects['tag:one'][B.KEY],original)
        row=self.burn(checks,engine=e,actor=index[self.b.entity_id])
        self.assertEqual((row['status'],row['policy_variant'],row['source_choice']),('complete','korean_either_strict',None))
        self.assertEqual(row['resolved_at'],original['burned_at']+17)
        self.assertEqual(e.rng.getstate(),rng)
        again=SKILLS.event(e,index[self.both.entity_id],row['targets'][self.both.entity_id]['skill_options']['roll_id'])
        self.assertEqual((again.first,again.final),(first.first,first.final))
        self.assertFalse(row['targets'][self.both.entity_id]['result']['lost'])
        loss=G.capability_losses(index[q.entity_id])[B._source_id(row,q.entity_id)]
        self.assertEqual(loss['clock_anchor'],row['resolved_at']);self.dump(e)


if __name__=='__main__':unittest.main()
