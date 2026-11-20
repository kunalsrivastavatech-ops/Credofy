"""
Tests for Credofy Premium Borrower Assistance Service (Isolated Local Demo)
"""
import unittest
import urllib.request
import urllib.parse
import json
import os
import io

API_BASE = "http://localhost:8000"

class CredofyPremiumTestSuite(unittest.TestCase):

    def test_01_verify_request_validation_failure(self):
        """Verify that submitting without consent or valid data fails gracefully."""
        url = f"{API_BASE}/api/premium/verify-request"
        
        # Test missing consent
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="full_name"\r\n\r\n'
            f"Test User\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="email"\r\n\r\n'
            f"test@example.com\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="mobile"\r\n\r\n'
            f"9876543210\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="utr_number"\r\n\r\n'
            f"431289012345\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="consent"\r\n\r\n'
            f"false\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="screenshot"; filename="sample.png"\r\n'
            f"Content-Type: image/png\r\n\r\n"
            f"FAKEDATA\r\n"
            f"--{boundary}--\r\n"
        ).encode('utf-8')

        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req) as resp:
                self.fail("Should have raised 400 for consent=false")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
            err_data = json.loads(e.read().decode('utf-8'))
            self.assertIn("Consent", err_data["detail"])
            print("  ✓ Test 1 Passed: Consent validation properly enforces 400 rejection.")

    def test_02_successful_premium_submission(self):
        """Verify successful verification submission returns CRD-PREM-2026-XXXXX and saves isolated record."""
        url = f"{API_BASE}/api/premium/verify-request"
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="full_name"\r\n\r\n'
            f"Rohan Verma\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="email"\r\n\r\n'
            f"rohan.verma@example.com\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="mobile"\r\n\r\n'
            f"9876543210\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="utr_number"\r\n\r\n'
            f"UTR499281729012\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="rejection_notes"\r\n\r\n'
            f"Personal loan rejected at HDFC Bank due to low CIBIL score.\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="consent"\r\n\r\n'
            f"true\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="screenshot"; filename="payment_receipt.png"\r\n'
            f"Content-Type: image/png\r\n\r\n"
            f"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRTESTIMAGEBYTES\r\n"
            f"--{boundary}--\r\n"
        ).encode('utf-8', errors='surrogateescape')

        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            res_data = json.loads(resp.read().decode('utf-8'))
            self.assertEqual(res_data["status"], "success")
            ref_id = res_data["reference_id"]
            self.assertTrue(ref_id.startswith("CRD-PREM-2026-"))
            self.assertEqual(res_data["data"]["amount"], 499)
            self.assertEqual(res_data["data"]["status"], "Pending Verification")
            print(f"  ✓ Test 2 Passed: Created Premium Request {ref_id} successfully.")

            # Test 03: Status Lookup
            status_url = f"{API_BASE}/api/premium/status/{ref_id}"
            with urllib.request.urlopen(status_url) as s_resp:
                self.assertEqual(s_resp.status, 200)
                s_data = json.loads(s_resp.read().decode('utf-8'))
                self.assertEqual(s_data["data"]["reference_id"], ref_id)
                self.assertEqual(s_data["data"]["full_name"], "Rohan Verma")
                print(f"  ✓ Test 3 Passed: Successfully queried status for {ref_id}.")

            # Test 04: Customer Requests Query
            my_url = f"{API_BASE}/api/premium/my-requests?identifier=9876543210"
            with urllib.request.urlopen(my_url) as m_resp:
                self.assertEqual(m_resp.status, 200)
                m_data = json.loads(m_resp.read().decode('utf-8'))
                self.assertGreaterEqual(m_data["count"], 1)
                matching = [r for r in m_data["requests"] if r["reference_id"] == ref_id]
                self.assertEqual(len(matching), 1)
                print(f"  ✓ Test 4 Passed: Customer Dashboard query returned {m_data['count']} requests.")

if __name__ == '__main__':
    unittest.main()
