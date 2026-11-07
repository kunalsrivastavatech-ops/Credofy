import os
import sys
import unittest
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, 'src'))
sys.path.append(os.path.join(BASE_DIR, 'backend'))

from xai_engine import KredoExplainabilityEngine
from fairness_audit import KredoFairnessAuditor
import server

class TestKredoBackendSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xai = KredoExplainabilityEngine()
        cls.fairness = KredoFairnessAuditor()

    def test_01_model_artifacts_exist(self):
        """Verify all serialized model & pipeline files exist."""
        models_dir = os.path.join(BASE_DIR, 'models')
        self.assertTrue(os.path.exists(os.path.join(models_dir, 'kredo_model.pkl')))
        self.assertTrue(os.path.exists(os.path.join(models_dir, 'preprocessor.pkl')))
        self.assertTrue(os.path.exists(os.path.join(models_dir, 'explainer.pkl')))
        self.assertTrue(os.path.exists(os.path.join(models_dir, 'accuracy_report.json')))

    def test_02_accuracy_report_benchmarks(self):
        """Verify model accuracy report satisfies hackathon criteria (>80%)."""
        with open(os.path.join(BASE_DIR, 'models', 'accuracy_report.json')) as f:
            rep = json.load(f)
        cv_acc = rep['cv_5fold_metrics']['mean_accuracy']
        cv_auc = rep['cv_5fold_metrics']['mean_roc_auc']
        self.assertGreaterEqual(cv_acc, 0.85, "Cross-validation accuracy must be >= 85%")
        self.assertGreaterEqual(cv_auc, 0.90, "Cross-validation ROC-AUC must be >= 0.90")

    def test_03_rural_woman_shg_approval(self):
        """Test Sunita (Rural Woman SHG) receives fair evaluation."""
        applicant = {
            'Gender': 'Female',
            'Married': 'Yes',
            'Dependents': '2',
            'Education': 'Not Graduate',
            'Self_Employed': 'Yes',
            'ApplicantIncome': 24000,
            'CoapplicantIncome': 18000,
            'LoanAmount': 2.5,
            'Loan_Amount_Term': 60,
            'CIBIL_Score': 740,
            'Credit_History': 1,
            'Property_Area': 'Rural'
        }
        res = self.xai.predict_and_explain(applicant)
        self.assertTrue(res['is_approved'])
        self.assertGreaterEqual(res['approval_probability'], 80.0)
        self.assertIn("positive_factors", res['explanations_en'])
        self.assertIn("positive_factors", res['explanations_hi'])

    def test_04_bilingual_explanation_content(self):
        """Verify SHAP attributions translate into non-empty English & Hindi text."""
        applicant = {
            'Gender': 'Male',
            'Married': 'No',
            'Dependents': '0',
            'Education': 'Graduate',
            'Self_Employed': 'No',
            'ApplicantIncome': 30000,
            'CoapplicantIncome': 0,
            'LoanAmount': 8.0,
            'Loan_Amount_Term': 24,
            'CIBIL_Score': 610,
            'Credit_History': 0,
            'Property_Area': 'Semiurban'
        }
        res = self.xai.predict_and_explain(applicant)
        self.assertFalse(res['is_approved'])
        self.assertGreater(len(res['explanations_en']['negative_factors']), 0)
        self.assertGreater(len(res['explanations_hi']['negative_factors']), 0)
        self.assertGreater(len(res['counterfactuals_en']), 0)
        self.assertGreater(len(res['counterfactuals_hi']), 0)

    def test_05_rbi_fairness_four_fifths_compliance(self):
        """Verify Disparate Impact Ratio >= 0.80 for Geographic & Gender parity."""
        f_rep = self.fairness.compute_fairness_report()
        geo_dir = f_rep['geographic_fairness']['disparate_impact_ratio']
        gender_dir = f_rep['gender_fairness']['disparate_impact_ratio']
        self.assertGreaterEqual(geo_dir, 0.80, "Geographic DIR must satisfy 4/5ths rule")
        self.assertGreaterEqual(gender_dir, 0.80, "Gender DIR must satisfy 4/5ths rule")

    def test_06_mongodb_persistence(self):
        """Verify MongoDB collection stores and retrieves underwriting records."""
        count_before = server.applications_col.count_documents({})
        req = server.ApplicantRequest(
            applicant_name="Test Borrower",
            ApplicantIncome=50000,
            LoanAmount=4.0,
            CIBIL_Score=760
        )
        res = server.underwrite_loan(req)
        count_after = server.applications_col.count_documents({})
        self.assertEqual(count_after, count_before + 1)
        self.assertTrue(res['persisted_in_mongodb'])

if __name__ == '__main__':
    unittest.main()
