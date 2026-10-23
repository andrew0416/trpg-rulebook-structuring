"""Permanent TP spending and owner-bound refunds in the same actual transfer."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_stat_edge_state as fixtures
from builder import build_trainer
import pokemon_party as PARTY,pokemon_stat_edges as EDGES,state_grants as G
from state_codec import dump_engine,load_engine
import world_entities as W

class TransferRefundTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.StatEdgeStateTests.setUpClass.__func__)
 add=fixtures.StatEdgeStateTests.add
 pokemon=fixtures.StatEdgeStateTests.pokemon
 teach=fixtures.StatEdgeStateTests.teach
 def setUp(self):
  fixtures.StatEdgeStateTests.setUp(self);self.c=self.pokemon()
  self.teach(self.c,'atk') # Actual permanent investment: 5 -> 4 TP.
  self.a.spec['feats']=['feat/래밍-스피드']
  self.e.acquire_grant_group(self.c,'owner/grant',[{'source_id':'owner/run-up','field':'abilities','value':'ability/도움닫기'}],2,
   rule_id='feat/래밍-스피드',reason='actual acquired owner-bound provider',owner_id=self.a.entity_id,lifetime='your_pokemon')
  self.other=self.add(build_trainer(self.r,'receiver',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10)))
  PARTY.configure(self.e,self.a,mode='unlimited',reason='actual owner',roster=[self.c])
  PARTY.configure(self.e,self.other,mode='unlimited',reason='actual receiver',roster=[])
 def transfer(self):return PARTY.transfer(self.e,self.a,target=self.c,new_owner=self.other,reason='actual exchange',request_id='mixed-transfer')
 def test_transfer_refunds_only_owner_payment_preserves_permanent_edge_and_replay(self):
  self.assertEqual(self.c.spec['tutor_points'],2);self.assertIn('도움닫기',self.c.abilities)
  result=self.transfer()
  self.assertEqual(self.c.spec['tutor_points'],4);self.assertNotIn('도움닫기',self.c.abilities)
  self.assertEqual(EDGES.exemptions(self.r,self.c.spec),{'atk'})
  self.assertEqual(self.c.spec['trainer_id'],self.other.entity_id)
  payment=self.c.spec[G.KEY]['payments']['owner/grant']
  self.assertEqual(payment['paid'],2);self.assertEqual(sum(row['amount'] for row in payment['refunds']),2)
  self.assertNotIn('owner/run-up',self.c.spec[G.KEY]['sources'])
  loaded=load_engine(self.r,dump_engine(self.e));actors=W.actor_index(loaded);before=dump_engine(loaded)
  replay=PARTY.transfer(loaded,actors[self.a.entity_id],target=actors[self.c.entity_id],new_owner=actors[self.other.entity_id],reason='actual exchange',request_id='mixed-transfer')
  self.assertEqual(replay,result);self.assertEqual(dump_engine(loaded),before)
  self.assertEqual(EDGES.exemptions(self.r,actors[self.c.entity_id].spec),{'atk'})
 def test_changed_transfer_source_cannot_refund_or_change_owner(self):
  native=Path.read_bytes;before=dump_engine(self.e)
  def changed(path):return native(path)+(b'changed' if path.name=='ch05-pokemon.md' else b'')
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaisesRegex(ValueError,'changed'):self.transfer()
  self.assertEqual(dump_engine(self.e),before)

if __name__=='__main__':unittest.main()
