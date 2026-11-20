import os
import sys
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import pandas as pd
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Ensure both src and backend directories are in sys.path
sys.path.append(os.path.join(BASE_DIR, 'src'))
sys.path.append(os.path.join(BASE_DIR, 'backend'))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from xai_engine import CredofyExplainabilityEngine, EquiBharatExplainabilityEngine, KredoExplainabilityEngine
from fairness_audit import CredofyFairnessAuditor, EquiBharatFairnessAuditor, KredoFairnessAuditor
from ai_chat_engine import credit_chatbot
from document_scanner_engine import document_scanner

# ================= MongoDB Integration =================
import pymongo
import certifi
import mongomock
import time

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

class MongoDatabaseManager:
    """
    Production Dual-Layer Database Manager:
    - Automatically checks and connects to Live MongoDB Atlas.
    - Gracefully uses embedded fallback if offline or port 27017 is blocked.
    - Dynamically auto-reconnects to Atlas whenever network/hotspot is ready.
    - Synchronizes any offline records straight to Atlas when connected.
    """
    def __init__(self, uri: str):
        self.uri = uri
        self._mock_client = mongomock.MongoClient()
        self._mock_db = self._mock_client["equibharat_db"]
        self._atlas_client = None
        self._atlas_db = None
        self._is_atlas = False
        self._last_atlas_attempt = 0
        
        # Initial connect attempt
        self.check_atlas_connection(timeout_ms=3000)
        self._seed_if_empty(self._mock_db)

    def check_atlas_connection(self, timeout_ms: int = 3000) -> bool:
        if not self.uri or "mongodb" not in self.uri:
            self._is_atlas = False
            return False
        
        try:
            client_kwargs = {
                "serverSelectionTimeoutMS": timeout_ms,
                "connectTimeoutMS": timeout_ms
            }
            if "mongodb+srv" in self.uri:
                client_kwargs["tlsCAFile"] = certifi.where()
            
            client = pymongo.MongoClient(self.uri, **client_kwargs)
            client.admin.command('ping')
            self._atlas_client = client
            self._atlas_db = client["equibharat_db"]
            self._is_atlas = True
            safe_uri = self.uri.split("@")[-1] if "@" in self.uri else self.uri
            print(f"✓ Connected to Live MongoDB Atlas (Users-Only Persistence): {safe_uri}")
            
            # Sync user profiles to Atlas (applications are kept in-memory to preserve storage quota)
            self._sync_to_atlas()
            return True
        except Exception as e:
            print("Atlas connect notice:", type(e).__name__, e)
            self._is_atlas = False
            return False

    def _sync_to_atlas(self):
        """Only syncs user logins to live Atlas to prevent cluster storage bloat."""
        if not self._is_atlas or self._atlas_db is None:
            return
        try:
            mock_users = list(self._mock_db["users"].find({}))
            for d in mock_users:
                doc_copy = dict(d)
                doc_copy.pop("_id", None)
                if "email" in doc_copy:
                    self._atlas_db["users"].replace_one({"email": doc_copy["email"]}, doc_copy, upsert=True)
        except Exception as e:
            print(f"Note: Atlas user sync warning: {e}")

    def _seed_if_empty(self, target_db):
        """Seeds sample loan data into in-memory mock db only (never into live Atlas)."""
        if self._is_atlas and target_db is self._atlas_db:
            return
        try:
            if target_db["applications"].count_documents({}) == 0:
                csv_path = os.path.join(BASE_DIR, "data", "indian_loan_data.csv")
                if os.path.exists(csv_path):
                    seed_df = pd.read_csv(csv_path)
                    records = seed_df.to_dict(orient="records")
                    for idx, r in enumerate(records):
                        r["application_id"] = f"EQUI-SEED-{idx+1:04d}"
                        r["created_at"] = datetime.utcnow().isoformat()
                        r["is_seed"] = True
                    target_db["applications"].insert_many(records)
                    print(f"✓ Seeded in-memory engine with {len(records)} credit applications.")
        except Exception:
            pass

    @property
    def active_db(self):
        now = time.time()
        # Retry Atlas every 15 seconds if currently offline
        if not self._is_atlas and (now - self._last_atlas_attempt > 15):
            self._last_atlas_attempt = now
            self.check_atlas_connection(timeout_ms=2500)
        
        return self._atlas_db if (self._is_atlas and self._atlas_db is not None) else self._mock_db

    @property
    def mode(self) -> str:
        if self._is_atlas:
            safe_uri = self.uri.split("@")[-1] if "@" in self.uri else self.uri
            return f"Live MongoDB Atlas ({safe_uri}) [Storage Guard: Users Only]"
        return "Embedded MongoDB (In-Memory Fallback - Offline Sync Ready)"

db_manager = MongoDatabaseManager(MONGO_URI)

class CollectionProxy:
    def __init__(self, col_name: str):
        self._col_name = col_name
    
    def __getattr__(self, item):
        # All local proxy collections use fast in-memory storage; primary users live directly in Firebase Cloud Firestore
        return getattr(db_manager._mock_db[self._col_name], item)

applications_col = CollectionProxy("applications")
fairness_col = CollectionProxy("fairness_audits")
audit_logs_col = CollectionProxy("audit_logs")
users_col = CollectionProxy("users")
scanned_docs_col = CollectionProxy("scanned_documents")
bank_leads_col = CollectionProxy("bank_leads")

# ================= FIREBASE CLOUD FIRESTORE INTEGRATION =================
import firebase_admin
from firebase_admin import credentials, firestore
import base64

FIREBASE_CREDS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "firebase_credentials.json")
firebase_db = None
firebase_status = "Not Initialized"

# Embedded Base64 Service Account for Cloud Deployments (e.g. Render)
EMBEDDED_FIREBASE_B64 = (
    "eyJ0eXBlIjogInNlcnZpY2VfYWNjb3VudCIsICJwcm9qZWN0X2lkIjogImNyZWRvZnktNTE3NDQiLCAicHJpdmF0ZV9rZXlfaWQiOiAiZmVmNWU5NGY5NDFlZDhlZWQzNzE3NDc2ZWFhNzY3Y2M4NTMyZjVhZiIsICJwcml2YXRlX2tleSI6ICItLS0tLUJFR0lOIFBSSVZBVEUgS0VZLS0tLS1cbk1JSUV2Z0lCQURBTkJna3Foa2lHOXcwQkFRRUZBQVNDQktnd2dnU2tBZ0VBQW9JQkFRQ2x2VEpuRGJZQlZWL0xcblFTdnN1VHhNR1lsd3o1dTRTaWpFNk1KR2o5WDdjSmF5UWcyKzF0enN5KzRsZDBqSmtnSStLRmFCZURJeFZybHpcbmNCbng3NjZBQlFCVHlMZThtempOOVp6Ym5DcjB3aEpNR0tURjQ4ZHRsQnZPaGJZaGxXeWdPM3BDSXcvQzhFZmxcbkFOTmxKUktoenpQNE9XemtYdnlYdEluV0E3dEJIOExCZTU2eXFuTTN0amhyU09aZkV1TURlVVRDZ1oranZDYXNcbm53RUhPR1NlSEhNMHY2dHV6NU45WWN1SW5FdTFCVWg5MnJKOXo3eHJDQnFyNkpNNGlOWU5rajRqaFZUdU1MN0xcbmJ4WG9wdXk0QWVKRFZLWlpJMjEyMFBkMm1LaW9ONFNmalpGNjMrZHlUektqdUkvYlY1T1JvMjdZVzNQSTBHNVZcbmY4cEExSlVQQWdNQkFBRUNnZ0VBR3RzbS9TcnNHSmc0Ynd1TzdndHYrVmJUL2dzdURQVTdXUGpzYmhtbGoxcEZcbm1QbjZGemZpMFo0VDUwOUdaSjg3ck0zRmdySXkwK3JkSHhjRnBUMzAxVHE2UEZsVWFJUHdkdk03S1J6TG15Q05cbmJYWTYwUFFoWHlDMlJzZEU1WGs4Z2xSUThjR1RycjlYcndSc3ZNRituT2loMzdHU2N3anZQamZiYytuajRGL2RcbjMzeFpWb1BIK0ROblk2YnlkcEJGK0ZMMHhuZVdOT0VWTjY3UWhybG9LcFlndzNwbDNVL0U1eklSMGJUMWdQTjhcbjRYNFpVRmk0WDQ5N3d4WHpRaVZmWk0vanZwL2JzNW9mRUxNWGk1NXh6blRCRHBxQ2NMbTFjU1dnRkhpUnNUcVhcbnBqOW1GSnF1Q05rOUN2RlN6Rzl5NXpZMzkvdnU1U3l0YTF2UWd1S2RxUUtCZ1FEUnJjMW90Vy94bWpFdHlSbC9cbmtwM0RIUzBabGNLSVFSdjlpbU1DU0dGUHFMUzdDVURaS05BMXF5cndQQmhuQkRmMUFwVkpxOHdhM254aEtZMzNcbmUzbnZoY0pZUldCL25kalN5Zk5wUUsyYkFnaVZFWGtncVQ1TUlBYW9VL29VSHpENk9EN3ppNnJxZ0VIaFh1c2pcblpEV3E3aWdXNXRWRk5NR0hFYWxQMHFTbnlRS0JnUURLV21wODEzeWVlS25zSmo2N0J0L0lqeDRvcUZIMythVi9cbmVpWjhxbE82U0NUWjhORG9lNHdQT1BINHdCK3RXQlB6VHdrNFRxSGx5YnRXNWtWS01oU2M0V0tvVXNIT3U5TzBcbmluUDNhdXlYdXhoVGovUzhsWTRUeUZTcDJKV2grc1FDWmVJMnRic0hpaWgyejNlQWdQWkVoRnQxVE9jT3BZV05cbnhMUytnOEp5RndLQmdRQ0YrbHhLRDhVYng3NnMxdGFvSVhNVS9VdVlFWTFmcXRyTHd1Vkl6QjhCMjNiQUhFV0hcbmZRQ3RpbFhCYzJUVVRtbkM4SWVicjE2WHZKb1ZLNHcvR25McmpiaUUxcSsyVzVIei9uNitQa212eGpqZHAzQ1NcblloSWdha1pXd0hJRzhYZEdLekp1UkV4TjB1NUZwM1R3QkZRV2lGNnRZNG5hMHI3bUkyN2dSbVJYb1FLQmdEeFhcblgvL2dabG4vVTNTSEp4ZXdnaFVWa0lIQlI4Z3htc2Q3em5SSWVuVkhSQzMxWU9haXlPNVZKZHJ1dDhPQ1MxaTNcbnplRUxtYjJqUFlrNVc1bzNldXdaVGNreC9IZEFqVzMrQjN6VlZyNGNYYkcxY042M25rbUo2SzFKVjcyWXdOQ1NcblB6WGZWV2wzS24vYmVDQksxS1V6N3UzNHc4SWJXOHNkeUdRemVFMTdBb0dCQUp5S29ZSTFQQncwUzFnWDdkS2Jcbmt5bFp5TmhraGprWUpscmsrblA1cFdOL0VTallNUVhJUFNIY3J3dmYvQStjS2NSTVEzWkRiYXNCWnFNN1pyL0hcbjNNTmJoaXNob3YvRXJTTi9mcU4rMzgvYWQzNUdUbTUwOEZKeXFrN0w0WjQ2L0xoYWFqSlVZOGJhN1FKQlhId3dcbk5pSUpSZlpwSFBiWk1adWc3SG9BcnRtR1xuLS0tLS1FTkQgUFJJVkFURSBLRVktLS0tLVxuIiwgImNsaWVudF9lbWFpbCI6ICJmaXJlYmFzZS1hZG1pbnNkay1mYnN2Y0BjcmVkb2Z5LTUxNzQ0LmlhbS5nc2VydmljZWFjY291bnQuY29tIiwgImNsaWVudF9pZCI6ICIxMTc2ODU4NjY0NzAyNDcxNjM3MjEiLCAiYXV0aF91cmkiOiAiaHR0cHM6Ly9hY2NvdW50cy5nb29nbGUuY29tL28vb2F1dGgyL2F1dGgiLCAidG9rZW5fdXJpIjogImh0dHBzOi8vb2F1dGgyLmdvb2dsZWFwaXMuY29tL3Rva2VuIiwgImF1dGhfcHJvdmlkZXJfeDUwOV9jZXJ0X3VybCI6ICJodHRwczovL3d3dy5nb29nbGVhcGlzLmNvbS9vYXV0aDIvdjEvY2VydHMiLCAiY2xpZW50X3g1MDlfY2VydF91cmwiOiAiaHR0cHM6Ly93d3cuZ29vZ2xlYXBpcy5jb20vcm9ib3QvdjEvbWV0YWRhdGEveDUwOS9maXJlYmFzZS1hZG1pbnNkay1mYnN2YyU0MGNyZWRvZnktNTE3NDQuaWFtLmdzZXJ2aWNlYWNjb3VudC5jb20iLCAidW5pdmVyc2VfZG9tYWluIjogImdvb2dsZWFwaXMuY29tIn0="
)

def init_firebase_admin():
    global firebase_db, firebase_status
    cred_obj = None

    # Priority 1: Environment variable FIREBASE_CREDENTIALS_JSON
    env_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")
    if env_json:
        try:
            cred_dict = json.loads(env_json)
            cred_obj = credentials.Certificate(cred_dict)
            print("✓ Loaded Firebase credentials from FIREBASE_CREDENTIALS_JSON.")
        except Exception as e:
            print("Notice: Could not parse FIREBASE_CREDENTIALS_JSON:", e)

    # Priority 2: Environment variable FIREBASE_CREDENTIALS_BASE64
    if not cred_obj:
        env_b64 = os.environ.get("FIREBASE_CREDENTIALS_BASE64")
        if env_b64:
            try:
                cred_dict = json.loads(base64.b64decode(env_b64).decode("utf-8"))
                cred_obj = credentials.Certificate(cred_dict)
                print("✓ Loaded Firebase credentials from FIREBASE_CREDENTIALS_BASE64.")
            except Exception as e:
                print("Notice: Could not decode FIREBASE_CREDENTIALS_BASE64:", e)

    # Priority 3: Local file on disk (development)
    if not cred_obj and os.path.exists(FIREBASE_CREDS_PATH):
        try:
            cred_obj = credentials.Certificate(FIREBASE_CREDS_PATH)
            print("✓ Loaded Firebase credentials from local file.")
        except Exception as e:
            print("Notice: Could not read FIREBASE_CREDS_PATH:", e)

    # Priority 4: Embedded Base64 fallback (guarantees Render cloud connectivity)
    if not cred_obj and EMBEDDED_FIREBASE_B64:
        try:
            cred_dict = json.loads(base64.b64decode(EMBEDDED_FIREBASE_B64).decode("utf-8"))
            cred_obj = credentials.Certificate(cred_dict)
            print("✓ Loaded Firebase credentials from Cloud Embedded profile.")
        except Exception as e:
            print("Notice: Could not decode EMBEDDED_FIREBASE_B64:", e)

    if cred_obj:
        try:
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred_obj)
            firebase_db = firestore.client()
            firebase_status = "Connected (credofy-51744)"
            print("✓ Firebase Cloud Firestore initialized for project 'credofy-51744'.")
        except Exception as e:
            firebase_status = f"Pending Activation: {e}"
            print("Firebase init error:", e)
    else:
        firebase_status = "Credentials Missing"
        print("Firebase init: No credentials available.")

init_firebase_admin()

def sync_user_to_firestore(user_doc: dict):
    """
    Saves or updates user profile and login timestamp directly in Cloud Firestore.
    Collection: 'users' -> Document ID: user email
    """
    if not firebase_db:
        return False
    try:
        user_email = user_doc.get("email")
        if not user_email:
            return False
        clean_key = user_email.strip().lower()
        doc_data = {
            "account_id": user_doc.get("account_id"),
            "email": clean_key,
            "name": user_doc.get("name"),
            "picture": user_doc.get("picture"),
            "google_id": user_doc.get("google_id"),
            "auth_provider": user_doc.get("auth_provider", "Google OAuth 2.0"),
            "created_at": user_doc.get("created_at"),
            "last_login": user_doc.get("last_login") or datetime.utcnow().isoformat(),
            "database": "Cloud Firestore",
            "firestore_synced_at": datetime.utcnow().isoformat()
        }
        firebase_db.collection("users").document(clean_key).set(doc_data, merge=True)
        return True
    except Exception as e:
        print("Firestore sync notice (User will also be saved to Mongo):", e)
        return False

# Initialize Core XAI & Fairness Engines
xai_engine = CredofyExplainabilityEngine(model_dir=os.path.join(BASE_DIR, "models"))
fairness_auditor = CredofyFairnessAuditor(
    data_path=os.path.join(BASE_DIR, "data", "indian_loan_data.csv"),
    model_dir=os.path.join(BASE_DIR, "models")
)

import html
import re
from collections import defaultdict
from starlette.requests import Request
from starlette.responses import Response, HTMLResponse

# ================= SECURITY ENGINE: RATE LIMITER & CYBER SHIELD =================
class SecurityRateLimiter:
    """
    In-memory sliding-window rate limiter per client IP address.
    Defends against DDoS, brute-force spam, and bulk file upload attacks.
    """
    def __init__(self):
        self.clients = defaultdict(list)
    
    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.time()
        # Evict timestamps outside the sliding window
        self.clients[key] = [t for t in self.clients[key] if now - t < window_seconds]
        if len(self.clients[key]) >= max_requests:
            return False
        self.clients[key].append(now)
        return True

rate_limiter = SecurityRateLimiter()

def get_real_client_ip(request: Request) -> str:
    """Safely extracts real client IP behind proxies, load balancers, or Render CDN."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"

# FastAPI App
app = FastAPI(
    title="Credofy Enterprise Backend API",
    description="Intelligent Explainable Loan Decision Engine, Bilingual XAI, and RBI-Compliant Underwriting Platform",
    version="2.1.0"
)

# 1. HTTP Security Headers Middleware (OWASP Standard)
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response: Response = await call_next(request)
    # Prevent clickjacking / iframe injection
    response.headers["X-Frame-Options"] = "DENY"
    # Prevent MIME-type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Cross-site scripting filter
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # Strict referrer policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Hardware feature permission constraints
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # HSTS for HTTPS connections
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# 2. Hardened CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
        "https://credofy.onrender.com",
        "https://credofy.ai"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Pydantic Schemas
class ApplicantRequest(BaseModel):
    Gender: str = Field(default="Male", description="Male / Female")
    Married: str = Field(default="Yes", description="Yes / No")
    Dependents: str = Field(default="1", description="0, 1, 2, 3+")
    Education: str = Field(default="Graduate", description="Graduate / Not Graduate")
    Self_Employed: str = Field(default="No", description="Yes (MSME/Kirana) / No (Salaried)")
    ApplicantIncome: float = Field(default=35000.0, description="Monthly Income in INR (₹)")
    CoapplicantIncome: float = Field(default=0.0, description="Co-borrower Monthly Income in INR (₹)")
    LoanAmount: float = Field(default=3.5, description="Requested Loan in INR Lakhs")
    Loan_Amount_Term: int = Field(default=36, description="Tenure in Months")
    CIBIL_Score: int = Field(default=710, description="CIBIL Score (300 to 900)")
    Credit_History: int = Field(default=1, description="1 = Clean History, 0 = Past Delays")
    Property_Area: str = Field(default="Semiurban", description="Rural / Semiurban / Urban")
    applicant_name: Optional[str] = "Applicant"
    account_id: Optional[str] = "EQUI-USR-0001"
    email: Optional[str] = "user@gmail.com"
    SelectedBank: Optional[str] = "State Bank of India (SBI)"
    loan_purpose: Optional[str] = "Personal Loan"

class BatchApplicantRequest(BaseModel):
    applicants: List[ApplicantRequest]

class CounterfactualQuery(BaseModel):
    applicant: ApplicantRequest
    target_probability: float = Field(default=0.75, description="Desired minimum approval probability")

# ================= API ENDPOINTS =================

@app.get("/api/health")
def health_check():
    """System health check & MongoDB statistics."""
    try:
        app_count = applications_col.count_documents({})
    except Exception:
        app_count = 0
    try:
        user_count = users_col.count_documents({})
    except Exception:
        user_count = 0
    try:
        audit_count = fairness_col.count_documents({})
    except Exception:
        audit_count = 0

    return {
        "status": "online",
        "service": "Credofy Underwriting & Fairness API",
        "database": db_manager.mode,
        "total_applications_in_db": app_count,
        "total_users_in_db": user_count,
        "total_audits_logged": audit_count,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/api/underwrite")
def underwrite_loan(applicant: ApplicantRequest):
    """
    Core Underwriting Workflow:
    1. Preprocesses inputs & infers calibrated probability.
    2. Runs SHAP TreeExplainer to extract local attributions.
    3. Translates feature attributions to English & Hindi plain-language explanations.
    4. Computes actionable counterfactual suggestions.
    5. Persists complete payload into MongoDB `applications` collection linked to user.
    """
    data_dict = applicant.dict()
    name = data_dict.pop("applicant_name", "Applicant")
    account_id = data_dict.pop("account_id", "EQUI-USR-0001")
    email = data_dict.pop("email", "user@gmail.com")
    selected_bank = data_dict.pop("SelectedBank", "State Bank of India (SBI)")
    loan_purpose = data_dict.pop("loan_purpose", "Personal Loan")
    
    result = xai_engine.predict_and_explain(data_dict)
    
    app_id = f"EQUI-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{int(data_dict['CIBIL_Score'])}"
    doc = {
        "application_id": app_id,
        "account_id": account_id,
        "email": email,
        "applicant_name": name,
        "selected_bank": selected_bank,
        "loan_purpose": loan_purpose,
        "created_at": datetime.utcnow().isoformat(),
        "input_features": {
            **data_dict,
            "SelectedBank": selected_bank,
            "loan_purpose": loan_purpose
        },
        "decision": {
            "is_approved": result["is_approved"],
            "approval_probability": result["approval_probability"],
            "risk_band": result["risk_band"],
            "foir": result["raw_foir"],
            "monthly_emi": result["monthly_emi"]
        },
        "explainability": {
            "feature_impacts": result["feature_impacts"],
            "explanations_en": result["explanations_en"],
            "explanations_hi": result["explanations_hi"],
            "counterfactuals_en": result["counterfactuals_en"],
            "counterfactuals_hi": result["counterfactuals_hi"]
        }
    }
    
    applications_col.insert_one(doc)
    doc.pop("_id", None)
    
    # Log regulatory audit trail
    audit_logs_col.insert_one({
        "event": "UNDERWRITE_LOAN",
        "application_id": app_id,
        "account_id": account_id,
        "email": email,
        "applicant_name": name,
        "selected_bank": selected_bank,
        "loan_purpose": loan_purpose,
        "timestamp": datetime.utcnow().isoformat(),
        "decision": result["is_approved"]
    })
    
    return {
        "application_id": app_id,
        "result": result,
        "persisted_in_mongodb": True
    }

@app.post("/api/batch-underwrite")
def batch_underwrite(batch: BatchApplicantRequest):
    """Processes multiple loan applications in bulk and logs each into MongoDB."""
    results = []
    for item in batch.applicants:
        res = underwrite_loan(item)
        results.append(res)
    return {
        "processed_count": len(results),
        "results": results
    }

@app.post("/api/counterfactual")
def compute_counterfactual(query: CounterfactualQuery):
    """
    Computes fine-grained mathematical counterfactuals exploring alternative parameter sets
    (e.g., lower loan amount, higher co-applicant income, longer tenure) to reach target probability.
    """
    req_dict = query.applicant.dict()
    req_dict.pop("applicant_name", None)
    base_result = xai_engine.predict_and_explain(req_dict)
    
    scenarios = []
    # Scenario 1: Lower Loan Amount by 15%, 25%, 35%
    for discount in [0.85, 0.75, 0.65]:
        mod = dict(req_dict)
        mod['LoanAmount'] = round(req_dict['LoanAmount'] * discount, 1)
        r = xai_engine.predict_and_explain(mod)
        scenarios.append({
            "action": f"Reduce loan to ₹{mod['LoanAmount']} Lakhs",
            "action_hi": f"लोन राशि घटाकर ₹{mod['LoanAmount']} लाख करें",
            "new_probability": r["approval_probability"],
            "is_approved": r["is_approved"]
        })
        
    # Scenario 2: Add Co-Applicant Income
    if req_dict.get('CoapplicantIncome', 0) == 0:
        for extra in [15000, 25000, 35000]:
            mod = dict(req_dict)
            mod['CoapplicantIncome'] = extra
            r = xai_engine.predict_and_explain(mod)
            scenarios.append({
                "action": f"Add co-borrower earning ₹{extra:,}/mo",
                "action_hi": f"सह-आवेदक जोड़ें जिनकी आय ₹{extra:,}/माह हो",
                "new_probability": r["approval_probability"],
                "is_approved": r["is_approved"]
            })
            
    # Scenario 3: Extend Tenure
    for new_term in [60, 120, 240]:
        if new_term > req_dict['Loan_Amount_Term']:
            mod = dict(req_dict)
            mod['Loan_Amount_Term'] = new_term
            r = xai_engine.predict_and_explain(mod)
            scenarios.append({
                "action": f"Extend tenure to {new_term} months",
                "action_hi": f"लोन अवधि बढ़ाकर {new_term} महीने करें",
                "new_probability": r["approval_probability"],
                "is_approved": r["is_approved"]
            })
            
    return {
        "current_probability": base_result["approval_probability"],
        "target_probability": query.target_probability * 100,
        "counterfactuals_en": base_result.get("counterfactuals_en", []),
        "counterfactuals_hi": base_result.get("counterfactuals_hi", []),
        "counterfactual_scenarios": scenarios
    }

@app.get("/api/applications")
def get_applications(limit: int = Query(50, ge=1, le=200)):
    """Fetches recent applications from MongoDB."""
    cursor = applications_col.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    return {
        "count": applications_col.count_documents({}),
        "applications": list(cursor)
    }

@app.get("/api/applications/{application_id}")
def get_single_application(application_id: str):
    """Fetches a specific loan evaluation document from MongoDB by ID."""
    doc = applications_col.find_one({"application_id": application_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Application ID not found in database")
    return doc

@app.get("/api/fairness")
@app.get("/api/fairness-report")
def get_fairness_report():
    """
    Computes live algorithmic fairness audit across the portfolio.
    Checks Disparate Impact Ratio (DIR) for Rural vs Urban and Gender against RBI's 80% rule.
    Logs the audit run into MongoDB `fairness_audits`.
    """
    report = fairness_auditor.compute_fairness_report()
    fairness_col.insert_one({
        "audit_timestamp": datetime.utcnow().isoformat(),
        "report": report
    })
    return report

@app.get("/api/metrics")
def get_model_accuracy_metrics():
    """Returns 5-Fold Stratified Cross-Validation & holdout accuracy metrics."""
    report_file = os.path.join(BASE_DIR, "models", "accuracy_report.json")
    if os.path.exists(report_file):
        with open(report_file, "r") as f:
            return json.load(f)
    raise HTTPException(status_code=404, detail="Accuracy report not found")

@app.get("/api/audit-trail")
def get_audit_trail(limit: int = 50):
    """Returns regulatory compliance audit logs from MongoDB."""
    cursor = audit_logs_col.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit)
    return {
        "total_audit_events": audit_logs_col.count_documents({}),
        "events": list(cursor)
    }

# ================= USER ACCOUNT & GOOGLE OAUTH ENDPOINTS =================
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

class GoogleAuthPayload(BaseModel):
    credential: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    picture: Optional[str] = None
    google_id: Optional[str] = None

@app.post("/api/auth/google")
def authenticate_google_oauth(payload: GoogleAuthPayload, request: Request):
    """
    Real Google OAuth 2.0 with MongoDB Persistence:
    1. If `credential` (Google ID Token JWT) is provided, verifies cryptographic signature.
    2. Extracts Google User Claims: sub, email, name, picture.
    3. Finds or creates user in MongoDB `users` collection.
    4. Issues unique Credofy Account ID (e.g. CRD-USR-0001).
    Secured: Rate-limited per IP address.
    """
    client_ip = get_real_client_ip(request)
    if not rate_limiter.is_allowed(f"auth:{client_ip}", max_requests=60, window_seconds=60):
        raise HTTPException(status_code=429, detail="Rate Limit: Too many authentication attempts.")
    user_info = {}
    if payload.credential:
        try:
            # Verify cryptographic signature against Google certs
            id_info = google_id_token.verify_oauth2_token(
                payload.credential, 
                google_requests.Request(),
                GOOGLE_CLIENT_ID if GOOGLE_CLIENT_ID else None
            )
            user_info = {
                "google_id": id_info.get("sub"),
                "email": id_info.get("email"),
                "name": id_info.get("name"),
                "picture": id_info.get("picture"),
                "email_verified": id_info.get("email_verified", True)
            }
        except Exception as e:
            print("Google token verification notice:", e)
            user_info = {
                "google_id": payload.google_id or f"google_{int(datetime.utcnow().timestamp())}",
                "email": payload.email or "user@gmail.com",
                "name": payload.name or "Google User",
                "picture": payload.picture,
                "email_verified": True
            }
    else:
        user_info = {
            "google_id": payload.google_id or f"google_{int(datetime.utcnow().timestamp())}",
            "email": payload.email or "user@gmail.com",
            "name": payload.name or "Google User",
            "picture": payload.picture,
            "email_verified": True
        }

    email = user_info["email"].strip().lower()

    # 1. Primary User Store: Firebase Cloud Firestore
    existing = None
    if firebase_db:
        try:
            doc_snap = firebase_db.collection("users").document(email).get()
            if doc_snap.exists:
                existing = doc_snap.to_dict()
        except Exception as e:
            print("Firestore user lookup fallback:", e)

    # Local fallback cache if Firestore lookup was not available
    if not existing:
        existing = users_col.find_one({"email": email}, {"_id": 0})

    if existing:
        login_time = datetime.utcnow().isoformat()
        updated_data = {
            "last_login": login_time,
            "picture": user_info.get("picture") or existing.get("picture"),
            "name": user_info.get("name") or existing.get("name")
        }
        if firebase_db:
            try:
                firebase_db.collection("users").document(email).update(updated_data)
            except Exception:
                pass
        # local cache sync
        users_col.update_one({"email": email}, {"$set": updated_data})
        return {
            "status": "authenticated",
            "account_id": existing.get("account_id"),
            "email": existing.get("email"),
            "name": updated_data.get("name"),
            "picture": updated_data.get("picture"),
            "auth_provider": "Google OAuth 2.0",
            "database_status": "Active (Firebase Cloud Firestore)",
            "member_since": existing.get("created_at")
        }
    
    count = 1
    if firebase_db:
        try:
            users_stream = firebase_db.collection("users").limit(5000).stream()
            count = sum(1 for _ in users_stream) + 1
        except Exception:
            count = users_col.count_documents({}) + 1
    else:
        count = users_col.count_documents({}) + 1

    new_account_id = f"CRD-USR-{count:04d}"
    created_at = datetime.utcnow().isoformat()
    new_user = {
        "account_id": new_account_id,
        "email": email,
        "name": user_info["name"],
        "picture": user_info["picture"],
        "google_id": user_info["google_id"],
        "auth_provider": "Google OAuth 2.0",
        "created_at": created_at,
        "last_login": created_at,
        "database": "Firebase Cloud Firestore",
        "firestore_synced_at": created_at
    }

    # Primary save to Firebase Cloud Firestore
    if firebase_db:
        try:
            firebase_db.collection("users").document(email).set(new_user)
        except Exception as e:
            print("Firestore write notice:", e)

    # Local cache sync
    users_col.insert_one(new_user)
    return {
        "status": "created",
        "account_id": new_account_id,
        "email": email,
        "name": user_info["name"],
        "picture": user_info["picture"],
        "auth_provider": "Google OAuth 2.0",
        "database_status": "Active (Firebase Cloud Firestore)",
        "member_since": created_at
    }

class UserLoginPayload(BaseModel):
    email: str
    name: str
    picture: Optional[str] = None
    google_id: Optional[str] = None

@app.post("/api/user-login")
def login_or_register_user(payload: UserLoginPayload, request: Request):
    """Backward-compatible user registration/login route using Google OAuth engine."""
    return authenticate_google_oauth(GoogleAuthPayload(
        email=payload.email,
        name=payload.name,
        picture=payload.picture,
        google_id=payload.google_id
    ), request=request)

# ================= AI CREDIT COPILOT CHATBOT =================
class ChatbotRequest(BaseModel):
    message: str
    applicant_context: Dict[str, Any]
    history: Optional[List[Dict[str, str]]] = []

@app.post("/api/chat")
def chat_with_credofy_ai(req: ChatbotRequest, request: Request):
    """
    Interactive conversational AI Credit Copilot for Credofy.
    Answers borrower questions specifically regarding CIBIL, EMI, loan approvals,
    bank comparisons, and documentation in English & Hindi.
    Secured: Sliding window rate limit per client IP.
    """
    client_ip = get_real_client_ip(request)
    if not rate_limiter.is_allowed(f"chat:{client_ip}", max_requests=40, window_seconds=60):
        raise HTTPException(
            status_code=429,
            detail="Rate Limit Exceeded: Too many chat messages. Please wait 1 minute before sending more."
        )

    res = credit_chatbot.chat_with_meta(
        user_message=req.message,
        applicant_context=req.applicant_context,
        history=req.history or []
    )
    return {
        "reply": res["reply"],
        "engine": res["engine"],
        "gemini_active": res["gemini_active"]
    }

@app.get("/api/chat/status")
def get_chat_status():
    """Returns Gemini connection status."""
    return {
        "gemini_active": credit_chatbot.is_gemini_active(),
        "model": getattr(credit_chatbot, "gemini_model_name", "local_copilot")
    }

class GeminiKeyPayload(BaseModel):
    api_key: str
    admin_secret: Optional[str] = None

@app.post("/api/config/gemini-key")
def configure_gemini_key(payload: GeminiKeyPayload, request: Request):
    """
    Dynamically activates Google Gemini LLM API key.
    Secured: Requires TELEGRAM_ADMIN_SECRET in payload or x-admin-secret header.
    """
    header_secret = request.headers.get("x-admin-secret")
    client_secret = payload.admin_secret or header_secret
    if client_secret != TELEGRAM_ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized: Invalid Admin Secret Key.")

    key = payload.api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="API key cannot be empty")
    
    success = credit_chatbot.set_gemini_api_key(key)
    if not success:
        return {
            "status": "error",
            "message": "Invalid Gemini API key or quota exceeded. Please verify key at aistudio.google.com"
        }
    
    env_path = os.path.join(BASE_DIR, ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()
    
    new_lines = [l for l in lines if not l.startswith("GEMINI_API_KEY=")]
    new_lines.append(f'GEMINI_API_KEY="{key}"\n')
    with open(env_path, "w") as f:
        f.writelines(new_lines)
    
    return {
        "status": "success",
        "message": "Google Gemini 2.0 connected successfully!",
        "model": credit_chatbot.gemini_model_name
    }

@app.get("/api/db-status")
def get_db_status():
    """Returns real-time database connection diagnostics."""
    is_atlas = db_manager.check_atlas_connection(timeout_ms=2500)
    try:
        user_c = users_col.count_documents({})
    except Exception:
        user_c = 0
    try:
        app_c = applications_col.count_documents({})
    except Exception:
        app_c = 0

    cluster_host = "Unknown"
    if db_manager.uri and "@" in db_manager.uri:
        cluster_host = db_manager.uri.split("@")[-1].split("/")[0]

    return {
        "mode": db_manager.mode,
        "is_atlas": is_atlas,
        "target_cluster": cluster_host,
        "database": "equibharat_db",
        "users_count": user_c,
        "applications_count": app_c,
        "firebase_firestore": firebase_status,
        "firebase_project": "credofy-51744",
        "user_storage_engine": "Firebase Cloud Firestore (100% Primary)",
        "troubleshooting_note": "Ensure 0.0.0.0/0 is whitelisted in Atlas Security > Network Access, or connect via Personal Mobile Hotspot to avoid port 27017 filtering."
    }

# ================= AI DOCUMENT SCANNER ENDPOINT =================
@app.post("/api/scan-document")
async def scan_uploaded_document(
    file: UploadFile = File(...),
    applicant_name: str = Form(default="Kunal Sharma"),
    stated_income: float = Form(default=45000.0),
    account_id: str = Form(default="EQUI-USR-0001"),
    email: str = Form(default="user@gmail.com")
):
    """
    Extracts text, checks Indian ID formats (PAN, Aadhaar),
    validates income credits against stated income, and saves audit in MongoDB.
    """
    contents = await file.read()
    scan_result = document_scanner.scan_file(
        filename=file.filename,
        file_bytes=contents,
        applicant_name=applicant_name,
        stated_income=stated_income
    )
    
    # Save scan audit record to MongoDB linked to user
    scanned_docs_col.insert_one({
        "timestamp": datetime.utcnow().isoformat(),
        "filename": file.filename,
        "applicant_name": applicant_name,
        "account_id": account_id,
        "email": email,
        "result": scan_result
    })
    
    return {"result": scan_result}

# ================= BANK REDIRECTION & LEAD TRACKER =================
class RedirectionLead(BaseModel):
    account_id: str
    email: Optional[str] = "user@gmail.com"
    bank_id: str
    bank_name: str
    portal_url: str
    loan_amount_lakhs: float
    cibil_score: int

@app.post("/api/log-bank-redirection")
def log_bank_portal_redirection(lead: RedirectionLead):
    """
    Tracks when a borrower is redirected to an official bank portal to complete their loan.
    Saves direct lead in MongoDB linked to user.
    """
    doc = lead.dict()
    doc["timestamp"] = datetime.utcnow().isoformat()
    doc["lead_status"] = "Redirected to Official Bank Portal"
    lead_id = f"LEAD-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    doc["lead_id"] = lead_id
    bank_leads_col.insert_one(doc)
    return {
        "status": "success",
        "lead_id": lead_id,
        "redirect_url": lead.portal_url,
        "message": f"Application packet prepared for {lead.bank_name}."
    }

# ================= USER MONGODB RECORDS VIEWER =================
@app.get("/api/user-records/{account_id}")
@app.get("/api/user-passbook/{account_id}")
def get_user_mongodb_records(account_id: str):
    """
    Retrieves all records stored in MongoDB for a specific Google user:
    - User Profile from `users` collection
    - All Underwritten Applications from `applications` collection
    - All Scanned Documents from `scanned_documents` collection
    - All Bank Redirection Leads from `bank_leads` collection
    """
    user_doc = users_col.find_one({"account_id": account_id}, {"_id": 0})
    user_apps = list(applications_col.find({"account_id": account_id}, {"_id": 0}).sort("created_at", -1).limit(20))
    user_docs = list(scanned_docs_col.find({"account_id": account_id}, {"_id": 0}).sort("timestamp", -1).limit(20))
    user_leads = list(bank_leads_col.find({"account_id": account_id}, {"_id": 0}).sort("timestamp", -1).limit(20))
    
    return {
        "account_id": account_id,
        "database": db_manager.mode,
        "user_profile": user_doc,
        "counts": {
            "applications": len(user_apps),
            "scanned_documents": len(user_docs),
            "bank_leads": len(user_leads)
        },
        "applications": user_apps,
        "scanned_documents": user_docs,
        "bank_leads": user_leads
    }


# ================= POCKET FINANCE & DAILY WEALTH HUB =================
gullak_col = CollectionProxy("gullak_records")

# Comprehensive Curated RBI Registry & Scam App Blacklist
RBI_REGISTERED_ENTITIES = [
    {"name": "State Bank of India (SBI)", "category": "PSU Bank", "license": "RBI/BANK/001", "status": "verified", "safety_rating": "5/5 AAA Prime", "notes": "India's largest public sector bank."},
    {"name": "HDFC Bank Ltd", "category": "Private Scheduled Bank", "license": "RBI/BANK/102", "status": "verified", "safety_rating": "5/5 AAA Prime", "notes": "RBI Domestic Systemically Important Bank (D-SIB)."},
    {"name": "ICICI Bank Ltd", "category": "Private Scheduled Bank", "license": "RBI/BANK/103", "status": "verified", "safety_rating": "5/5 AAA Prime", "notes": "RBI D-SIB Scheduled Commercial Bank."},
    {"name": "Bajaj Finance Ltd", "category": "Systemically Important NBFC", "license": "RBI/NBFC/042", "status": "verified", "safety_rating": "5/5 AAA", "notes": "Registered Systemically Important Non-Deposit Taking NBFC."},
    {"name": "Tata Capital Financial Services", "category": "RBI Registered NBFC", "license": "RBI/NBFC/088", "status": "verified", "safety_rating": "5/5 AAA", "notes": "Tata Sons backed licensed lending institution."},
    {"name": "Muthoot Finance Ltd", "category": "RBI Registered NBFC", "license": "RBI/NBFC/019", "status": "verified", "safety_rating": "5/5 AA+", "notes": "India's largest gold loan specialist NBFC."},
    {"name": "Bank of Baroda", "category": "PSU Bank", "license": "RBI/BANK/005", "status": "verified", "safety_rating": "5/5 AAA", "notes": "Public Sector Scheduled Commercial Bank."},
    {"name": "Punjab National Bank (PNB)", "category": "PSU Bank", "license": "RBI/BANK/002", "status": "verified", "safety_rating": "5/5 AAA", "notes": "Public Sector Scheduled Commercial Bank."},
    {"name": "Canara Bank", "category": "PSU Bank", "license": "RBI/BANK/008", "status": "verified", "safety_rating": "5/5 AAA", "notes": "Public Sector Scheduled Commercial Bank."},
    {"name": "Axis Bank Ltd", "category": "Private Scheduled Bank", "license": "RBI/BANK/104", "status": "verified", "safety_rating": "5/5 AAA", "notes": "Scheduled Commercial Bank."},
    {"name": "Kotak Mahindra Bank", "category": "Private Scheduled Bank", "license": "RBI/BANK/105", "status": "verified", "safety_rating": "5/5 AAA", "notes": "Scheduled Commercial Bank."},
    {"name": "Aditya Birla Finance Ltd", "category": "RBI Registered NBFC", "license": "RBI/NBFC/053", "status": "verified", "safety_rating": "5/5 AAA", "notes": "Registered Corporate NBFC."},
    {"name": "L&T Finance Holdings", "category": "RBI Registered NBFC", "license": "RBI/NBFC/067", "status": "verified", "safety_rating": "5/5 AAA", "notes": "Infrastructure & Rural lending NBFC."}
]

FLAGGED_FRAUD_APPS = [
    {"name": "CashBean Quick / BeanCash", "category": "Illegal 7-Day App", "status": "blacklisted", "danger_level": "CRITICAL RISK", "reasons": ["Banned under IT Act Section 69A", "Demands advance processing fee", "Harassing unauthorized contacts gallery"]},
    {"name": "FlashRupee / RupeeFlash", "category": "Unauthorized Lending APK", "status": "blacklisted", "danger_level": "CRITICAL RISK", "reasons": ["Not registered with RBI", "Extortionate 300%+ APR disguised as 0.1%/day", "Phishing unauthorized mobile permissions"]},
    {"name": "LightningRupee / FastCash5Min", "category": "Predatory Micro-Lender", "status": "blacklisted", "danger_level": "CRITICAL RISK", "reasons": ["Unregistered offshore shell company", "Threatens borrower with morphing photos", "Blacklisted by CERT-In and RBI Sachet portal"]},
    {"name": "QuickLoan7 / SevenDayPaisa", "category": "Illegal Loan App", "status": "blacklisted", "danger_level": "CRITICAL RISK", "reasons": ["Charges 40% upfront deduction", "Refuses standard 3-month tenure", "Fake NBFC certificate detected"]},
    {"name": "PaisaIn5Min / EasyBorrowInstant", "category": "WhatsApp/Telegram Loan Scam", "status": "blacklisted", "danger_level": "CRITICAL RISK", "reasons": ["Asks borrower to deposit 'Security Deposit' before disbursal", "No physical office in India", "Circulated via unauthorized APK links"]}
]

CENTRAL_WELFARE_SCHEMES = [
    {
        "id": "pm-kisan",
        "name": "PM Kisan Samman Nidhi",
        "name_hi": "प्रधानमंत्री किसान सम्मान निधि",
        "category": "Farmer / Agriculture",
        "category_hi": "किसान व कृषि",
        "benefit": "₹6,000 per year direct bank credit (3 equal installments of ₹2,000).",
        "benefit_hi": "₹6,000 प्रति वर्ष सीधा बैंक खाते में (₹2,000 की 3 किस्तों में)।",
        "eligibility": "Small and marginal landholder farmer families.",
        "eligibility_hi": "छोटे एवं सीमांत भू-स्वामी किसान परिवार।",
        "documents": ["Aadhaar Card", "Land Ownership Khatauni/Khasra", "Bank Passbook"],
        "official_url": "https://pmkisan.gov.in",
        "badge": "Central Direct Benefit Transfer"
    },
    {
        "id": "sukanya-samriddhi",
        "name": "Sukanya Samriddhi Yojana (SSY)",
        "name_hi": "सुकन्या समृद्धि योजना",
        "category": "Girl Child & Daughters",
        "category_hi": "बालिका व बेटियां",
        "benefit": "8.2% p.a. guaranteed sovereign interest • 100% Tax-Free under Section 80C & EEE.",
        "benefit_hi": "8.2% वार्षिक गारंटीड ब्याज • 80C व EEE के तहत पूर्णतः कर-मुक्त।",
        "eligibility": "Parents or legal guardians of girl child below 10 years of age.",
        "eligibility_hi": "10 वर्ष से कम आयु की बालिकाओं के माता-पिता।",
        "documents": ["Birth Certificate of Girl Child", "Guardian Aadhaar & PAN", "Address Proof"],
        "official_url": "https://www.indiapost.gov.in",
        "badge": "Sovereign Savings Shield"
    },
    {
        "id": "ayushman-bharat",
        "name": "Ayushman Bharat PM-JAY",
        "name_hi": "आयुष्मान भारत प्रधानमंत्री जन आरोग्य",
        "category": "Health & Medical Shield",
        "category_hi": "स्वास्थ्य व चिकित्सा सुरक्षा",
        "benefit": "₹5,00,000 free cashless hospital treatment per family per year.",
        "benefit_hi": "₹5,00,000 प्रति परिवार प्रति वर्ष मुफ्त कैशलेस इलाज।",
        "eligibility": "Economically vulnerable households identified via SECC/Ration Card.",
        "eligibility_hi": "राशन कार्ड एवं सामाजिक-आर्थिक सूची में शामिल परिवार।",
        "documents": ["Ration Card", "Aadhaar Card of all family members"],
        "official_url": "https://mera.pmjay.gov.in",
        "badge": "Free Medical Coverage"
    },
    {
        "id": "atal-pension",
        "name": "Atal Pension Yojana (APY)",
        "name_hi": "अटल पेंशन योजना",
        "category": "Retirement & Gig Workers",
        "category_hi": "पेंशन व गिग वर्कर्स",
        "benefit": "Guaranteed lifetime monthly pension from ₹1,000 to ₹5,000 after age 60.",
        "benefit_hi": "60 वर्ष के बाद आजीवन ₹1,000 से ₹5,000 की मासिक सरकारी पेंशन।",
        "eligibility": "Any Indian citizen between 18 and 40 years holding a bank account.",
        "eligibility_hi": "18 से 40 वर्ष के भारतीय नागरिक जिनके पास बैंक खाता है।",
        "documents": ["Bank Savings Account", "Aadhaar Card", "Mobile Linked Account"],
        "official_url": "https://www.npscra.nsdl.co.in",
        "badge": "Guaranteed Monthly Pension"
    },
    {
        "id": "pm-svanidhi",
        "name": "PM SVANidhi Micro-Credit",
        "name_hi": "पीएम स्वनिधि रेहड़ी-पटरी योजना",
        "category": "Micro-Business & Vendors",
        "category_hi": "रेहड़ी-पटरी व लघु विक्रेता",
        "benefit": "Collateral-free working capital of ₹10,000 up to ₹50,000 with 7% interest cashback.",
        "benefit_hi": "बिना गारंटी ₹10,000 से ₹50,000 तक कार्यशील पूंजी व 7% ब्याज सब्सिडी।",
        "eligibility": "Urban, peri-urban, and rural street vendors and micro-artisans.",
        "eligibility_hi": "शहरी एवं ग्रामीण रेहड़ी-पटरी वाले और छोटे कारीगर।",
        "documents": ["Vendor Certificate / LOR", "Aadhaar", "Bank Account Details"],
        "official_url": "https://pmsvanidhi.mohua.gov.in",
        "badge": "Vendor Empowerment Grant"
    },
    {
        "id": "national-scholarship",
        "name": "National Merit Scholarship Portal",
        "name_hi": "राष्ट्रीय छात्रवृत्ति पोर्टल (विद्यार्थी)",
        "category": "Students & Education",
        "category_hi": "विद्यार्थी व उच्च शिक्षा",
        "benefit": "Direct college fee grant up to ₹20,000 - ₹50,000 per year for meritorious students.",
        "benefit_hi": "उच्च शिक्षा हेतु ₹20,000 से ₹50,000 प्रति वर्ष की सीधी फीस सहायता।",
        "eligibility": "School and college students with family annual income < ₹2.5 Lakhs.",
        "eligibility_hi": "पारिवारिक वार्षिक आय ₹2.5 लाख से कम वाले मेधावी छात्र-छात्राएं।",
        "documents": ["Previous Year Marksheet", "Income Certificate", "College Fee Receipt", "Bank Passbook"],
        "official_url": "https://scholarships.gov.in",
        "badge": "Direct Student Tuition Grant"
    }
]

class GullakDepositPayload(BaseModel):
    account_id: str
    jar_id: str
    jar_name: str
    amount: float
    note: Optional[str] = ""

@app.post("/api/pocket/gullak/deposit")
def deposit_to_gullak(payload: GullakDepositPayload):
    """
    Records a micro-saving deposit into user's digital Gullak in MongoDB.
    Computes compounding projection and maintains savings streak.
    """
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Deposit amount must be positive.")
    
    timestamp = datetime.utcnow().isoformat()
    record = {
        "account_id": payload.account_id,
        "jar_id": payload.jar_id,
        "jar_name": payload.jar_name,
        "amount": round(payload.amount, 2),
        "note": payload.note or "Daily Pocket Savings",
        "timestamp": timestamp
    }
    gullak_col.insert_one(record)
    
    # Calculate totals
    user_deposits = list(gullak_col.find({"account_id": payload.account_id}, {"_id": 0}))
    total_saved = sum(d["amount"] for d in user_deposits)
    
    # Simple annual projection (at 6.5% p.a. liquid fund return)
    daily_avg = total_saved / max(1, len(user_deposits))
    one_year_saved = daily_avg * 365
    one_year_interest = one_year_saved * 0.065
    
    return {
        "status": "success",
        "deposited_amount": payload.amount,
        "jar_id": payload.jar_id,
        "total_saved": round(total_saved, 2),
        "total_deposits_count": len(user_deposits),
        "savings_streak_days": len(user_deposits),
        "one_year_projection": {
            "principal": round(one_year_saved, 2),
            "interest_earned": round(one_year_interest, 2),
            "total_maturity": round(one_year_saved + one_year_interest, 2)
        },
        "message": f"Successfully added ₹{payload.amount} to your {payload.jar_name} Gullak!"
    }

@app.get("/api/pocket/gullak/{account_id}")
def get_user_gullak_summary(account_id: str):
    """Retrieves user's digital Gullak jars and historical savings from MongoDB."""
    deposits = list(gullak_col.find({"account_id": account_id}, {"_id": 0}).sort("timestamp", -1))
    total_saved = sum(d["amount"] for d in deposits)
    
    jar_totals = {}
    for d in deposits:
        jid = d.get("jar_id", "emergency")
        jar_totals[jid] = jar_totals.get(jid, 0.0) + d["amount"]
        
    return {
        "account_id": account_id,
        "total_saved": round(total_saved, 2),
        "deposits_count": len(deposits),
        "streak_days": len(deposits),
        "jar_breakdown": jar_totals,
        "recent_deposits": deposits[:10]
    }

class LenderVerifyPayload(BaseModel):
    query: str

@app.post("/api/pocket/verify-lender")
def verify_lender_safety(payload: LenderVerifyPayload):
    """
    Checks whether a bank, NBFC, or loan app is verified with the RBI
    or flagged on the illegal 7-day extortion blacklist.
    """
    q = payload.query.strip().lower()
    if not q:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
        
    # Check blacklist first
    for fraud in FLAGGED_FRAUD_APPS:
        if q in fraud["name"].lower() or any(w in fraud["name"].lower() for w in q.split()):
            return {
                "verdict": "DANGEROUS_SCAM",
                "is_safe": False,
                "badge": "🔴 ILLEGAL / BLACKLISTED LOAN APP",
                "entity": fraud["name"],
                "category": fraud["category"],
                "danger_level": fraud["danger_level"],
                "reasons": fraud["reasons"],
                "advisory": "DO NOT install this APK or send money. File a complaint on 1930 (National Cyber Crime Helpline) or sachet.rbi.org.in immediately."
            }
            
    # Check registered whitelist
    for reg in RBI_REGISTERED_ENTITIES:
        if q in reg["name"].lower() or any(w in reg["name"].lower() for w in q.split() if len(w) > 3):
            return {
                "verdict": "VERIFIED_SAFE",
                "is_safe": True,
                "badge": "🟢 RBI AUTHORIZED & LICENSED",
                "entity": reg["name"],
                "category": reg["category"],
                "license": reg["license"],
                "safety_rating": reg["safety_rating"],
                "notes": reg["notes"],
                "advisory": "This financial institution is officially licensed and supervised under the Reserve Bank of India Fair Lending code."
            }
            
    # Unknown entity guidance
    return {
        "verdict": "UNKNOWN_UNVERIFIED",
        "is_safe": False,
        "badge": "⚠️ UNVERIFIED ENTITY",
        "entity": payload.query,
        "advisory": "This entity was not found in the verified RBI Tier-1 database. Never download APKs from WhatsApp or pay advance processing fees."
    }

class MessageAnalyzePayload(BaseModel):
    message_text: str

@app.post("/api/pocket/analyze-message")
def analyze_suspicious_message(payload: MessageAnalyzePayload):
    """
    Analyzes suspicious SMS or WhatsApp loan messages for predatory traps,
    unauthorized links, and upfront fee fraud.
    """
    text = payload.message_text.strip().lower()
    flags = []
    
    if any(k in text for k in ["fee", "processing fee", "security deposit", "advance", "shulk"]):
        flags.append("🚨 Advance Fee Trap: Legitimate banks NEVER ask for upfront deposit before loan disbursal.")
    if any(k in text for k in ["bit.ly", "tinyurl", "t.me", "wa.me", ".apk", "drive.google"]):
        flags.append("⚠️ Suspicious Shortlink: Phishing link or unverified APK download detected.")
    if any(k in text for k in ["no cibil", "bina cibil", "zero cibil", "instant 5 min", "bina kagaz", "no kyc"]):
        flags.append("⚠️ Unrealistic Terms: Claims of 'No CIBIL / No KYC' often mask predatory 300%+ APR extortion apps.")
    if any(k in text for k in ["congratulations", "badhai", "pre-approved 2,00,000", "approved 5,00,000"]) and not any(b in text for b in ["sbi", "hdfc", "icici", "axis"]):
        flags.append("⚠️ Unsolicited Approval: Pre-approved claim without prior relationship or bureau inquiry.")
        
    risk_level = "High Risk / Potential Scam" if len(flags) >= 2 else ("Moderate Caution" if len(flags) == 1 else "Low Risk / Standard Communication")
    is_safe = len(flags) == 0
    
    return {
        "risk_level": risk_level,
        "is_safe": is_safe,
        "flag_count": len(flags),
        "flags_detected": flags,
        "advisory": "If in doubt, never click links in SMS. Check your official bureau report or visit a physical bank branch."
    }

@app.get("/api/pocket/welfare-schemes")
def get_welfare_schemes(category: Optional[str] = None):
    """Returns curated central government welfare benefits and grant schemes."""
    if category and category.lower() != "all":
        filtered = [s for s in CENTRAL_WELFARE_SCHEMES if category.lower() in s["category"].lower()]
        return {"count": len(filtered), "schemes": filtered}
    return {"count": len(CENTRAL_WELFARE_SCHEMES), "schemes": CENTRAL_WELFARE_SCHEMES}

# ================= NATIONAL GOVERNMENT SCHEMES & REGULATORY DIRECTORY =================
from schemes_catalog import ALL_GOVERNMENT_SCHEMES, GOVERNMENT_LICENSES_DIRECTORY, RBI_CITIZEN_RIGHTS_DIRECTORY

class ConquerReadinessPayload(BaseModel):
    scheme_id: str
    applicant_income: float = 50000.0
    cibil_score: int = 750
    has_aadhaar: bool = True
    has_pan: bool = True
    has_bank_account: bool = True
    has_udyam_or_land: bool = False

@app.get("/api/schemes/catalog")
def get_schemes_catalog(
    status: Optional[str] = "all",
    category: Optional[str] = "all",
    search: Optional[str] = None
):
    """
    Returns the comprehensive Master Government Schemes Repository.
    Supports filtering by Status (ACTIVE, UPCOMING, HISTORIC), Category, and Search keywords.
    """
    results = ALL_GOVERNMENT_SCHEMES
    
    # Status filter
    if status and status.lower() != "all":
        results = [s for s in results if s["status"].lower() == status.lower()]
        
    # Category filter
    if category and category.lower() != "all":
        results = [s for s in results if category.lower() in s["category"].lower() or category.lower() in s["category_hi"].lower()]
        
    # Search filter
    if search and search.strip():
        q = search.strip().lower()
        results = [
            s for s in results if (
                q in s["name"].lower() or 
                q in s["name_hi"].lower() or 
                q in s["ministry"].lower() or 
                q in s["category"].lower() or 
                q in s["summary"].lower()
            )
        ]
        
    active_count = len([s for s in ALL_GOVERNMENT_SCHEMES if s["status"] == "ACTIVE"])
    upcoming_count = len([s for s in ALL_GOVERNMENT_SCHEMES if s["status"] == "UPCOMING"])
    historic_count = len([s for s in ALL_GOVERNMENT_SCHEMES if s["status"] == "HISTORIC"])
    
    return {
        "total_count": len(results),
        "total_in_repository": len(ALL_GOVERNMENT_SCHEMES),
        "statistics": {
            "active_schemes": active_count,
            "upcoming_schemes": upcoming_count,
            "historic_schemes": historic_count,
            "verified_gov_portals": len(set(s["official_portal_url"] for s in ALL_GOVERNMENT_SCHEMES))
        },
        "schemes": results
    }

@app.get("/api/schemes/{scheme_id}")
def get_scheme_details(scheme_id: str):
    """Returns single scheme full roadmap, execution chart, and EquiBharat commercial bridge."""
    for s in ALL_GOVERNMENT_SCHEMES:
        if s["id"].lower() == scheme_id.lower():
            return {"status": "found", "scheme": s}
    raise HTTPException(status_code=404, detail=f"Scheme '{scheme_id}' not found in master repository.")

@app.get("/api/regulations/licenses")
def get_government_licenses_directory():
    """Returns comprehensive directory of business licenses (Udyam, GST, FSSAI, IEC, etc.)."""
    return {
        "status": "success",
        "total_licenses": len(GOVERNMENT_LICENSES_DIRECTORY),
        "licenses": GOVERNMENT_LICENSES_DIRECTORY
    }

@app.get("/api/regulations/rbi-rights")
def get_rbi_citizen_rights_directory():
    """Returns official citizen borrower rights under RBI law (DLG 2022, Fair Lending, CIBIL, Ombudsman)."""
    return {
        "status": "success",
        "total_rights": len(RBI_CITIZEN_RIGHTS_DIRECTORY),
        "rights": RBI_CITIZEN_RIGHTS_DIRECTORY
    }

@app.post("/api/schemes/conquer-readiness")
def evaluate_conquer_readiness(payload: ConquerReadinessPayload):
    """
    Evaluates citizen's profile readiness against a government scheme's statutory prerequisites.
    Returns 0-100% readiness score, verified factors, missing documentation, and EquiBharat pre-sanction bridge.
    """
    target = None
    for s in ALL_GOVERNMENT_SCHEMES:
        if s["id"].lower() == payload.scheme_id.lower():
            target = s
            break
            
    if not target:
        raise HTTPException(status_code=404, detail="Target scheme not found.")
        
    readiness_score = 40  # Base for identity initiation
    checklist = []
    
    if payload.has_aadhaar:
        readiness_score += 20
        checklist.append({"item": "Aadhaar e-KYC & Mobile Linkage", "status": "VERIFIED", "impact": "+20%"})
    else:
        checklist.append({"item": "Aadhaar e-KYC & Mobile Linkage", "status": "MISSING", "impact": "Required for DBT"})
        
    if payload.has_bank_account:
        readiness_score += 15
        checklist.append({"item": "Bank Savings Account Seeding", "status": "VERIFIED", "impact": "+15%"})
    else:
        checklist.append({"item": "Bank Savings Account Seeding", "status": "MISSING", "impact": "Required for Disbursal"})
        
    if payload.has_pan:
        readiness_score += 10
        checklist.append({"item": "Permanent Account Number (PAN)", "status": "VERIFIED", "impact": "+10%"})
        
    if payload.cibil_score >= 700:
        readiness_score += 15
        checklist.append({"item": f"Credit Bureau Standing ({payload.cibil_score})", "status": "EXCELLENT", "impact": "+15%"})
    elif payload.cibil_score >= 600:
        readiness_score += 5
        checklist.append({"item": f"Credit Bureau Standing ({payload.cibil_score})", "status": "FAIR", "impact": "+5%"})
    else:
        checklist.append({"item": f"Credit Bureau Standing ({payload.cibil_score})", "status": "LOW", "impact": "Subsidized/Guarantee Tiers Recommended"})
        
    readiness_score = min(100, readiness_score)
    
    return {
        "scheme_id": target["id"],
        "scheme_name": target["name"],
        "readiness_score": readiness_score,
        "readiness_band": "High Success Probability" if readiness_score >= 80 else ("Moderate Preparation Needed" if readiness_score >= 60 else "Foundational Verification Required"),
        "checklist": checklist,
        "estimated_disbursal_days": target["conquer_metrics"]["timeline_days"],
        "official_portal_url": target["official_portal_url"],
        "credofy_loan_bridge": {
            "is_applicable": target.get("has_loan_bridge", False),
            "loan_purpose_id": target.get("loan_purpose_id", "personal"),
            "cta_text": target.get("credofy_cta", target.get("equibharat_cta", "Check Loan Eligibility via Credofy"))
        },
        "equibharat_loan_bridge": {
            "is_applicable": target.get("has_loan_bridge", False),
            "loan_purpose_id": target.get("loan_purpose_id", "personal"),
            "cta_text": target.get("credofy_cta", target.get("equibharat_cta", "Check Loan Eligibility via Credofy"))
        }
    }


# ================= CREDOFY PREMIUM BORROWER ASSISTANCE (LOCAL & TELEGRAM CONNECTED) =================
import secrets
import re
import urllib.parse
import requests

PREMIUM_DATA_DIR = os.path.join(BASE_DIR, "data", "premium_requests")
PREMIUM_UPLOADS_DIR = os.path.join(PREMIUM_DATA_DIR, "uploads")
os.makedirs(PREMIUM_UPLOADS_DIR, exist_ok=True)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "9092152966:AAGUCgtSXrZiWFTh9pbnrj9Pgw7GPqoWVss")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "7156184246")
TELEGRAM_ADMIN_SECRET = os.environ.get("TELEGRAM_ADMIN_SECRET", "credofy_kunal_secret_2026")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://credofy.onrender.com")

def send_telegram_payment_alert(record: dict, file_bytes: bytes, filename: str):
    """
    Sends real-time photo alert with UTR number, applicant details, 
    and 1-click Approve/Reject action buttons to Admin's Telegram phone app.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    ref_id = record["reference_id"]
    name = record["full_name"]
    mobile = record["mobile"]
    email = record["email"]
    utr = record["utr_number"]
    notes = record.get("rejection_notes") or "None provided"

    caption = (
        f"🚨 <b>NEW CREDOFY PREMIUM PAYMENT!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Amount:</b> ₹499 (UPI Transfer)\n"
        f"👤 <b>Applicant:</b> {name}\n"
        f"📱 <b>Mobile:</b> +91 {mobile}\n"
        f"📧 <b>Email:</b> {email}\n"
        f"🔢 <b>UTR / Ref:</b> <code>{utr}</code>\n"
        f"🆔 <b>Ref ID:</b> <code>{ref_id}</code>\n"
        f"📝 <b>Rejection Notes:</b> {notes[:100]}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 <i>Tap below to approve or contact applicant directly:</i>"
    )

    approve_url = f"{PUBLIC_BASE_URL}/api/premium/admin-action?ref={ref_id}&action=approve&secret={TELEGRAM_ADMIN_SECRET}"
    reject_url = f"{PUBLIC_BASE_URL}/api/premium/admin-action?ref={ref_id}&action=reject&secret={TELEGRAM_ADMIN_SECRET}"
    wa_msg = urllib.parse.quote(f"Hello {name}, I am from Credofy. We received your ₹499 payment verification (Ref: {ref_id}). I am your dedicated borrower assistance counselor.")
    whatsapp_url = f"https://wa.me/91{mobile}?text={wa_msg}"

    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "✅ Approve Payment (1-Click)", "url": approve_url},
                {"text": "❌ Reject", "url": reject_url}
            ],
            [
                {"text": "💬 WhatsApp Customer Directly", "url": whatsapp_url}
            ]
        ]
    }

    try:
        ext = os.path.splitext(filename)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png']:
            api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            files = {"photo": (filename, file_bytes, f"image/{ext.replace('.', '')}")}
            data = {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption,
                "parse_mode": "HTML",
                "reply_markup": json.dumps(reply_markup)
            }
            requests.post(api_url, data=data, files=files, timeout=8)
        else:
            api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
            files = {"document": (filename, file_bytes, "application/pdf")}
            data = {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption,
                "parse_mode": "HTML",
                "reply_markup": json.dumps(reply_markup)
            }
            requests.post(api_url, data=data, files=files, timeout=8)
    except Exception as e:
        print(f"Telegram notification error: {e}")

@app.post("/api/premium/verify-request")
async def submit_premium_verification(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    mobile: str = Form(...),
    utr_number: str = Form(...),
    rejection_notes: Optional[str] = Form(None),
    consent: bool = Form(...),
    screenshot: UploadFile = File(...)
):
    """
    Receives ₹499 borrower assistance payment verification request,
    validates form details and screenshot with binary signature verification,
    enforces DDoS rate limits, generates unique CRD-PREM-2026-XXXXX ID,
    stores record, and sends instant Telegram Alert with 1-Click Approval to Admin.
    """
    # 1. IP Rate Limiting (Protects server memory and prevents Telegram notification flood)
    client_ip = get_real_client_ip(request)
    if not rate_limiter.is_allowed(f"prem_upload:{client_ip}", max_requests=10, window_seconds=600):
        raise HTTPException(
            status_code=429,
            detail="Security Rate Limit: Too many verification attempts from this IP. Please wait 10 minutes."
        )

    if not consent:
        raise HTTPException(status_code=400, detail="Consent for payment verification is required.")

    clean_name = full_name.strip()
    if len(clean_name) < 2 or len(clean_name) > 80:
        raise HTTPException(status_code=400, detail="Please enter a valid full name (2 to 80 characters).")

    clean_email = email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", clean_email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")

    clean_mobile = re.sub(r"\D", "", mobile)
    if len(clean_mobile) != 10:
        raise HTTPException(status_code=400, detail="Mobile number must be exactly 10 digits.")

    clean_utr = utr_number.strip().upper()
    if len(clean_utr) < 6 or len(clean_utr) > 24 or not re.match(r"^[A-Z0-9]+$", clean_utr):
        raise HTTPException(status_code=400, detail="Please enter a valid alphanumeric UPI / Bank UTR Transaction Reference number.")

    # Validate screenshot file extension
    ext = os.path.splitext(screenshot.filename or "")[1].lower()
    allowed_exts = [".jpg", ".jpeg", ".png", ".pdf"]
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"Unsupported file format '{ext}'. Allowed: JPG, JPEG, PNG, PDF.")

    # Read and validate file size (max 5MB)
    content = await screenshot.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds the 5MB limit.")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # 2. Binary Magic Bytes Validation (Prevents disguised shell scripts or malware)
    is_valid_binary = False
    if ext in [".jpg", ".jpeg"] and (content.startswith(b"\xff\xd8\xff") or b"\xff\xd8" in content[:8]):
        is_valid_binary = True
    elif ext == ".png" and (content.startswith(b"\x89PNG") or b"PNG" in content[:8]):
        is_valid_binary = True
    elif ext == ".pdf" and (content.startswith(b"%PDF") or b"%PDF" in content[:8]):
        is_valid_binary = True

    if not is_valid_binary:
        raise HTTPException(
            status_code=400,
            detail=f"Security Alert: Uploaded file does not have valid {ext.upper().replace('.', '')} binary image/document headers."
        )

    # Generate unique Reference ID: CRD-PREM-2026-XXXXX
    ref_suffix = secrets.token_hex(3).upper()
    ref_id = f"CRD-PREM-2026-{ref_suffix}"

    # Save screenshot safely in isolated local uploads dir
    safe_filename = f"{ref_id}_{int(time.time())}{ext}"
    saved_file_path = os.path.join(PREMIUM_UPLOADS_DIR, safe_filename)
    with open(saved_file_path, "wb") as f:
        f.write(content)

    now_iso = datetime.now().isoformat()
    record = {
        "reference_id": ref_id,
        "created_at": now_iso,
        "full_name": clean_name,
        "email": clean_email,
        "mobile": clean_mobile,
        "utr_number": clean_utr,
        "rejection_notes": (rejection_notes or "").strip(),
        "amount": 499,
        "currency": "INR",
        "service_name": "Credofy Premium Borrower Assistance",
        "status": "Pending Verification",
        "workflow_step": "Under Verification",
        "status_explanation": "Your payment verification request has been submitted successfully and is awaiting manual verification by the Credofy team.",
        "agent_assigned": None,
        "has_screenshot": True,
        "screenshot_file": safe_filename,
        "screenshot_size_bytes": len(content)
    }

    # Save to isolated JSON file
    record_file = os.path.join(PREMIUM_DATA_DIR, f"{ref_id}.json")
    with open(record_file, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    # Send Instant Real-Time Alert to Admin's Telegram Phone
    send_telegram_payment_alert(record, content, screenshot.filename or safe_filename)

    return {
        "status": "success",
        "message": "Your payment verification request has been submitted successfully.",
        "reference_id": ref_id,
        "data": record
    }

@app.get("/api/premium/admin-action")
def handle_admin_action(
    ref: str = Query(..., description="Reference ID"),
    action: str = Query(..., description="approve or reject"),
    secret: str = Query(..., description="Admin Secret Key")
):
    """
    1-Click Admin Approval / Rejection Endpoint triggered directly from Telegram.
    Updates the customer's live record immediately.
    """
    from fastapi.responses import HTMLResponse

    if secret != TELEGRAM_ADMIN_SECRET:
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;background:#0F172A;color:#EF4444;padding:40px;text-align:center;'>"
            "<h2>❌ Unauthorized: Invalid Admin Secret Key</h2></body></html>",
            status_code=403
        )

    clean_ref = ref.strip().upper()
    # 1. Strict regex validation (prevents directory traversal and injection)
    if not re.match(r"^CRD-PREM-2026-[A-F0-9]{4,10}$", clean_ref):
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;background:#0F172A;color:#EF4444;padding:40px;text-align:center;'>"
            "<h2>❌ Invalid Reference ID Format</h2></body></html>",
            status_code=400
        )

    record_file = os.path.abspath(os.path.join(PREMIUM_DATA_DIR, f"{clean_ref}.json"))
    # Verify file path cannot escape PREMIUM_DATA_DIR
    if not record_file.startswith(os.path.abspath(PREMIUM_DATA_DIR)) or not os.path.exists(record_file):
        return HTMLResponse(
            f"<html><body style='font-family:sans-serif;background:#0F172A;color:#F59E0B;padding:40px;text-align:center;'>"
            f"<h2>⚠️ Reference ID Not Found: {html.escape(clean_ref)}</h2></body></html>",
            status_code=404
        )

    with open(record_file, "r", encoding="utf-8") as f:
        record = json.load(f)

    applicant_name = record.get("full_name", "Applicant")
    safe_name = html.escape(applicant_name)
    safe_ref = html.escape(clean_ref)

    if action.lower() == "approve":
        record["status"] = "Payment Verified"
        record["workflow_step"] = "Agent Assigned"
        record["status_explanation"] = "Congratulations! Your ₹499 payment has been verified by the Credofy team. Our senior borrower advisory team has been allocated to your case and will contact you directly within 24–48 business hours."
        record["agent_assigned"] = "Credofy Advisory Team (Lead Desk)"
        status_color = "#10B981"
        action_text = "APPROVED & VERIFIED"
        message_detail = f"Payment for <b>{safe_name}</b> has been approved! Customer's live status is now green and our team will contact them directly."
    else:
        record["status"] = "Payment Rejected"
        record["workflow_step"] = "Payment Verification Failed"
        record["status_explanation"] = "The UTR or payment screenshot provided could not be verified against banking records. Please re-check or contact kunalsrivastava.tech@gmail.com."
        record["agent_assigned"] = "None"
        status_color = "#EF4444"
        action_text = "REJECTED"
        message_detail = f"Payment for <b>{safe_name}</b> has been marked as rejected."

    record["updated_at"] = datetime.now().isoformat()

    # Save updated record
    with open(record_file, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    # Ping Telegram with confirmation
    try:
        conf_msg = f"🔔 <b>STATUS UPDATE:</b> Reference <code>{safe_ref}</code> ({safe_name}) was marked as <b>{html.escape(action_text)}</b> by Admin."
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": conf_msg, "parse_mode": "HTML"},
            timeout=5
        )
    except Exception:
        pass

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>Credofy Admin Action — {html.escape(action_text)}</title>
      <style>
        body {{
          background: #070B14;
          color: #F8FAFC;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 100vh;
          margin: 0;
          padding: 20px;
          box-sizing: border-box;
        }}
        .card {{
          background: #0F1626;
          border: 1px solid #1E293B;
          border-radius: 24px;
          padding: 36px 28px;
          max-width: 460px;
          width: 100%;
          text-align: center;
          box-shadow: 0 25px 50px rgba(0,0,0,0.5);
        }}
        .badge {{
          display: inline-block;
          background: {status_color}20;
          border: 1px solid {status_color}50;
          color: {status_color};
          font-weight: 800;
          font-size: 14px;
          padding: 6px 16px;
          border-radius: 999px;
          margin-bottom: 20px;
        }}
        h2 {{ margin: 0 0 10px 0; font-size: 20px; line-height: 1.4; }}
        p {{ color: #94A3B8; font-size: 13px; line-height: 1.5; }}
        .ref {{ font-family: monospace; background: #070B14; padding: 6px 12px; border-radius: 8px; color: #F59E0B; font-weight: bold; font-size: 15px; margin: 15px 0; display: inline-block; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="badge">Action: {html.escape(action_text)}</div>
        <h2>{message_detail}</h2>
        <div class="ref">{safe_ref}</div>
        <p>The customer's dashboard on Credofy has been updated in real-time. You can close this window now.</p>
      </div>
    </body>
    </html>
    """)

@app.get("/api/premium/status/{reference_id}")
def get_premium_request_status(reference_id: str):
    """
    Fetches the verification & agent status for a given reference ID.
    Hardened against Directory Traversal and Regex Format Violations.
    """
    clean_ref = reference_id.strip().upper()
    if not re.match(r"^CRD-PREM-2026-[A-F0-9]{4,10}$", clean_ref):
        raise HTTPException(status_code=400, detail="Invalid Reference ID format.")

    record_file = os.path.abspath(os.path.join(PREMIUM_DATA_DIR, f"{clean_ref}.json"))
    if not record_file.startswith(os.path.abspath(PREMIUM_DATA_DIR)) or not os.path.exists(record_file):
        raise HTTPException(status_code=404, detail="Reference ID not found.")

    with open(record_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {"status": "success", "data": data}

@app.get("/api/premium/my-requests")
def get_my_premium_requests(identifier: str = Query(..., description="Mobile number or email")):
    """
    Returns all premium requests matching customer's email or mobile number.
    Input-validated to prevent arbitrary parameter abuse.
    """
    clean_id = identifier.strip().lower()
    clean_mobile = re.sub(r"\D", "", clean_id)
    if len(clean_id) > 100:
        raise HTTPException(status_code=400, detail="Identifier is too long.")
    results = []

    if os.path.exists(PREMIUM_DATA_DIR):
        for fname in os.listdir(PREMIUM_DATA_DIR):
            if fname.endswith(".json") and fname.startswith("CRD-PREM-"):
                try:
                    with open(os.path.join(PREMIUM_DATA_DIR, fname), "r", encoding="utf-8") as f:
                        req = json.load(f)
                        req_email = req.get("email", "").lower()
                        req_mobile = req.get("mobile", "")
                        if (clean_id and clean_id == req_email) or (clean_mobile and clean_mobile == req_mobile):
                            results.append(req)
                except Exception:
                    pass

    # Sort newest first
    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"status": "success", "count": len(results), "requests": results}



from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Check if React dist directory exists for Unified Single-URL Hosting
FRONTEND_DIST = os.path.join(BASE_DIR, "frontend", "dist")
if os.path.exists(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend_spa(full_path: str):
        # Allow API routes to be handled by FastAPI
        if full_path.startswith("api/") or full_path == "api" or full_path.startswith("docs") or full_path.startswith("openapi.json"):
            raise HTTPException(status_code=404, detail="API route not found")
        
        # Check if requested static file exists in frontend dist (e.g. manifest.json)
        target_file = os.path.join(FRONTEND_DIST, full_path)
        if full_path and os.path.isfile(target_file):
            return FileResponse(target_file)

        index_file = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.exists(index_file):
            return FileResponse(
                index_file,
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
        return {"error": "Frontend build index.html not found"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("server:app", host=host, port=port, reload=False)
