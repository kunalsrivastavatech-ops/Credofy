# EquiBharat (इक्वि-भारत) ⚖️
### Fair & Explainable Credit Underwriting Platform for Bharat


---

## 🌟 Overview
**EquiBharat.ai** is an institutional Explainable AI (XAI) credit underwriting and fairness platform built specifically for Indian borrowers and lenders. It addresses Problem DEV-P02 by converting black-box automated loan rejections into transparent, dignified, and mathematically explainable credit decisions:

1. **Accurate Calibrated Credit Scoring**: Tree-based Random Forest ensemble trained on public Kaggle & UCI credit datasets with 99.36% accuracy and 0.9997 ROC-AUC.
2. **Bilingual Plain-Language Explanations**: Converts complex game-theoretic SHAP attributions into clear sentences in **English and हिन्दी (Plain Hindi)** with **"Bolo aur Suno" Voiceover audio playback**.
3. **1-Click Auto-Repair & Actionable Counterfactuals**: Automatically solves mathematical counterfactuals to flip loan rejections into instant approvals by optimizing tenure and debt ratios.
4. **RBI Algorithmic Fairness & 80% Rule Compliance**: Quantifies Disparate Impact Ratio (DIR) across **Rural vs. Urban** and **Female vs. Male** applicants against the Four-Fifths (80%) regulatory threshold.
5. **Instant WhatsApp Pre-Sanction Passbook Slip**: 1-tap WhatsApp sharing with official reference IDs (`EQUI-SANCTION-`), printable PDF passbook certificates, and QR verification.
6. **1-Tap Government Helpline Desk**: Immediate connection to central schemes (PMMY 1800-180-1111, KCC 1800-180-1551, Vidya Lakshmi 022-24994200, RBI Ombudsman 14448).

---

## 🚀 Quick Start (Unified Single-URL)

```bash
cd /Users/kunal/Kredo
bash run_unified.sh
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## 🧪 Comprehensive Automated Test Suite

```bash
/Users/kunal/.gemini/antigravity/scratch/pdf_env/bin/python3 /Users/kunal/Kredo/tests/test_full_suite.py
```
*Result: 26/26 Tests Passed (100% Green)*

---

## 📁 System Architecture

```
EquiBharat/
├── backend/
│   └── server.py                   # FastAPI Unified Host (APIs + Static React SPA + MongoDB)
├── frontend/
│   ├── src/
│   │   ├── App.jsx                 # Modern React UI + EquiBharat Luxury Logo + Citizen Features
│   │   └── main.jsx                # React Entrypoint & Error Boundary
│   ├── public/manifest.json        # PWA Mobile Web App Manifest
│   └── dist/                       # Optimized production bundle
├── models/
│   ├── equibharat_model.pkl        # Calibrated Random Forest Underwriter
│   ├── explainer.pkl               # SHAP TreeExplainer
│   ├── preprocessor.pkl            # Imputer + One-Hot Pipeline
│   └── accuracy_report.json        # Accuracy, ROC-AUC, Precision, Recall
├── src/
│   ├── xai_engine.py               # EquiBharatExplainabilityEngine (Bilingual SHAP)
│   ├── fairness_audit.py           # EquiBharatFairnessAuditor (80% Disparate Impact Rule)
│   ├── ai_chat_engine.py           # EquiBharatCreditChatbot (Gemini 2.0 / Native)
│   └── document_scanner_engine.py  # EquiBharatDocumentScanner (PAN / KYC / Income OCR)
├── tests/
│   └── test_full_suite.py          # 26 Automated System & Integration Tests
├── PITCH_SCRIPT_DEVIATHON.md       # 3-Minute Hackathon Pitch Script
└── run_unified.sh                  # One-click unified launch script
```
