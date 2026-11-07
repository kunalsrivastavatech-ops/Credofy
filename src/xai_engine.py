import os
import numpy as np
import pandas as pd
import joblib
import shap

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, 'models')

class EquiBharatExplainabilityEngine:
    def __init__(self, model_dir=None):
        if model_dir is None:
            model_dir = MODELS_DIR
        model_file = "equibharat_model.pkl" if os.path.exists(os.path.join(model_dir, "equibharat_model.pkl")) else "kredo_model.pkl"
        try:
            self.model = joblib.load(os.path.join(model_dir, model_file))
            self.preprocessor = joblib.load(os.path.join(model_dir, "preprocessor.pkl"))
            self.explainer = joblib.load(os.path.join(model_dir, "explainer.pkl"))
            self.feature_names = joblib.load(os.path.join(model_dir, "feature_names.pkl"))
        except Exception as e:
            print(f"Notice: Pickled model load warning ({e}). Auto-retraining fresh model in current Python environment...")
            try:
                from train_model import train_and_export
                train_and_export()
                self.model = joblib.load(os.path.join(model_dir, model_file))
                self.preprocessor = joblib.load(os.path.join(model_dir, "preprocessor.pkl"))
                self.explainer = joblib.load(os.path.join(model_dir, "explainer.pkl"))
                self.feature_names = joblib.load(os.path.join(model_dir, "feature_names.pkl"))
            except Exception as e2:
                print(f"Error during runtime fallback training: {e2}")
                raise e
        
        # Friendly Indian Terminology mappings
        self.feature_labels_en = {
            'CIBIL_Score': 'Credit Bureau Score (CIBIL)',
            'Credit_History': 'Repayment Track Record',
            'FOIR': 'EMI-to-Income Ratio (FOIR)',
            'ApplicantIncome': 'Monthly Net Income',
            'CoapplicantIncome': 'Co-Applicant Family Income',
            'LoanAmount': 'Requested Loan Amount',
            'Loan_Amount_Term': 'Repayment Tenure',
            'Property_Area': 'Property Location / Geography',
            'Self_Employed': 'Employment / MSME Status',
            'Education': 'Education Qualification',
            'Married': 'Marital Status',
            'Dependents': 'Family Dependents'
        }
        
        self.feature_labels_hi = {
            'CIBIL_Score': 'क्रेडिट स्कोर (CIBIL Score)',
            'Credit_History': 'पुराना लोन भुगतान रिकॉर्ड',
            'FOIR': 'आय की तुलना में EMI का बोझ (FOIR)',
            'ApplicantIncome': 'मासिक शुद्ध आय (Net Monthly Income)',
            'CoapplicantIncome': 'सह-आवेदक (परिवार) की आय',
            'LoanAmount': 'मांगी गई लोन राशि',
            'Loan_Amount_Term': 'लोन चुकाने की अवधि (Tenure)',
            'Property_Area': 'स्थान / क्षेत्र (ग्रामीण या शहरी)',
            'Self_Employed': 'व्यवसाय / नौकरी का प्रकार',
            'Education': 'शिक्षा स्तर',
            'Married': 'वैवाहिक स्थिति',
            'Dependents': 'परिवार में आश्रित सदस्य'
        }

    def predict_and_explain(self, applicant_dict):
        """
        Takes raw applicant dict, calculates approval likelihood and generates
        per-applicant SHAP values translated into English and Hindi, plus counterfactuals.
        """
        df_raw = pd.DataFrame([applicant_dict])
        
        # Calculate FOIR if not explicitly supplied
        tot_inc = max(1.0, float(applicant_dict['ApplicantIncome'] + applicant_dict.get('CoapplicantIncome', 0)))
        loan_lakhs = max(0.1, float(applicant_dict['LoanAmount']))
        term = max(1, int(applicant_dict.get('Loan_Amount_Term', 36)))
        monthly_rate = 0.095 / 12
        denom = ((1 + monthly_rate)**term - 1)
        if denom > 0:
            emi = (loan_lakhs * 100000) * (monthly_rate * (1 + monthly_rate)**term) / denom
        else:
            emi = (loan_lakhs * 100000) / term
        calculated_foir = round(emi / tot_inc, 3)
        df_raw['FOIR'] = calculated_foir

        # Preprocess
        X_proc = self.preprocessor.transform(df_raw)
        
        # Probability & Prediction
        prob_approved = float(self.model.predict_proba(X_proc)[0, 1])
        is_approved = bool(prob_approved >= 0.50)
        
        # SHAP calculation
        shap_values = self.explainer.shap_values(X_proc)
        if isinstance(shap_values, list):
            sv = shap_values[1][0] # Positive class (Approval)
        elif len(shap_values.shape) == 3:
            sv = shap_values[0, :, 1]
        else:
            sv = shap_values[0]

        # Consolidate one-hot encoded categories back into unified feature contributions
        feature_impacts = {}
        for fname, val in zip(self.feature_names, sv):
            base_col = fname
            for cat in ['Gender', 'Married', 'Dependents', 'Education', 'Self_Employed', 'Property_Area']:
                if fname.startswith(f"cat__{cat}_") or fname.startswith(f"{cat}_"):
                    base_col = cat
                    break
            feature_impacts[base_col] = feature_impacts.get(base_col, 0.0) + float(val)

        # Sort features by impact
        sorted_positives = sorted([(k, v) for k, v in feature_impacts.items() if v > 0], key=lambda x: x[1], reverse=True)
        sorted_negatives = sorted([(k, v) for k, v in feature_impacts.items() if v < 0], key=lambda x: x[1])

        # Generate English and Hindi plain text explanations
        explanations_en = self._generate_text_en(sorted_positives[:3], sorted_negatives[:3], applicant_dict, is_approved)
        explanations_hi = self._generate_text_hi(sorted_positives[:3], sorted_negatives[:3], applicant_dict, is_approved)

        # Optimized Counterfactual Suggestions
        counterfactuals_en, counterfactuals_hi = self._generate_counterfactuals(applicant_dict, prob_approved)

        return {
            'is_approved': is_approved,
            'approval_probability': round(prob_approved * 100, 1),
            'risk_band': 'Low Risk (कम जोखिम)' if prob_approved >= 0.70 else ('Moderate Risk (मध्यम जोखिम)' if prob_approved >= 0.50 else 'High Risk (उच्च जोखिम)'),
            'feature_impacts': feature_impacts,
            'explanations_en': explanations_en,
            'explanations_hi': explanations_hi,
            'counterfactuals_en': counterfactuals_en,
            'counterfactuals_hi': counterfactuals_hi,
            'raw_foir': float(calculated_foir),
            'monthly_emi': int(emi)
        }

    def _generate_text_en(self, top_pos, top_neg, applicant_dict, is_approved):
        pos_notes = []
        for feat, val in top_pos:
            label = self.feature_labels_en.get(feat, feat)
            if feat == 'CIBIL_Score':
                pos_notes.append(f"Strong CIBIL Score ({applicant_dict['CIBIL_Score']}) significantly boosted your approval odds.")
            elif feat == 'Credit_History':
                pos_notes.append("Clean past loan repayment track record created strong institutional confidence.")
            elif feat == 'CoapplicantIncome' and applicant_dict.get('CoapplicantIncome', 0) > 0:
                pos_notes.append(f"Family co-applicant income (₹{int(applicant_dict['CoapplicantIncome']):,}/mo) provided solid collateral support.")
            elif feat == 'FOIR':
                pos_notes.append("Estimated monthly EMI is well within safe debt-service limits.")
            elif feat == 'ApplicantIncome':
                pos_notes.append(f"Verified monthly net income (₹{int(applicant_dict['ApplicantIncome']):,}/mo) demonstrates steady cashflow.")
            else:
                pos_notes.append(f"{label} had a favorable positive contribution to your profile.")

        neg_notes = []
        for feat, val in top_neg:
            label = self.feature_labels_en.get(feat, feat)
            if feat == 'CIBIL_Score':
                neg_notes.append(f"CIBIL Score of {applicant_dict['CIBIL_Score']} is below preferred bank thresholds.")
            elif feat == 'Credit_History':
                neg_notes.append("Previous late payment flag was a primary hurdle in automated underwriting.")
            elif feat == 'FOIR':
                neg_notes.append("Estimated monthly EMI requires an excessive portion of monthly net earnings.")
            elif feat == 'LoanAmount':
                neg_notes.append(f"Requested loan amount (₹{applicant_dict['LoanAmount']} Lakhs) is high for current earnings.")
            else:
                neg_notes.append(f"{label} reduced your approval probability.")

        return {
            'positive_factors': pos_notes or ["No major positive factors identified."],
            'negative_factors': neg_notes or ["No major hurdles identified."]
        }

    def _generate_text_hi(self, top_pos, top_neg, applicant_dict, is_approved):
        pos_notes = []
        for feat, val in top_pos:
            label = self.feature_labels_hi.get(feat, feat)
            if feat == 'CIBIL_Score':
                pos_notes.append(f"मजबूत CIBIL स्कोर ({applicant_dict['CIBIL_Score']}) ने आपकी मंज़ूरी में सबसे बड़ा योगदान दिया।")
            elif feat == 'Credit_History':
                pos_notes.append("पुराने कर्जों का समय पर भुगतान करने का साफ रिकॉर्ड सबसे बड़ा सकारात्मक कारक रहा।")
            elif feat == 'CoapplicantIncome' and applicant_dict.get('CoapplicantIncome', 0) > 0:
                pos_notes.append(f"सह-आवेदक (परिवार) की आय (₹{int(applicant_dict['CoapplicantIncome']):,}/माह) ने मजबूत सुरक्षा दी।")
            elif feat == 'FOIR':
                pos_notes.append("अनुमानित मासिक किस्त (EMI) आपकी कुल आय के सुरक्षित दायरे में है।")
            elif feat == 'ApplicantIncome':
                pos_notes.append(f"सत्यापित मासिक आय (₹{int(applicant_dict['ApplicantIncome']):,}/माह) से निरंतर कमाई की पुष्टि हुई।")
            else:
                pos_notes.append(f"{label} ने आपके आवेदन को सकारात्मक मजबूती दी।")

        neg_notes = []
        for feat, val in top_neg:
            label = self.feature_labels_hi.get(feat, feat)
            if feat == 'CIBIL_Score':
                neg_notes.append(f"आपका CIBIL स्कोर ({applicant_dict['CIBIL_Score']}) बैंक के मानक स्तर से कम रहा।")
            elif feat == 'Credit_History':
                neg_notes.append("पुराने किसी लोन की किस्त में देरी या डिफ़ॉल्ट होना मुख्य रुकावट बना।")
            elif feat == 'FOIR':
                neg_notes.append("मासिक कमाई की तुलना में लोन की किस्त (EMI) का अनुपात बहुत अधिक है।")
            elif feat == 'LoanAmount':
                neg_notes.append(f"मांगी गई लोन राशि (₹{applicant_dict['LoanAmount']} लाख) वर्तमान आय से अधिक है।")
            else:
                neg_notes.append(f"{label} ने आपकी लोन मंज़ूरी की संभावना को घटाया।")

        return {
            'positive_factors': pos_notes or ["कोई मुख्य सकारात्मक कारक नहीं पाया गया।"],
            'negative_factors': neg_notes or ["कोई बड़ी रुकावट नहीं पाई गई।"]
        }

    def _generate_counterfactuals(self, applicant_dict, current_prob):
        """Actionable counterfactual advice to turn rejection into approval."""
        cf_en = []
        cf_hi = []

        if current_prob < 0.70:
            if applicant_dict.get('CoapplicantIncome', 0) == 0:
                cf_en.append("Add a family co-borrower (spouse/parent) earning ₹15,000–₹25,000/month to boost household income.")
                cf_hi.append("परिवार के किसी सदस्य (पति/पत्नी/पिता) को सह-आवेदक जोड़ें जिनकी मासिक आय ₹15,000-₹25,000 हो।")
            
            if applicant_dict['LoanAmount'] > 2.0:
                reduced_amt = round(applicant_dict['LoanAmount'] * 0.8, 1)
                cf_en.append(f"Reduce requested loan from ₹{applicant_dict['LoanAmount']}L to ₹{reduced_amt}L to lower your monthly EMI burden.")
                cf_hi.append(f"लोन राशि को ₹{applicant_dict['LoanAmount']} लाख से घटाकर ₹{reduced_amt} लाख करें ताकि महीने की किस्त कम हो सके।")
            
            if applicant_dict['Loan_Amount_Term'] < 120:
                cf_en.append("Opt for a longer repayment tenure (e.g. 60 or 120 months) to reduce monthly EMI strain.")
                cf_hi.append("लोन चुकाने की अवधि बढ़ाएं (जैसे 5 से 10 वर्ष), जिससे हर महीने की किस्त घटकर बजट में आ जाए।")

            if applicant_dict.get('Self_Employed') == 'Yes' and applicant_dict['LoanAmount'] <= 10.0:
                cf_en.append("Consider applying under the Pradhan Mantri Mudra Yojana (PMMY) for collateral-free MSME credit.")
                cf_hi.append("प्रधानमंत्री मुद्रा योजना (PMMY) के तहत आवेदन करें, जहाँ छोटे व्यापारियों को बिना गारंटी सुलभ ऋण मिलता है।")
        else:
            cf_en.append("Your profile is in an excellent tier. You qualify for prime interest rates and minimal processing fees.")
            cf_hi.append("आपकी प्रोफ़ाइल बहुत मजबूत है। आप सबसे कम ब्याज दर और त्वरित मंज़ूरी के पात्र हैं।")

        return cf_en, cf_hi

# Backward-compatible alias
KredoExplainabilityEngine = EquiBharatExplainabilityEngine
