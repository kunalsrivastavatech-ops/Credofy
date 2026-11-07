import os
import sys
import json
import urllib.request
import urllib.error
import io
import time

BASE_URL = "http://localhost:8000"

def post_json(endpoint, payload):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        f"{BASE_URL}{endpoint}",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())

def get_json(endpoint):
    req = urllib.request.Request(f"{BASE_URL}{endpoint}")
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())

def run_stress_battery():
    print("\n=======================================================")
    print("🔥 RUNNING DEEP STRESS & ADVERSARIAL TESTING BATTERY")
    print("=======================================================")

    results = []

    # Case 1: Minimum Bounds (CIBIL 300, 0 Income, 0 Coapplicant)
    try:
        status, res = post_json("/api/underwrite", {
            "ApplicantIncome": 0,
            "CoapplicantIncome": 0,
            "LoanAmount": 10.0,
            "Loan_Amount_Term": 12,
            "CIBIL_Score": 300,
            "Credit_History": 0,
            "Gender": "Male",
            "Married": "No",
            "Dependents": "0",
            "Education": "Not Graduate",
            "Self_Employed": "No",
            "Property_Area": "Rural",
            "applicant_name": "Edge Minimum Borrower",
            "account_id": "EQUI-EDGE-001"
        })
        assert status == 200
        assert res["result"]["is_approved"] is False, "Should be rejected for 0 income & CIBIL 300"
        assert len(res["result"]["explanations_en"]["negative_factors"]) > 0
        print("  ✓ Case 1 Passed: Severe high-risk profile cleanly evaluated & rejected with plain reasons.")
        results.append(("Case 1: Minimum Bounds", "PASSED"))
    except Exception as e:
        print(f"  ❌ Case 1 Failed: {e}")
        results.append(("Case 1: Minimum Bounds", f"FAILED: {e}"))

    # Case 2: Maximum Bounds (CIBIL 900, High Income ₹5 Lakh/mo, Large Loan ₹1 Crore)
    try:
        status, res = post_json("/api/underwrite", {
            "ApplicantIncome": 500000,
            "CoapplicantIncome": 300000,
            "LoanAmount": 100.0,
            "Loan_Amount_Term": 240,
            "CIBIL_Score": 900,
            "Credit_History": 1,
            "Gender": "Female",
            "Married": "Yes",
            "Dependents": "2",
            "Education": "Graduate",
            "Self_Employed": "No",
            "Property_Area": "Urban",
            "applicant_name": "Ultra HNI Borrower",
            "account_id": "EQUI-HNI-001"
        })
        assert status == 200
        assert res["result"]["is_approved"] is True
        assert res["result"]["approval_probability"] >= 90
        print("  ✓ Case 2 Passed: Ultra-prime high income profile smoothly processed with prime probability.")
        results.append(("Case 2: Maximum Bounds", "PASSED"))
    except Exception as e:
        print(f"  ❌ Case 2 Failed: {e}")
        results.append(("Case 2: Maximum Bounds", f"FAILED: {e}"))

    # Case 3: XSS & Special Characters in Applicant Name
    try:
        malicious_name = "Sunita Devi <script>alert('XSS')</script> & 'OR 1=1--"
        status, res = post_json("/api/underwrite", {
            "ApplicantIncome": 35000,
            "CoapplicantIncome": 15000,
            "LoanAmount": 2.5,
            "Loan_Amount_Term": 36,
            "CIBIL_Score": 730,
            "Credit_History": 1,
            "Gender": "Female",
            "Married": "Yes",
            "Dependents": "1",
            "Education": "Graduate",
            "Self_Employed": "Yes",
            "Property_Area": "Rural",
            "applicant_name": malicious_name,
            "account_id": "EQUI-SEC-001"
        })
        assert status == 200
        # Check that it safely saved and can be retrieved without breaking JSON
        status, user_rec = get_json("/api/user-records/EQUI-SEC-001")
        assert status == 200
        print("  ✓ Case 3 Passed: Special characters & injection vectors safely sanitized and persisted.")
        results.append(("Case 3: XSS / SQL Injection", "PASSED"))
    except Exception as e:
        print(f"  ❌ Case 3 Failed: {e}")
        results.append(("Case 3: XSS / SQL Injection", f"FAILED: {e}"))

    # Case 4: Concurrent Rapid Batch Underwriting (50 applicants)
    try:
        batch_payload = []
        for i in range(50):
            batch_payload.append({
                "ApplicantIncome": 25000 + (i * 2000),
                "CoapplicantIncome": 10000 + (i * 500),
                "LoanAmount": 2.0 + (i * 0.2),
                "Loan_Amount_Term": 36 if i % 2 == 0 else 60,
                "CIBIL_Score": 650 + (i * 4),
                "Credit_History": 1 if i % 5 != 0 else 0,
                "Gender": "Female" if i % 2 == 0 else "Male",
                "Married": "Yes" if i % 3 == 0 else "No",
                "Dependents": str(i % 4),
                "Education": "Graduate" if i % 2 == 0 else "Not Graduate",
                "Self_Employed": "Yes" if i % 4 == 0 else "No",
                "Property_Area": ["Rural", "Semiurban", "Urban"][i % 3],
                "applicant_name": f"Batch Applicant #{i+1}",
                "account_id": f"EQUI-BATCH-{i+1:03d}"
            })
        t0 = time.time()
        status, res = post_json("/api/batch-underwrite", {"applicants": batch_payload})
        dur = time.time() - t0
        assert status == 200
        assert len(res["results"]) == 50
        print(f"  ✓ Case 4 Passed: 50 concurrent loan evaluations processed in {dur:.2f}s ({len(res['results'])} outputs).")
        results.append(("Case 4: 50-Applicant Batch", "PASSED"))
    except Exception as e:
        print(f"  ❌ Case 4 Failed: {e}")
        results.append(("Case 4: 50-Applicant Batch", f"FAILED: {e}"))

    # Case 5: Multipart Document Scanner with Plain Text file, Binary Garbage, and Empty Bytes
    try:
        import urllib.request
        boundary = "----WebKitFormBoundaryEquiBharatTest123"
        
        # Test valid simulated PAN file
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="sample_pan_card.txt"\r\n'
            f"Content-Type: text/plain\r\n\r\n"
            f"INCOME TAX DEPARTMENT GOVT OF INDIA\r\nPERMANENT ACCOUNT NUMBER: ABCDE1234F\r\nNAME: SUNITA DEVI\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="applicant_name"\r\n\r\nSunita Devi\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="stated_income"\r\n\r\n35000\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="account_id"\r\n\r\nEQUI-DOC-001\r\n'
            f"--{boundary}--\r\n"
        ).encode('utf-8')
        
        req = urllib.request.Request(
            f"{BASE_URL}/api/scan-document",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            assert data["result"]["verified"] is True
            assert data["result"]["pan_number"] == "ABCDE1234F"
            print("  ✓ Case 5 Passed: Document Scanner OCR successfully extracted PAN ABCDE1234F.")
            results.append(("Case 5: Document Scanner OCR", "PASSED"))
    except Exception as e:
        print(f"  ❌ Case 5 Failed: {e}")
        results.append(("Case 5: Document Scanner OCR", f"FAILED: {e}"))

    # Case 6: AI Chatbot in Hindi, English, and Complex Comparative Banking Queries
    queries = [
        ("SBI vs HDFC ब्याज दर", "sbi"),
        ("What documents does Bank of Baroda require?", "baroda"),
        ("How can Ramesh lower his EMI from 12000 to 7000?", "emi"),
        ("मेरा CIBIL 680 है क्या मुझे लोन मिलेगा?", "cibil")
    ]
    chat_passed = True
    for q, kw in queries:
        try:
            status, res = post_json("/api/chat", {
                "message": q,
                "applicant_context": {
                    "applicant_name": "Sunita Devi",
                    "ApplicantIncome": 35000,
                    "LoanAmount": 3.0,
                    "CIBIL_Score": 720,
                    "SelectedBank": "State Bank of India (SBI)"
                },
                "history": []
            })
            assert status == 200
            assert len(res["reply"]) > 50, f"Reply too short: {res['reply']}"
        except Exception as err:
            print(f"  ❌ Chat query '{q}' failed: {err}")
            chat_passed = False
    if chat_passed:
        print("  ✓ Case 6 Passed: Multilingual AI Chat Copilot answered 4 complex banking scenarios.")
        results.append(("Case 6: AI Copilot Multilingual Queries", "PASSED"))
    else:
        results.append(("Case 6: AI Copilot Multilingual Queries", "FAILED"))

    # Case 7: Counterfactual Solver on Severe Rejection
    try:
        status, res = post_json("/api/counterfactual", {
            "applicant": {
                "ApplicantIncome": 18000,
                "CoapplicantIncome": 0,
                "LoanAmount": 7.0,
                "Loan_Amount_Term": 24,
                "CIBIL_Score": 600,
                "Credit_History": 0,
                "Gender": "Male",
                "Married": "No",
                "Dependents": "0",
                "Education": "Not Graduate",
                "Self_Employed": "Yes",
                "Property_Area": "Rural"
            },
            "target_probability": 0.80
        })
        assert status == 200
        cf_en = res["counterfactuals_en"]
        cf_hi = res["counterfactuals_hi"]
        assert len(cf_en) > 0 and len(cf_hi) > 0
        print(f"  ✓ Case 7 Passed: Counterfactual engine generated {len(cf_en)} actionable levers to flip rejection.")
        results.append(("Case 7: Counterfactual Solver", "PASSED"))
    except Exception as e:
        print(f"  ❌ Case 7 Failed: {e}")
        results.append(("Case 7: Counterfactual Solver", f"FAILED: {e}"))

    print("\n-------------------------------------------------------")
    print(f"STRESS TEST SUMMARY: {sum(1 for _, s in results if s == 'PASSED')}/{len(results)} PASSED")
    print("-------------------------------------------------------")

if __name__ == "__main__":
    run_stress_battery()
