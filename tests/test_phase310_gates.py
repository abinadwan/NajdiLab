import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from app import dataset_platform as platform
from app import training_control
from app.training_control import freeze_readiness_gate, quality_gate

class Phase310GateTests(unittest.TestCase):
    def test_current_v009_gate_semantics_and_66_masks(self):
        freeze=freeze_readiness_gate('gold-v009-remediation-draft'); training=quality_gate('gold-v009-remediation-draft')
        self.assertNotIn('DATASET_NOT_FROZEN',{x['code'] for x in freeze['blocking_issues']})
        self.assertNotIn('DATASET_NOT_FROZEN',{x['code'] for x in training['blocking_issues']})
        self.assertEqual(freeze['checks']['loss_mask_total'],66)
        self.assertEqual(freeze['dataset_counts']['training'],66)
        self.assertEqual(freeze['dataset_counts']['direct_language'],12)
        self.assertEqual(freeze['dataset_counts']['preference_pairs'],10)
        loss=json.loads((platform.DATASETS_ROOT/'gold-v009-remediation-draft'/'loss-mask-validation.json').read_text(encoding='utf-8'))
        self.assertEqual(loss['by_format'],{'sft':{'passed':24,'total':24},'multi_turn':{'passed':34,'total':34},'native_tool_use':{'passed':8,'total':8}})

    def test_freeze_readiness_removes_only_draft_state_blocker(self):
        sample={'status':'BLOCKED','blocking_issues':[{'code':'DATASET_NOT_FROZEN','message':'draft'}],'warnings':[],'checks':{}}
        with patch.object(training_control,'quality_gate',return_value=sample):
            result=training_control.freeze_readiness_gate('draft')
        self.assertEqual(result['status'],'PASS'); self.assertEqual(result['blocking_issues'],[])

    def test_stale_diagnostic_fingerprint_is_rejected(self):
        directory=platform.DATASETS_ROOT/'gold-v009-remediation-draft'; manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
        stale=json.loads(json.dumps(manifest)); stale['diagnostics']['training_fingerprint']='0'*64
        valid,error=platform._diagnostics_status(directory,stale)
        self.assertFalse(valid); self.assertIn('source does not match',error)

if __name__=='__main__': unittest.main()
