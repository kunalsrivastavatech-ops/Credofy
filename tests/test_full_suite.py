import os
import sys
import json
import io
import unittest
import urllib.request
import urllib.error

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, 'src'))
sys.path.append(os.path.join(BASE_DIR, 'backend'))

API_BASE = "http://localhost:8000"

class EquiBharatFullTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("\n=======================================================")
        print("🧪 RUNNING COMPREHENSIVE EQUIBHARAT.AI TEST SUITE")
        print("   Full Architecture: ML + XAI + Fairness + APIs + SPA")
        print("=======================================================")

    # ---------------- 1. ML & XAI ENGINE TESTS ----------------
    def test_01_ml_and_xai_pipeline(self):
        """Test trained Random Forest and SHAP TreeExplainer inference."""
        from xai_engine import EquiBharatExplainabilityEngine
        engine = EquiBharatExplainabilityEngine(model_dir=os.path.join(BASE_DIR, "models"))
        
        sample_applicant = {
            "ApplicantIncome": 55000,
            "CoapplicantIncome": 25000,
            "LoanAmount": 5.0,
            "Loan_Amount_Term": 60,
            "CIBIL_Score": 760,
            "Credit_History": 1,
            "Gender": "Male",
            "Married": "Yes",
            "Dependents": "1",
            "Education": "Graduate",
            "Self_Employed": "No",
            "Property_Area": "Urban"
        }
        res = engine.predict_and_explain(sample_applicant)
        
        self.assertIn("is_approved", res)
        self.assertIn("approval_probability", res)
        self.assertIn("risk_band", res)
        self.assertIn("feature_impacts", res)
        self.assertIn("explanations_en", res)
        self.assertIn("explanations_hi", res)
        self.assertIn("counterfactuals_en", res)
        self.assertIn("counterfactuals_hi", res)
        
        self.assertTrue(0 <= res["approval_probability"] <= 100)
        self.assertTrue(len(res["explanations_en"]["positive_factors"]) > 0)
        self.assertTrue(len(res["explanations_hi"]["positive_factors"]) > 0)
        print("  ✓ Test 1 Passed: Core ML & SHAP Bilingual XAI Engine operational.")

    # ---------------- 2. FAIRNESS & COMPLIANCE TESTS ----------------
    def test_02_fairness_auditor(self):
        """Test RBI Disparate Impact Ratio (DIR) compliance calculation."""
        from fairness_audit import EquiBharatFairnessAuditor
        auditor = EquiBharatFairnessAuditor(
            data_path=os.path.join(BASE_DIR, "data", "indian_loan_data.csv"),
            model_dir=os.path.join(BASE_DIR, "models")
        )
        report = auditor.compute_fairness_report()
        
        self.assertIn("summary", report)
        self.assertIn("gender_fairness", report)
        self.assertIn("geographic_fairness", report)
        self.assertTrue(report["gender_fairness"]["is_compliant"])
        self.assertTrue(report["geographic_fairness"]["is_compliant"])
        self.assertGreaterEqual(report["gender_fairness"]["disparate_impact_ratio"], 0.80)
        self.assertGreaterEqual(report["geographic_fairness"]["disparate_impact_ratio"], 0.80)
        print("  ✓ Test 2 Passed: RBI 80% Fair Lending Disparate Impact Audit verified.")

    # ---------------- 3. API HEALTH & STATUS ----------------
    def test_03_api_health(self):
        """Verify GET /api/health returns online status and DB statistics."""
        with urllib.request.urlopen(f"{API_BASE}/api/health") as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode())
            self.assertEqual(data["status"], "online")
            self.assertIn("EquiBharat", data["service"])
            self.assertGreaterEqual(data["total_applications_in_db"], 2500)
            print(f"  ✓ Test 3 Passed: Health check OK. MongoDB records: {data['total_applications_in_db']}.")

    # ---------------- 4. USER AUTH & ACCOUNT ID ----------------
    def test_04_user_login_and_account_id(self):
        """Verify POST /api/auth/google and /api/user-login store profile in MongoDB."""
        payload = json.dumps({
            "email": "test.user@equibharat.ai",
            "name": "EquiBharat Test Borrower",
            "picture": "https://images.unsplash.com/photo-1535713875002",
            "google_id": "google_123456789"
        }).encode()
        req = urllib.request.Request(
            f"{API_BASE}/api/auth/google",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode())
            self.assertIn("account_id", data)
            self.assertTrue(data["account_id"].startswith("EQUI-USR-"))
            self.assertEqual(data["email"], "test.user@equibharat.ai")
            self.assertIn("database_status", data)
            print(f"  ✓ Test 4 Passed: Google Auth synced to MongoDB Account ID: {data['account_id']}.")

    # ---------------- 5. SINGLE UNDERWRITING ----------------
    def test_05_underwrite_api(self):
        """Verify POST /api/underwrite evaluates loan and saves to MongoDB."""
        payload = json.dumps({
            "applicant_name": "Rohan Verma",
            "ApplicantIncome": 48000,
            "CoapplicantIncome": 15000,
            "LoanAmount": 3.8,
            "Loan_Amount_Term": 36,
            "CIBIL_Score": 735,
            "Credit_History": 1,
            "Gender": "Male",
            "Married": "Yes",
            "Dependents": "0",
            "Education": "Graduate",
            "Self_Employed": "No",
            "Property_Area": "Urban",
            "SelectedBank": "State Bank of India (SBI)"
        }).encode()
        req = urllib.request.Request(
            f"{API_BASE}/api/underwrite",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode())
            self.assertIn("application_id", data)
            self.assertIn("result", data)
            self.assertTrue(data["result"]["approval_probability"] > 90)
            self.assertTrue(data["persisted_in_mongodb"])
            print(f"  ✓ Test 5 Passed: Underwriting API approved ({data['result']['approval_probability']}%) and saved.")

    # ---------------- 6. BATCH UNDERWRITING ----------------
    def test_06_batch_underwrite_api(self):
        """Verify POST /api/batch-underwrite processes multiple borrowers concurrently."""
        applicants = [
            {
                "ApplicantIncome": 60000, "CoapplicantIncome": 0, "LoanAmount": 4.0,
                "Loan_Amount_Term": 60, "CIBIL_Score": 780, "Credit_History": 1,
                "Gender": "Female", "Married": "No", "Dependents": "0",
                "Education": "Graduate", "Self_Employed": "No", "Property_Area": "Urban"
            },
            {
                "ApplicantIncome": 20000, "CoapplicantIncome": 0, "LoanAmount": 8.0,
                "Loan_Amount_Term": 24, "CIBIL_Score": 540, "Credit_History": 0,
                "Gender": "Male", "Married": "Yes", "Dependents": "3+",
                "Education": "Not Graduate", "Self_Employed": "Yes", "Property_Area": "Rural"
            }
        ]
        payload = json.dumps({"applicants": applicants}).encode()
        req = urllib.request.Request(
            f"{API_BASE}/api/batch-underwrite",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode())
            self.assertEqual(data["processed_count"], 2)
            self.assertTrue(data["results"][0]["result"]["is_approved"])
            self.assertFalse(data["results"][1]["result"]["is_approved"])
            print("  ✓ Test 6 Passed: Batch underwriting handles multiple risk tiers correctly.")

    # ---------------- 7. COUNTERFACTUAL WHAT-IF ----------------
    def test_07_counterfactual_api(self):
        """Verify POST /api/counterfactual generates actionable levers to flip decision."""
        payload = json.dumps({
            "applicant": {
                "ApplicantIncome": 22000,
                "CoapplicantIncome": 0,
                "LoanAmount": 6.0,
                "Loan_Amount_Term": 24,
                "CIBIL_Score": 610,
                "Credit_History": 0,
                "Gender": "Male",
                "Married": "Yes",
                "Dependents": "2",
                "Education": "Graduate",
                "Self_Employed": "Yes",
                "Property_Area": "Semiurban"
            },
            "target_probability": 0.75
        }).encode()
        req = urllib.request.Request(
            f"{API_BASE}/api/counterfactual",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode())
            self.assertIn("counterfactual_scenarios", data)
            self.assertTrue(len(data["counterfactual_scenarios"]) > 0)
            print(f"  ✓ Test 7 Passed: Generated {len(data['counterfactual_scenarios'])} counterfactual what-if scenarios.")

    # ---------------- 8. AI CREDIT CHATBOT COPILOT ----------------
    def test_08_chatbot_copilot_api(self):
        """Verify POST /api/chat responds intelligently with specific financial advice."""
        # Query in English
        payload_en = json.dumps({
            "message": "How does my FOIR of 14% affect my SBI home loan?",
            "applicant_context": {
                "applicant_name": "Kunal Sharma",
                "ApplicantIncome": 45000,
                "CoapplicantIncome": 20000,
                "LoanAmount": 4.5,
                "Loan_Amount_Term": 60,
                "CIBIL_Score": 740,
                "SelectedBank": "State Bank of India (SBI)"
            }
        }).encode()
        req_en = urllib.request.Request(
            f"{API_BASE}/api/chat",
            data=payload_en,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req_en) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode())
            self.assertIn("reply", data)
            self.assertTrue(len(data["reply"]) > 50)
            self.assertTrue("FOIR" in data["reply"] or "EMI" in data["reply"] or "CIBIL" in data["reply"])

        # Query in Hindi
        payload_hi = json.dumps({
            "message": "कृपया मुझे बताएं कि ब्याज दर कम कैसे करें?",
            "applicant_context": {
                "applicant_name": "Kunal Sharma",
                "ApplicantIncome": 45000,
                "LoanAmount": 4.5,
                "CIBIL_Score": 740,
                "SelectedBank": "State Bank of India (SBI)"
            }
        }).encode()
        req_hi = urllib.request.Request(
            f"{API_BASE}/api/chat",
            data=payload_hi,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req_hi) as response:
            self.assertEqual(response.status, 200)
            data_hi = json.loads(response.read().decode())
            self.assertIn("reply", data_hi)
            self.assertTrue(len(data_hi["reply"]) > 30)
            print("  ✓ Test 8 Passed: Conversational AI Copilot responds specifically in English & Hindi.")

    # ---------------- 9. AI DOCUMENT SCANNER ----------------
    def test_09_document_scanner_api(self):
        """Verify POST /api/scan-document performs OCR and validates PAN & Income."""
        from document_scanner_engine import document_scanner
        sample_doc = b"GOVERNMENT OF INDIA\nINCOME TAX DEPARTMENT\nPermanent Account Number\nABCDE1234F\nName: Kunal Sharma\n"
        scan = document_scanner.scan_file(
            filename="pan_card.txt",
            file_bytes=sample_doc,
            applicant_name="Kunal Sharma",
            stated_income=45000.0
        )
        self.assertTrue(scan["verified"])
        self.assertEqual(scan["pan_number"], "ABCDE1234F")
        self.assertIn("Exact Match", scan["name_match_status"])
        self.assertTrue(scan["confidence"].startswith("99"))
        print("  ✓ Test 9 Passed: Document Scanner extracted PAN 'ABCDE1234F' and verified applicant.")

    # ---------------- 10. BANK REDIRECTION & LEADS ----------------
    def test_10_bank_redirection_lead_api(self):
        """Verify POST /api/log-bank-redirection registers borrower lead into MongoDB."""
        payload = json.dumps({
            "account_id": "EQUI-USR-0001",
            "bank_id": "hdfc",
            "bank_name": "HDFC Bank",
            "portal_url": "https://www.hdfcbank.com/personal/borrow/popular-loans",
            "loan_amount_lakhs": 5.0,
            "cibil_score": 750
        }).encode()
        req = urllib.request.Request(
            f"{API_BASE}/api/log-bank-redirection",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode())
            self.assertEqual(data["status"], "success")
            self.assertTrue(data["lead_id"].startswith("LEAD-"))
            self.assertEqual(data["redirect_url"], "https://www.hdfcbank.com/personal/borrow/popular-loans")
            print(f"  ✓ Test 10 Passed: Bank redirection tracked with Lead ID: {data['lead_id']}.")

    # ---------------- 11. AUDIT TRAIL & METRICS ----------------
    def test_11_audit_trail_and_metrics(self):
        """Verify GET /api/audit-trail and /api/metrics."""
        with urllib.request.urlopen(f"{API_BASE}/api/metrics") as r:
            self.assertEqual(r.status, 200)
            metrics = json.loads(r.read().decode())
            self.assertIn("cv_5fold_metrics", metrics)
            mean_acc = metrics["cv_5fold_metrics"]["mean_accuracy"]
            mean_auc = metrics["cv_5fold_metrics"]["mean_roc_auc"]
            self.assertGreater(mean_acc, 0.95)
            self.assertGreater(mean_auc, 0.95)

        with urllib.request.urlopen(f"{API_BASE}/api/audit-trail") as r:
            self.assertEqual(r.status, 200)
            trail = json.loads(r.read().decode())
            self.assertIn("total_audit_events", trail)
            print(f"  ✓ Test 11 Passed: Model Accuracy {mean_acc*100:.2f}%, ROC-AUC {mean_auc:.4f}.")

    # ---------------- 12. FRONTEND SPA SINGLE-URL SERVING ----------------
    def test_12_frontend_single_url_serving(self):
        """Verify root URL / serves compiled React Single-Page Application."""
        import re
        with urllib.request.urlopen(f"{API_BASE}/") as response:
            self.assertEqual(response.status, 200)
            html = response.read().decode()
            self.assertIn("<div id=\"root\"></div>", html)
            match = re.search(r'src="/assets/(index-[^"]+\.js)"', html)
            self.assertIsNotNone(match, "Could not find index-*.js script bundle in root HTML")
            print("  ✓ Test 12 Passed: Single URL http://localhost:8000/ correctly serves production React SPA.")

    # ---------------- 13. JAVASCRIPT ASSET BUNDLE INTEGRITY ----------------
    def test_13_bundle_file_integrity(self):
        """Verify the built bundle JS asset loads with HTTP 200 and valid JS structure."""
        import re, glob
        # Find latest asset filename from dist/assets
        assets = glob.glob(os.path.join(BASE_DIR, "frontend", "dist", "assets", "index-*.js"))
        self.assertTrue(len(assets) > 0, "No built index-*.js asset found")
        asset_basename = os.path.basename(assets[0])
        with urllib.request.urlopen(f"{API_BASE}/assets/{asset_basename}") as response:
            self.assertEqual(response.status, 200)
            js_data = response.read()
            self.assertGreater(len(js_data), 150000)
            print(f"  ✓ Test 13 Passed: Production bundle verified ({asset_basename}, {len(js_data)} bytes).")

    # ---------------- 14. POCKET FINANCE & DIGITAL GULLAK ----------------
    def test_14_pocket_finance_gullak_and_safety(self):
        """Verify Digital Gullak micro-savings, lender verification, SMS scam analyzer, and welfare schemes."""
        # 1. Deposit into Gullak
        dep_req = urllib.request.Request(
            f"{API_BASE}/api/pocket/gullak/deposit",
            data=json.dumps({
                "account_id": "test_citizen_01",
                "jar_id": "emergency",
                "jar_name": "Emergency Fund",
                "amount": 100.0,
                "note": "Initial test deposit"
            }).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(dep_req) as r:
            self.assertEqual(r.status, 200)
            res = json.loads(r.read().decode())
            self.assertEqual(res["status"], "success")
            self.assertGreaterEqual(res["total_saved"], 100.0)

        # 2. Get Gullak Summary
        with urllib.request.urlopen(f"{API_BASE}/api/pocket/gullak/test_citizen_01") as r:
            self.assertEqual(r.status, 200)
            res = json.loads(r.read().decode())
            self.assertIn("jar_breakdown", res)
            self.assertGreaterEqual(res["jar_breakdown"]["emergency"], 100.0)

        # 3. Verify Genuine Lender (SBI)
        vl_req = urllib.request.Request(
            f"{API_BASE}/api/pocket/verify-lender",
            data=json.dumps({"query": "State Bank of India"}).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(vl_req) as r:
            self.assertEqual(r.status, 200)
            res = json.loads(r.read().decode())
            self.assertEqual(res["verdict"], "VERIFIED_SAFE")
            self.assertTrue(res["is_safe"])

        # 4. Verify Predatory Lender Block (CashBean)
        vl_scam_req = urllib.request.Request(
            f"{API_BASE}/api/pocket/verify-lender",
            data=json.dumps({"query": "CashBean"}).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(vl_scam_req) as r:
            self.assertEqual(r.status, 200)
            res = json.loads(r.read().decode())
            self.assertEqual(res["verdict"], "DANGEROUS_SCAM")
            self.assertFalse(res["is_safe"])

        # 5. Analyze Phishing / Upfront Fee Scam SMS
        sms_req = urllib.request.Request(
            f"{API_BASE}/api/pocket/analyze-message",
            data=json.dumps({"message_text": "Congratulations! Loan of Rs 5 Lakh approved immediately. Pay processing fee of Rs 1,500 on bit.ly/loan500k to disburse within 10 minutes."}).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(sms_req) as r:
            self.assertEqual(r.status, 200)
            res = json.loads(r.read().decode())
            self.assertEqual(res["risk_level"], "High Risk / Potential Scam")
            self.assertFalse(res["is_safe"])
            self.assertGreaterEqual(res["flag_count"], 2)

        # 6. Fetch Central Welfare Schemes
        with urllib.request.urlopen(f"{API_BASE}/api/pocket/welfare-schemes") as r:
            self.assertEqual(r.status, 200)
            data = json.loads(r.read().decode())
            self.assertIn("schemes", data)
            self.assertGreaterEqual(len(data["schemes"]), 4)
            print("  ✓ Test 14 Passed: Pocket Finance (Gullak, RBI Lender Shield, SMS Scam Analyzer, Welfare Schemes) verified.")

    # ---------------- 15. BHARAT SCHEMES & REGULATORY DIRECTORY ----------------
    def test_15_national_government_schemes_and_regulatory_portal(self):
        """Verify Master Schemes Repository (Historic, Active, Upcoming), Licenses, RBI Rights, and Conquer Bridge."""
        # 1. Master Schemes Catalog
        with urllib.request.urlopen(f"{API_BASE}/api/schemes/catalog") as r:
            self.assertEqual(r.status, 200)
            data = json.loads(r.read().decode())
            self.assertGreaterEqual(data["total_count"], 15)
            self.assertIn("statistics", data)
            self.assertGreaterEqual(data["statistics"]["active_schemes"], 8)
            self.assertGreaterEqual(data["statistics"]["upcoming_schemes"], 3)
            self.assertGreaterEqual(data["statistics"]["historic_schemes"], 5)

        # 2. Filter Upcoming Pipeline Schemes
        with urllib.request.urlopen(f"{API_BASE}/api/schemes/catalog?status=UPCOMING") as r:
            self.assertEqual(r.status, 200)
            data = json.loads(r.read().decode())
            self.assertGreaterEqual(data["total_count"], 3)
            scheme_ids = [s["id"] for s in data["schemes"]]
            self.assertIn("viksit-msme-2027", scheme_ids)
            self.assertIn("pm-edrive-scheme", scheme_ids)

        # 3. Single Scheme Details & Roadmap Steps (MUDRA)
        with urllib.request.urlopen(f"{API_BASE}/api/schemes/mudra") as r:
            self.assertEqual(r.status, 200)
            data = json.loads(r.read().decode())
            self.assertEqual(data["status"], "found")
            scheme = data["scheme"]
            self.assertEqual(scheme["id"], "mudra")
            self.assertEqual(len(scheme["roadmap_steps"]), 4)
            self.assertTrue(scheme["has_loan_bridge"])
            self.assertTrue(any(dom in (scheme["official_portal_url"] + scheme["official_portal_name"]).lower() for dom in [".gov.in", ".org.in", ".nic.in"]))

        # 4. Government Licenses Directory (Udyam, GST, FSSAI, IEC, Shop Act, DPIIT)
        with urllib.request.urlopen(f"{API_BASE}/api/regulations/licenses") as r:
            self.assertEqual(r.status, 200)
            data = json.loads(r.read().decode())
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["total_licenses"], 6)
            lic_ids = [l["id"] for l in data["licenses"]]
            self.assertIn("udyam", lic_ids)
            self.assertIn("gst", lic_ids)
            self.assertIn("fssai", lic_ids)
            self.assertIn("iec", lic_ids)

        # 5. RBI Citizen Borrower Rights Directory
        with urllib.request.urlopen(f"{API_BASE}/api/regulations/rbi-rights") as r:
            self.assertEqual(r.status, 200)
            data = json.loads(r.read().decode())
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["total_rights"], 5)
            rights_ids = [rt["id"] for rt in data["rights"]]
            self.assertIn("dlg-2022", rights_ids)
            self.assertIn("fair-lending-80pct", rights_ids)
            self.assertIn("cibil-rights-30days", rights_ids)
            self.assertIn("rb-ios-14448", rights_ids)

        # 6. Conquer Readiness Evaluation & Private Commercial Bridge
        conquer_req = urllib.request.Request(
            f"{API_BASE}/api/schemes/conquer-readiness",
            data=json.dumps({
                "scheme_id": "mudra",
                "applicant_income": 60000.0,
                "cibil_score": 760,
                "has_aadhaar": True,
                "has_pan": True,
                "has_bank_account": True
            }).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(conquer_req) as r:
            self.assertEqual(r.status, 200)
            readiness = json.loads(r.read().decode())
            self.assertEqual(readiness["scheme_id"], "mudra")
            self.assertEqual(readiness["readiness_score"], 100)
            self.assertEqual(readiness["readiness_band"], "High Success Probability")
            self.assertTrue(readiness["equibharat_loan_bridge"]["is_applicable"])
            print("  ✓ Test 15 Passed: Bharat Schemes & Regulations (Historic/Active/Upcoming, Licenses, RBI Rights, Conquer Bridge) verified.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
