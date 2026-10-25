"""Whole CSV9 activation and undo contract, preserving the Ch11 observer."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
from native_scenario_fixture import assert_rejections_unchanged
import trainer_feature_acquisition as A
import type_sync as S
import state_grants as G
import state_fields as F
import move_state as M
import downtime as D
import world_entities as W


class TypeSyncFeatureTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='all')

 def setUp(self):
  self.e=Engine(self.r,1909)
  self.a=self.trainer()
  self.water=self.pokemon('꼬부기')
  self.p=self.pokemon()
  A.acquire_static(self.e,self.a,'class/타입-에이스',acquisition_request_id='water-ace',branch='물')

 def trainer(self,*,rank=4,virtuoso=False,name='Type Sync provider'):
  edges=['edge/원소-교감'];choices={'edge/원소-교감':'물'}
  if virtuoso:edges.append('edge/거장');choices['edge/거장']=['의학']
  spec=build_trainer(self.r,name,30,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),
       skills={'의학':rank,'오컬트학':2,'기술학':2,'육상':6},
       extra={'edges':edges,'edge_choices':choices,'type_link_skills':{'물':'육상'},'feats':[],'classes':[]})
  actor=Combatant(self.r,spec);self.e.gm.add_combatant(actor);return actor

 def pokemon(self,species='이상해씨',owner=None):
  actor=Combatant(self.r,build_pokemon(self.r,species,10,moves=['move/몸통박치기'],
       extra={'trainer_id':(owner or self.a).entity_id,'tutor_points':8}))
  self.e.gm.add_combatant(actor);return actor

 def acquire(self,edition='local_csv'):
  return A.acquire_static(self.e,self.a,S.FEATURE,acquisition_request_id='sync-acquisition',
                          selection={'edition':edition,'type':'물'})

 def options(self,p=None,**kw):
  p=p or self.p
  result={'application_id':'water-sync','chosen_type':'물','mode':'replace','replace_type':'풀',
          'capabilities':list(dict.fromkeys(p.spec.get('capabilities',[])+['아가미'])),
          'abilities':list(p.spec.get('abilities',[])),
          'level_up':[{'level':1,'move_id':'move/몸통박치기'},{'level':11,'move_id':'move/물대포'}],
          'learning':{'exceptions':{}},'decisions':dict.fromkeys(S.DECISIONS,'GM reviewed individual anatomy, abilities and learning'),
          'reason':'GM-established completed Type Sync procedure'}
  result.update(kw);return result

 def apply(self,p=None,**kw):
  return self.e.apply_type_sync(self.a,target=p or self.p,seconds=60,**self.options(p,**kw))

 def remove(self,**kw):
  options={'target':self.p,'application_id':'water-sync','removal_id':'undo-water','seconds':30,
           'reason':'completed removal of the sourced Type Sync adaptation'}
  options.update(kw);return self.e.remove_type_sync(self.a,**options)

 def valid(self):
  state=self.e.validate_state();self.assertTrue(state['valid'],state['issues'])

 def test_acquisition_requires_actual_matching_class_edge_and_adept_skill(self):
  wrong=self.trainer(name='unqualified second trainer')
  assert_rejections_unchanged(self.e,[
   lambda:A.acquire_static(self.e,wrong,S.FEATURE,acquisition_request_id='bad',selection={'edition':'local_csv','type':'물'}),
   lambda:A.acquire_static(self.e,self.a,S.FEATURE,acquisition_request_id='bad2',selection={'edition':'local_csv','type':'전기'}),
   lambda:A.acquire_static(self.e,self.a,S.FEATURE,acquisition_request_id='bad3',selection={'edition':'official_playtest','type':'물'})],
   reason_pattern=['Class','Elemental|Class','edition'])
  self.acquire();self.valid()

 def test_exact_csv_and_supplement_sources_and_effective_rank_quotas(self):
  self.assertEqual(S.feature_source(self.r,'local_csv')['clause_id'],S.CSV)
  for rank,expected in ((4,1),(5,2),(6,3)):
   F.base_patch(self.a,{'skills':dict(self.a.spec['skills'],의학=rank)},reason='observed actual skill advancement')
   self.assertEqual(S.quota(self.r,self.a,'local_csv'),expected)
   self.assertEqual(S.quota(self.r,self.a,'supplement'),min(rank-2,4))
  virtuoso=self.trainer(rank=6,virtuoso=True,name='actual Virtuoso')
  self.assertEqual(S.quota(self.r,virtuoso,'local_csv'),5)
  self.assertEqual(S.quota(self.r,virtuoso,'supplement'),4)

 def test_highest_skill_quota_consumption_and_once_ever_target(self):
  self.acquire();self.apply()
  q=self.pokemon()
  assert_rejections_unchanged(self.e,[lambda:self.apply(q,application_id='second'),lambda:self.apply(application_id='repeat')],
                             reason_pattern=['quota','only once'])
  F.base_patch(self.a,{'skills':dict(self.a.spec['skills'],기술학=5)},reason='actual Expert Technology')
  self.apply(q,application_id='second');self.remove()
  self.assertEqual(sum(row['refunded_by'] is None for row in self.a.spec[S.USES].values()),1)
  assert_rejections_unchanged(self.e,[lambda:self.apply(application_id='again'),lambda:self.remove()],reason_pattern=['only once','replayed'])
  self.apply(self.pokemon(),application_id='third');self.valid()

 def test_conversion_paths_use_actual_permanent_types(self):
  self.acquire()
  for i,(before,mode,old,after) in enumerate(((['풀'],'add',None,['풀','물']),(['풀'],'replace','풀',['물']),
         (['풀','독'],'replace','풀',['물','독']),(['풀','물'],'retain_chosen',None,['물']))):
   p=self.pokemon();self.e.gm.set_types(p,before,reason='actual original individual types')
   self.apply(p,application_id='conversion-'+str(i),mode=mode,replace_type=old)
   self.assertEqual(p.spec['types'],after)
   self.remove(target=p,application_id='conversion-'+str(i),removal_id='undo-'+str(i))
   self.assertEqual(p.spec['types'],before)

 def test_bad_adaptation_action_and_foreign_target_are_atomic(self):
  self.acquire();foreign=self.pokemon(owner=self.trainer(name='other owner'))
  bad=self.options();bad['decisions'].pop('learning')
  assert_rejections_unchanged(self.e,[
   lambda:self.apply(mode='add',replace_type=None),
   lambda:self.apply(chosen_type='전기'),
   lambda:self.e.apply_type_sync(self.a,target=self.p,seconds=60,**bad),
   lambda:self.apply(abilities=['nonexistent ability']),
   lambda:self.apply(foreign)],
   reason_pattern=['monotype','Elemental','four GM','ability|Ability|unknown|Unknown','different trainer'])
  self.apply();self.valid()

 def test_removal_preserves_unrelated_changes_temporary_sources_and_learned_moves(self):
  self.acquire();before=list(self.p.spec['capabilities']);self.apply()
  D.gain_exp_combatant(self.e,self.p,'to next level')
  self.assertIn('move/물대포',self.p.moves)
  G.grant(self.p,'capabilities','텔레파시','unrelated/telepathy','fixture')
  G.type_operation(self.p,'add',['고스트'],'unrelated/ghost')
  F.base_patch(self.p,{'capabilities':self.p.spec['capabilities']+['불쏘시개']},reason='unrelated permanent capability observation')
  self.remove()
  self.assertEqual(self.p.spec['types'],['풀','독']);self.assertIn('고스트',self.p.types)
  self.assertEqual(self.p.spec['capabilities'],before+['불쏘시개'])
  self.assertIn('텔레파시',G.effective_capabilities(self.p));self.assertIn('move/물대포',self.p.moves)
  self.assertIn('move/물대포',M.natural_moves(self.r,self.p.spec));self.assertIsNone(S.active(self.r,self.p.spec))
  self.assertIsNone(S.learning_permission(self.r,self.p.spec,'move/열탕','tm'));self.valid()

 def test_later_gm_adaptation_is_preserved_and_old_prefix_still_proves_learning(self):
  self.acquire();self.apply()
  self.e.gm.observe_type_sync(self.p,**self.options(application_id='later-fire',chosen_type='불꽃',replace_type='독',
       level_up=[{'level':12,'move_id':'move/불꽃세례'}]))
  self.remove()
  self.assertEqual(self.p.spec['types'],['풀','불꽃'])
  self.assertEqual(S.active(self.r,self.p.spec)['id'],'later-fire')
  prefix=deepcopy(self.p.spec);prefix[S.KEY]['history']=prefix[S.KEY]['history'][:1];prefix['types']=['물','독']
  self.assertTrue(S.learning_permission(self.r,prefix,'move/열탕','tm'))
  self.assertTrue(S.historical_evidence(self.r,self.p.spec,'water-sync','move/물대포',11))
  self.assertIsNone(S.learning_permission(self.r,self.p.spec,'move/열탕','tm'));self.valid()

 def test_supplement_quota_and_no_csv_undo(self):
  self.acquire('supplement');self.apply();self.apply(self.pokemon(),application_id='second')
  third=self.pokemon()
  assert_rejections_unchanged(self.e,[lambda:self.apply(third,application_id='third'),lambda:self.remove()],
                             reason_pattern=['quota','supplement'])

 def test_durable_restore_snapshot_and_off_field_historical_participants(self):
  self.acquire();self.apply();self.e.gm.snapshot('synced')
  self.e.gm.remove_combatant(self.p,reason='departed scene');self.e.gm.remove_combatant(self.a,reason='departed scene')
  self.assertIn(self.a.entity_id,W.actor_index(self.e));self.assertIn(self.p.entity_id,W.actor_index(self.e));self.valid()
  self.e.gm.restore('synced')
  ids=self.a.entity_id,self.p.entity_id
  self.e=Engine.import_state(self.r,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  actors=W.actor_index(self.e);self.a,self.p=(actors[uid] for uid in ids)
  self.remove();self.assertEqual(self.e.elapsed_seconds,90);self.valid()

 def test_provider_charge_or_source_tampering_is_rejected(self):
  self.acquire();self.apply();original=deepcopy(self.a.spec[S.USES])
  self.a.spec[S.USES]['water-sync']['refunded_by']='invented'
  with self.assertRaises(ValueError):S.validate(self.e)
  self.a.spec[S.USES]=original
  self.p.spec[S.KEY]['history'][0]['feature']['provider_id']='not-the-provider'
  with self.assertRaises(ValueError):S.validate(self.e)

 def test_all_printed_type_linked_classes_use_existing_owned_identity_reader(self):
  from types import SimpleNamespace
  # This is an ownership-query contract check, not acquisition of all 16 classes.
  for uid,unit in self.r.selection.units.items():
   if not uid.startswith('supp-fantasy/') or '-원소술사-' not in uid or uid.count('/')!=1:continue
   chosen=uid.split('/')[1].split('-원소술사-')[0]
   if chosen=='불':chosen='불꽃'
   proxy=SimpleNamespace(r=self.r,kind='trainer',entity_id='owned-query',spec={'classes':[],'feats':[uid]})
   self.assertEqual(S._linked_classes(self.e,proxy,chosen),[uid])
   self.assertEqual(S._linked_classes(self.e,proxy,'에스퍼'),[])
  for uid,chosen in (('class/파동술사','격투'),('class/염동력자','에스퍼'),
                     ('class/텔레파시능력자','에스퍼'),('class/공간도약자','에스퍼')):
   proxy=SimpleNamespace(r=self.r,kind='trainer',entity_id='owned-query',spec={'classes':[uid],'feats':[]})
   self.assertEqual(len(S._linked_classes(self.e,proxy,chosen)),1)
   self.assertEqual(S._linked_classes(self.e,proxy,'물'),[])

 def test_actual_csv_swarmlord_projection_qualifies_and_no_class_is_invented(self):
  spec=build_trainer(self.r,'actual Swarm Lord',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),
       skills={'의학':4,'생존':3,'명령':3},extra={'edges':['edge/원소-교감'],
       'edge_choices':{'edge/원소-교감':'벌레'},'feats':['무리군주'],
       'static_feature_choices':{'무리군주':'거미의 포용'}})
  actor=Combatant(self.r,spec)
  # Native FantasyClassBranchTests registers existing ownership before the GM
  # boundary checks its projected grants; a stale projection is not admissible.
  for roster in (self.e.everyone,self.e.gm.everyone):
   if actor not in roster:roster.append(actor)
  __import__('items').register_feats(self.e,actor)
  result=A.acquire_static(self.e,actor,S.FEATURE,acquisition_request_id='swarm-sync',selection={'edition':'local_csv','type':'벌레'})
  self.assertEqual(result['snapshot']['linked_classes'],['supp-fantasy/벌레-원소술사-무리군주'])
  self.valid()

 def test_transfer_and_storage_preserve_original_charge_and_refund_recipient(self):
  import pokemon_party as PARTY
  self.acquire();self.apply();other=self.trainer(name='new owner')
  PARTY.configure(self.e,self.a,mode='unlimited',reason='actual source roster',roster=[self.water,self.p])
  PARTY.configure(self.e,other,mode='custom',limit=0,storage={'kind':'center','id':'actual-center'},
                  reason='actual recipient storage',roster=[])
  PARTY.transfer(self.e,self.a,target=self.p,new_owner=other,reason='actual Pokemon transfer',request_id='transfer-synced')
  self.assertEqual(self.p.spec['trainer_id'],other.entity_id);self.assertEqual(self.p.spec['party_location']['location'],'storage')
  self.assertEqual(self.p.spec['types'],['물','독']);self.assertIsNone(self.a.spec[S.USES]['water-sync']['refunded_by'])
  self.remove();self.assertEqual(self.a.spec[S.USES]['water-sync']['refunded_by'],'undo-water')
  self.assertNotIn(S.USES,other.spec);self.valid()

 def test_completed_extended_job_cannot_be_replaced_by_another_activity(self):
  self.acquire();self.apply();saved=deepcopy(self.p.spec[S.KEY]['history'][0]['feature'])
  self.p.spec[S.KEY]['history'][0]['feature']['seconds']+=1
  with self.assertRaisesRegex(ValueError,'completed Extended'):S.validate(self.e)
  self.p.spec[S.KEY]['history'][0]['feature']=saved
  self.remove();self.p.spec[S.KEY]['history'][-1]['job_id']=saved['job_id']
  with self.assertRaisesRegex(ValueError,'completed Extended'):S.validate(self.e)


if __name__=='__main__':unittest.main()
