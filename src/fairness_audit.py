import os
import pandas as pd
import numpy as np
import joblib

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
MODELS_DIR = os.path.join(BASE_DIR, 'models')

class EquiBharatFairnessAuditor:
    def __init__(self, data_path=None, model_dir=None):
        if data_path is None:
            data_path = os.path.join(DATA_DIR, "indian_loan_data.csv")
        if model_dir is None:
            model_dir = MODELS_DIR
        self.data_path = data_path
        model_file = "equibharat_model.pkl" if os.path.exists(os.path.join(model_dir, "equibharat_model.pkl")) else "kredo_model.pkl"
        self.model = joblib.load(os.path.join(model_dir, model_file))
        self.preprocessor = joblib.load(os.path.join(model_dir, "preprocessor.pkl"))

    def compute_fairness_report(self):
        """
        Audits credit decisions against the regulatory Four-Fifths (80%) Rule across:
        1. Geographic Fairness: Rural (Gramin) vs Urban/Semi-Urban
        2. Gender Fairness: Female vs Male
        """
        df = pd.read_csv(self.data_path)
        
        feature_cols = [
            'Gender', 'Married', 'Dependents', 'Education', 'Self_Employed',
            'ApplicantIncome', 'CoapplicantIncome', 'LoanAmount', 'Loan_Amount_Term',
            'CIBIL_Score', 'Credit_History', 'Property_Area', 'FOIR'
        ]
        
        X = df[feature_cols]
        X_proc = self.preprocessor.transform(X)
        preds = self.model.predict(X_proc)
        probs = self.model.predict_proba(X_proc)[:, 1]
        
        df['Predicted_Approval'] = preds
        df['Approval_Prob'] = probs
        
        # 1. Geographic Fairness (Rural vs Urban)
        rural_df = df[df['Property_Area'] == 'Rural']
        urban_df = df[df['Property_Area'] == 'Urban']
        semi_df = df[df['Property_Area'] == 'Semiurban']
        
        rural_rate = float(rural_df['Predicted_Approval'].mean())
        urban_rate = float(urban_df['Predicted_Approval'].mean())
        semi_rate = float(semi_df['Predicted_Approval'].mean())
        
        geo_dir = rural_rate / max(1e-5, urban_rate)
        
        # 2. Gender Fairness (Female vs Male)
        female_df = df[df['Gender'] == 'Female']
        male_df = df[df['Gender'] == 'Male']
        
        female_rate = float(female_df['Predicted_Approval'].mean())
        male_rate = float(male_df['Predicted_Approval'].mean())
        
        gender_dir = female_rate / max(1e-5, male_rate)
        
        # 3. Demographic Parity Gaps
        geo_parity_gap = abs(urban_rate - rural_rate)
        gender_parity_gap = abs(male_rate - female_rate)
        
        report = {
            'summary': {
                'total_audited_records': len(df),
                'overall_approval_rate': round(float(df['Predicted_Approval'].mean()) * 100, 1),
                'four_fifths_threshold': 0.80
            },
            'geographic_fairness': {
                'rural_approval_rate': round(rural_rate * 100, 1),
                'urban_approval_rate': round(urban_rate * 100, 1),
                'semiurban_approval_rate': round(semi_rate * 100, 1),
                'disparate_impact_ratio': round(geo_dir, 3),
                'parity_gap': round(geo_parity_gap * 100, 1),
                'is_compliant': bool(geo_dir >= 0.80),
                'status_badge': 'Compliant (RBI अनुपालन)' if geo_dir >= 0.80 else 'Action Recommended (सुधार आवश्यक)'
            },
            'gender_fairness': {
                'female_approval_rate': round(female_rate * 100, 1),
                'male_approval_rate': round(male_rate * 100, 1),
                'disparate_impact_ratio': round(gender_dir, 3),
                'parity_gap': round(gender_parity_gap * 100, 1),
                'is_compliant': bool(gender_dir >= 0.80),
                'status_badge': 'Compliant (RBI अनुपालन)' if gender_dir >= 0.80 else 'Action Recommended (सुधार आवश्यक)'
            },
            'subgroup_stats': {
                'rural_count': len(rural_df),
                'urban_count': len(urban_df),
                'semiurban_count': len(semi_df),
                'female_count': len(female_df),
                'male_count': len(male_df)
            }
        }
        return report

# Backward-compatible alias
KredoFairnessAuditor = EquiBharatFairnessAuditor
