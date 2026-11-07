import os
import json
import numpy as np
import pandas as pd
import joblib
from datetime import datetime
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix, classification_report
)
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
import shap

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
MODELS_DIR = os.path.join(BASE_DIR, 'models')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)

def generate_indian_credit_dataset(n_samples=2500, random_state=42):
    """
    Generates a realistic Indian retail, MSME & Gramin credit dataset.
    Features reflect RBI Priority Sector Lending guidelines and CIBIL score distribution.
    """
    np.random.seed(random_state)
    
    # Demographics
    genders = np.random.choice(['Female', 'Male'], size=n_samples, p=[0.35, 0.65])
    married = np.random.choice(['Yes', 'No'], size=n_samples, p=[0.68, 0.32])
    dependents = np.random.choice(['0', '1', '2', '3+'], size=n_samples, p=[0.50, 0.22, 0.18, 0.10])
    education = np.random.choice(['Graduate', 'Not Graduate'], size=n_samples, p=[0.75, 0.25])
    self_employed = np.random.choice(['Yes', 'No'], size=n_samples, p=[0.38, 0.62])
    property_area = np.random.choice(['Rural', 'Semiurban', 'Urban'], size=n_samples, p=[0.35, 0.35, 0.30])
    
    # Financials
    applicant_income = []
    for area, emp in zip(property_area, self_employed):
        base = 26000 if area == 'Rural' else (36000 if area == 'Semiurban' else 55000)
        if emp == 'Yes': # Kirana / MSME / Trader
            income = np.random.gamma(shape=3.2, scale=base/3.2)
        else: # Salaried
            income = np.random.normal(loc=base, scale=base*0.3)
        applicant_income.append(max(8000, int(income)))
    applicant_income = np.array(applicant_income)
    
    has_coapplicant = np.random.choice([0, 1], size=n_samples, p=[0.30, 0.70])
    coapplicant_income = []
    for has_co, app_inc in zip(has_coapplicant, applicant_income):
        if has_co:
            co_inc = np.random.gamma(shape=2.5, scale=app_inc * 0.45 / 2.5)
            coapplicant_income.append(max(5000, int(co_inc)))
        else:
            coapplicant_income.append(0)
    coapplicant_income = np.array(coapplicant_income)
    
    total_income = applicant_income + coapplicant_income
    
    # Loan Amount in ₹ Lakhs (0.5 to 50 Lakhs)
    loan_amount_lakhs = np.round(
        (total_income * np.random.uniform(12, 34) / 100000) * np.random.uniform(0.75, 1.25),
        2
    )
    loan_amount_lakhs = np.clip(loan_amount_lakhs, 0.5, 50.0)
    
    # Tenure in Months
    terms = np.random.choice([12, 24, 36, 60, 120, 180, 240, 360], size=n_samples, p=[0.05, 0.08, 0.22, 0.25, 0.15, 0.12, 0.08, 0.05])
    
    # CIBIL Score (300 to 900)
    cibil_scores = np.random.beta(a=4.8, b=2.2, size=n_samples) * (900 - 300) + 300
    cibil_scores = np.clip(np.round(cibil_scores), 300, 900).astype(int)
    
    # Credit History (1 = Clean record, 0 = Past late payments / defaults)
    credit_history = np.where(cibil_scores >= 650, 1, 0)
    flip_mask = np.random.rand(n_samples) < 0.04
    credit_history = np.where(flip_mask, 1 - credit_history, credit_history)
    
    # Estimated Monthly EMI & FOIR (Fixed Obligation to Income Ratio)
    monthly_rate = 0.095 / 12
    emi = (loan_amount_lakhs * 100000) * (monthly_rate * (1 + monthly_rate)**terms) / ((1 + monthly_rate)**terms - 1)
    foir = np.round(emi / np.maximum(1, total_income), 3)
    
    # Real-world underwriting decision rules
    cibil_factor = (cibil_scores - 650) / 100.0
    ch_factor = np.where(credit_history == 1, 2.2, -3.2)
    foir_factor = np.where(foir > 0.50, -2.2, 0.9)
    income_factor = np.log10(total_income / 30000.0) * 1.5
    loan_amt_factor = -1.0 * (loan_amount_lakhs / 20.0)
    
    # Mild historical friction for fairness audit demonstration
    geo_bias = np.where(property_area == 'Rural', -0.25, 0.05)
    
    logits = (
        0.8 + ch_factor + 1.8 * cibil_factor + foir_factor + 
        income_factor + loan_amt_factor + geo_bias + np.random.normal(0, 0.35, n_samples)
    )
    probs = 1 / (1 + np.exp(-logits))
    loan_status = np.where(probs >= 0.50, 'Y', 'N')
    
    df = pd.DataFrame({
        'Gender': genders,
        'Married': married,
        'Dependents': dependents,
        'Education': education,
        'Self_Employed': self_employed,
        'ApplicantIncome': applicant_income,
        'CoapplicantIncome': coapplicant_income,
        'LoanAmount': loan_amount_lakhs,
        'Loan_Amount_Term': terms,
        'CIBIL_Score': cibil_scores,
        'Credit_History': credit_history,
        'Property_Area': property_area,
        'FOIR': foir,
        'Loan_Status': loan_status
    })
    return df

def train_and_export():
    print("[1/5] Ingesting and synthesizing Indian Credit Data...")
    df = generate_indian_credit_dataset(n_samples=2500, random_state=42)
    data_path = os.path.join(DATA_DIR, "indian_loan_data.csv")
    df.to_csv(data_path, index=False)
    print(f"      Saved {len(df)} records to {data_path}")
    
    feature_cols = [
        'Gender', 'Married', 'Dependents', 'Education', 'Self_Employed',
        'ApplicantIncome', 'CoapplicantIncome', 'LoanAmount', 'Loan_Amount_Term',
        'CIBIL_Score', 'Credit_History', 'Property_Area', 'FOIR'
    ]
    target_col = 'Loan_Status'
    
    X = df[feature_cols]
    y = df[target_col].map({'Y': 1, 'N': 0})
    
    num_cols = ['ApplicantIncome', 'CoapplicantIncome', 'LoanAmount', 'Loan_Amount_Term', 'CIBIL_Score', 'Credit_History', 'FOIR']
    cat_cols = ['Gender', 'Married', 'Dependents', 'Education', 'Self_Employed', 'Property_Area']
    
    print("[2/5] Building Scikit-Learn Transformation Pipeline...")
    num_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler())
    ])
    
    cat_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='most_frequent')),
        ('onehot', OneHotEncoder(handle_unknown='ignore', sparse_output=False))
    ])
    
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', num_transformer, num_cols),
            ('cat', cat_transformer, cat_cols)
        ]
    )
    
    # 5-Fold Stratified Cross-Validation Benchmark
    print("[3/5] Running 5-Fold Stratified Cross-Validation...")
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = {'accuracy': [], 'roc_auc': [], 'precision': [], 'recall': [], 'f1': []}
    
    X_processed = preprocessor.fit_transform(X)
    encoded_cat_names = preprocessor.named_transformers_['cat'].named_steps['onehot'].get_feature_names_out(cat_cols)
    all_feature_names = num_cols + list(encoded_cat_names)
    
    model = RandomForestClassifier(
        n_estimators=160,
        max_depth=8,
        min_samples_split=4,
        class_weight='balanced',
        random_state=42
    )
    
    for train_idx, val_idx in skf.split(X_processed, y):
        X_tr, X_val = X_processed[train_idx], X_processed[val_idx]
        y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]
        
        model.fit(X_tr, y_tr)
        preds = model.predict(X_val)
        probs = model.predict_proba(X_val)[:, 1]
        
        cv_scores['accuracy'].append(accuracy_score(y_val, preds))
        cv_scores['roc_auc'].append(roc_auc_score(y_val, probs))
        cv_scores['precision'].append(precision_score(y_val, preds))
        cv_scores['recall'].append(recall_score(y_val, preds))
        cv_scores['f1'].append(f1_score(y_val, preds))
        
    print(f"      CV Accuracy:  {np.mean(cv_scores['accuracy'])*100:.2f}% (±{np.std(cv_scores['accuracy'])*100:.2f}%)")
    print(f"      CV ROC-AUC:   {np.mean(cv_scores['roc_auc']):.4f}")
    print(f"      CV F1-Score:  {np.mean(cv_scores['f1']):.4f}")
    
    # Final Model Fit on Complete Dataset
    print("[4/5] Training Final Production Ensemble & Initializing SHAP TreeExplainer...")
    model.fit(X_processed, y)
    
    y_pred_all = model.predict(X_processed)
    y_prob_all = model.predict_proba(X_processed)[:, 1]
    cm = confusion_matrix(y, y_pred_all).tolist()
    
    explainer = shap.TreeExplainer(model)
    
    # Quantitative Accuracy Report Artifact
    accuracy_report = {
        'model_name': 'Kredo Production Random Forest Underwriter',
        'generated_at': datetime.utcnow().isoformat(),
        'cv_5fold_metrics': {
            'mean_accuracy': round(float(np.mean(cv_scores['accuracy'])), 4),
            'mean_roc_auc': round(float(np.mean(cv_scores['roc_auc'])), 4),
            'mean_precision': round(float(np.mean(cv_scores['precision'])), 4),
            'mean_recall': round(float(np.mean(cv_scores['recall'])), 4),
            'mean_f1_score': round(float(np.mean(cv_scores['f1'])), 4)
        },
        'full_dataset_metrics': {
            'accuracy': round(float(accuracy_score(y, y_pred_all)), 4),
            'roc_auc': round(float(roc_auc_score(y, y_prob_all)), 4),
            'precision': round(float(precision_score(y, y_pred_all)), 4),
            'recall': round(float(recall_score(y, y_pred_all)), 4),
            'f1_score': round(float(f1_score(y, y_pred_all)), 4)
        },
        'confusion_matrix': {
            'true_negatives': cm[0][0],
            'false_positives': cm[0][1],
            'false_negatives': cm[1][0],
            'true_positives': cm[1][1]
        },
        'total_samples': len(y),
        'features': all_feature_names
    }
    
    print("[5/5] Saving Serialized Artifacts to /models/...")
    with open(os.path.join(MODELS_DIR, 'accuracy_report.json'), 'w') as f:
        json.dump(accuracy_report, f, indent=2)
        
    joblib.dump(model, os.path.join(MODELS_DIR, 'kredo_model.pkl'))
    joblib.dump(model, os.path.join(MODELS_DIR, 'equibharat_model.pkl'))
    joblib.dump(preprocessor, os.path.join(MODELS_DIR, 'preprocessor.pkl'))
    joblib.dump(explainer, os.path.join(MODELS_DIR, 'explainer.pkl'))
    joblib.dump(all_feature_names, os.path.join(MODELS_DIR, 'feature_names.pkl'))
    
    print("✓ Model training & artifact serialization complete!")

if __name__ == '__main__':
    train_and_export()
