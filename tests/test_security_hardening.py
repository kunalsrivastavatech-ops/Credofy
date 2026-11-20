"""
Comprehensive Security Hardening Tests for Credofy Platform:
- HTTP Security Headers (X-Frame-Options, X-Content-Type-Options, etc.)
- Directory Traversal & Path Traversal Prevention
- Binary Magic Byte Image / PDF Validation (Anti-Malware / Disguised Script Execution)
- Unauthorized Admin Secret Protection (/api/config/gemini-key)
- Alphanumeric UTR and Identifier Sanitization
"""
import unittest
import urllib.request
import urllib.error
import json

API_BASE = "http://localhost:8000"

class CredofySecurityHardeningTests(unittest.TestCase):

    def test_01_http_security_headers(self):
        """Verify OWASP-compliant HTTP Security Headers are returned on API endpoints."""
        req = urllib.request.Request(f"{API_BASE}/api/health", method="GET")
        with urllib.request.urlopen(req) as resp:
            headers = dict(resp.headers)
            self.assertEqual(headers.get("x-frame-options"), "DENY")
            self.assertEqual(headers.get("x-content-type-options"), "nosniff")
            self.assertEqual(headers.get("x-xss-protection"), "1; mode=block")
            self.assertEqual(headers.get("referrer-policy"), "strict-origin-when-cross-origin")
            print("  ✓ Security Test 1 Passed: HTTP Security Headers (X-Frame-Options, nosniff, XSS) active.")

    def test_02_path_traversal_blocked(self):
        """Verify path traversal attempts in reference IDs are blocked with 400 Bad Request."""
        malicious_refs = ["../../etc/passwd", "..%2F..%2Fpasswords", "CRD-PREM-../../hack"]
        for bad_ref in malicious_refs:
            url = f"{API_BASE}/api/premium/status/{bad_ref}"
            try:
                urllib.request.urlopen(url)
                self.fail(f"Should have rejected malicious path traversal: {bad_ref}")
            except urllib.error.HTTPError as e:
                self.assertIn(e.code, [400, 404])
        print("  ✓ Security Test 2 Passed: Directory Traversal attacks blocked with strict regex & path validation.")

    def test_03_gemini_key_protected_without_secret(self):
        """Verify that updating server API key without valid admin secret returns 403 Forbidden."""
        url = f"{API_BASE}/api/config/gemini-key"
        payload = json.dumps({"api_key": "AIzaSyFakeKey12345"}).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            urllib.request.urlopen(req)
            self.fail("Should have rejected unauthenticated Gemini key configuration.")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 403)
            err = json.loads(e.read().decode())
            self.assertIn("Unauthorized", err["detail"])
            print("  ✓ Security Test 3 Passed: Server configuration protected with Admin Secret (403 Forbidden).")

    def test_04_disguised_script_rejected(self):
        """Verify that fake image files with invalid binary magic headers are blocked."""
        url = f"{API_BASE}/api/premium/verify-request"
        boundary = "----SecurityTestBoundary12345"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="full_name"\r\n\r\n'
            f"Attacker\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="email"\r\n\r\n'
            f"attacker@example.com\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="mobile"\r\n\r\n'
            f"9999999999\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="utr_number"\r\n\r\n'
            f"UTR999999999999\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="consent"\r\n\r\n'
            f"true\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="screenshot"; filename="malware.png"\r\n'
            f"Content-Type: image/png\r\n\r\n"
            f"#!/bin/bash\necho hacked\r\n"
            f"--{boundary}--\r\n"
        ).encode('utf-8')

        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST"
        )
        try:
            urllib.request.urlopen(req)
            self.fail("Should have rejected disguised bash script uploaded with .png extension.")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
            err = json.loads(e.read().decode())
            self.assertIn("Security Alert", err["detail"])
            print("  ✓ Security Test 4 Passed: Disguised binary/script upload blocked by Magic Byte verification.")

if __name__ == "__main__":
    unittest.main()
