import os
import sys
import json
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
from xai_engine import KredoExplainabilityEngine
from fairness_audit import KredoFairnessAuditor

# Page Configuration
st.set_page_config(
    page_title="Kredo | Explainable Credit for Bharat",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling (Modern Fintech + Indian Saffron Accent)
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        color: #0F172A;
        margin-bottom: 0px;
    }
    .sub-header {
        font-size: 1.05rem;
        font-weight: 600;
        color: #D97706;
        margin-bottom: 15px;
    }
    .badge-bharat {
        background-color: #FEF3C7;
        color: #92400E;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.8rem;
        border: 1px solid #FCD34D;
    }
    .status-approved {
        background-color: #DCFCE7;
        color: #166534;
        padding: 12px 18px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 1.4rem;
        border: 1.5px solid #86EFAC;
        text-align: center;
    }
    .status-review {
        background-color: #FEE2E2;
        color: #991B1B;
        padding: 12px 18px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 1.4rem;
        border: 1.5px solid #FCA5A5;
        text-align: center;
    }
    .card-box {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def load_engines():
    try:
        xai = KredoExplainabilityEngine()
        fairness = KredoFairnessAuditor()
        return xai, fairness
    except Exception as e:
        return None, None

xai_engine, fairness_auditor = load_engines()

# Sidebar: Language and Preloaded Bharat Personas
st.sidebar.image("https://img.icons8.com/fluency/96/bank-building.png", width=64)
st.sidebar.markdown("### **Kredo (क्रेडो)**")
st.sidebar.markdown("<span class='badge-bharat'>MISSION BHARAT • DEV-P02</span>", unsafe_allow_html=True)
st.sidebar.markdown("---")

# Language Selector
lang = st.sidebar.radio("Select Language / भाषा चुनें", ["English", "हिन्दी (Hindi)"], index=0)
is_hindi = (lang == "हिन्दी (Hindi)")

# Preloaded Personas
st.sidebar.markdown("#### **Quick Test Personas (परीक्षण प्रोफाइल)**")
persona = st.sidebar.selectbox(
    "Choose a persona to autofill:" if not is_hindi else "त्वरित प्रोफाइल चुनें:",
    ["Custom Input", "Sunita (Rural Woman SHG - Mathura)", "Ramesh (Tier-3 Kirana Owner)", "Priya (Urban Salaried Tech)"]
)

# Header Bar
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown("<div class='main-header'>Kredo.ai</div>", unsafe_allow_html=True)
    if not is_hindi:
        st.markdown("<div class='sub-header'>Explainable Underwriting & Algorithmic Fairness for Indian Lending</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='sub-header'>भारतीय ऋण प्रणाली के लिए पारदर्शी, निष्पक्ष व सरल AI निर्णय</div>", unsafe_allow_html=True)

with col_h2:
    st.markdown("<div style='text-align: right; padding-top: 10px;'><span class='badge-bharat'>DEVIATHON 2.0 • MERIDIAN</span></div>", unsafe_allow_html=True)

# Main Navigation Tabs
tab_applicant, tab_officer, tab_metrics = st.tabs([
    "👤 Borrower Portal (आवेदक पोर्टल)",
    "🏛️ Branch Officer & Compliance (बैंक व ऑडिट)",
    "📊 Model Accuracy Report (सटीकता रिपोर्ट)"
])

# Default form values based on persona
defaults = {
    'income': 35000,
    'co_income': 0,
    'loan_amt': 3.5,
    'term': 36,
    'cibil': 710,
    'credit_hist': 1,
    'gender': 'Male',
    'self_emp': 'No',
    'area': 'Semiurban',
    'married': 'Yes',
    'education': 'Graduate',
    'dependents': '1'
}

if persona == "Sunita (Rural Woman SHG - Mathura)":
    defaults.update({
        'income': 22000, 'co_income': 18000, 'loan_amt': 2.5, 'term': 60,
        'cibil': 740, 'credit_hist': 1, 'gender': 'Female', 'self_emp': 'Yes',
        'area': 'Rural', 'married': 'Yes', 'education': 'Not Graduate', 'dependents': '2'
    })
elif persona == "Ramesh (Tier-3 Kirana Owner)":
    defaults.update({
        'income': 28000, 'co_income': 0, 'loan_amt': 7.0, 'term': 24,
        'cibil': 630, 'credit_hist': 0, 'gender': 'Male', 'self_emp': 'Yes',
        'area': 'Rural', 'married': 'Yes', 'education': 'Not Graduate', 'dependents': '3+'
    })
elif persona == "Priya (Urban Salaried Tech)":
    defaults.update({
        'income': 85000, 'co_income': 40000, 'loan_amt': 25.0, 'term': 240,
        'cibil': 790, 'credit_hist': 1, 'gender': 'Female', 'self_emp': 'No',
        'area': 'Urban', 'married': 'No', 'education': 'Graduate', 'dependents': '0'
    })

# ----------------- TAB 1: BORROWER SELF-SERVICE -----------------
with tab_applicant:
    st.markdown("#### " + ("Applicant Financial Profile" if not is_hindi else "आवेदक की वित्तीय जानकारी"))
    
    with st.expander("📝 " + ("Edit Financial & Demographic Details" if not is_hindi else "वित्तीय व व्यक्तिगत विवरण भरें"), expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            app_income = st.number_input("Monthly Income (₹) / मासिक आय", min_value=8000, max_value=500000, value=defaults['income'], step=2000)
            co_income = st.number_input("Co-Applicant Income (₹) / सह-आवेदक आय", min_value=0, max_value=300000, value=defaults['co_income'], step=2000)
            cibil = st.slider("CIBIL Credit Score / सिबिल स्कोर (300-900)", 300, 900, defaults['cibil'], step=10)

        with c2:
            loan_lakhs = st.slider("Loan Amount (₹ Lakhs) / ऋण राशि (लाख में)", 0.5, 50.0, defaults['loan_amt'], step=0.5)
            term = st.selectbox("Tenure (Months) / अवधि (माह)", [12, 24, 36, 60, 120, 180, 240, 360], index=[12, 24, 36, 60, 120, 180, 240, 360].index(defaults['term']))
            credit_hist = st.radio("Past Loan Repayment History / पिछला भुगतान", [1, 0], index=0 if defaults['credit_hist'] == 1 else 1, format_func=lambda x: "Clean Record (समय पर भुगतान)" if x==1 else "Past Delays/Defaulter (किस्त में देरी)")

        with c3:
            prop_area = st.selectbox("Property Area / स्थान", ["Rural", "Semiurban", "Urban"], index=["Rural", "Semiurban", "Urban"].index(defaults['area']), format_func=lambda x: "ग्रामीण (Rural)" if x=="Rural" else ("कस्बा (Semi-Urban)" if x=="Semiurban" else "शहरी (Urban)"))
            gender = st.selectbox("Gender / लिंग", ["Female", "Male"], index=["Female", "Male"].index(defaults['gender']), format_func=lambda x: "महिला (Female)" if x=="Female" else "पुरुष (Male)")
            self_emp = st.selectbox("Employment / रोज़गार", ["No", "Yes"], index=["No", "Yes"].index(defaults['self_emp']), format_func=lambda x: "नौकरीपेशा (Salaried)" if x=="No" else "व्यापारी/स्वरोज़गार (Self-Employed/MSME)")

    applicant_data = {
        'Gender': gender,
        'Married': defaults['married'],
        'Dependents': defaults['dependents'],
        'Education': defaults['education'],
        'Self_Employed': self_emp,
        'ApplicantIncome': app_income,
        'CoapplicantIncome': co_income,
        'LoanAmount': loan_lakhs,
        'Loan_Amount_Term': term,
        'CIBIL_Score': cibil,
        'Credit_History': credit_hist,
        'Property_Area': prop_area
    }

    if xai_engine is None:
        st.warning("⚠️ Model training in progress. Please check back in a moment.")
    else:
        result = xai_engine.predict_and_explain(applicant_data)
        
        # Decision Banner
        st.markdown("---")
        res_col1, res_col2 = st.columns([1.5, 2.5])
        
        with res_col1:
            if result['is_approved']:
                st.markdown("<div class='status-approved'>✓ " + ("LOAN APPROVED" if not is_hindi else "ऋण स्वीकृत") + "</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='status-review'>⚠ " + ("ACTION REQUIRED / REJECTED" if not is_hindi else "सुधार आवश्यक / अस्वीकृत") + "</div>", unsafe_allow_html=True)
            
            st.metric(
                label="Approval Likelihood (मंज़ूरी की संभावना)" if not is_hindi else "मंज़ूरी की संभावना",
                value=f"{result['approval_probability']}%",
                delta=f"{result['risk_band']}"
            )
            
            # FOIR gauge
            foir_pct = round(result['raw_foir'] * 100, 1)
            foir_status = "Safe (<50%)" if foir_pct <= 50 else "High (>50%)"
            st.caption(f"Estimated Monthly EMI Burden (FOIR): **{foir_pct}%** ({foir_status})")

        with res_col2:
            st.markdown("##### " + ("Why did the AI make this decision?" if not is_hindi else "AI ने यह फ़ैसला क्यों लिया? (स्पष्ट व्याख्या)"))
            
            col_p, col_n = st.columns(2)
            with col_p:
                st.markdown("<b style='color:#16A34A;'>✓ " + ("Key Strengths (सकारात्मक कारक):" if not is_hindi else "सकारात्मक कारक:") + "</b>", unsafe_allow_html=True)
                reasons_pos = result['explanations_hi']['positive_factors'] if is_hindi else result['explanations_en']['positive_factors']
                for p in reasons_pos:
                    st.markdown(f"• {p}")

            with col_n:
                st.markdown("<b style='color:#DC2626;'>✗ " + ("Primary Hurdles (रुकावटें):" if not is_hindi else "मुख्य रुकावटें:") + "</b>", unsafe_allow_html=True)
                reasons_neg = result['explanations_hi']['negative_factors'] if is_hindi else result['explanations_en']['negative_factors']
                for n in reasons_neg:
                    st.markdown(f"• {n}")

        # Counterfactual Recommendations
        st.markdown("---")
        st.markdown("#### 💡 " + ("How to Qualify or Improve Your Terms (भविष्य के लिए सुझाव)" if not is_hindi else "मंज़ूरी पाने व शर्तों को बेहतर बनाने के सरल उपाय"))
        
        cf_list = result['counterfactuals_hi'] if is_hindi else result['counterfactuals_en']
        for tip in cf_list:
            st.info(f"👉 **{tip}**")

# ----------------- TAB 2: BRANCH OFFICER & COMPLIANCE -----------------
with tab_officer:
    st.markdown("#### 🏛️ " + ("Institutional Underwriting & RBI Fair Lending Monitor" if not is_hindi else "बैंक शाखा प्रबंधन एवं RBI निष्पक्षता ऑडिट"))
    
    if fairness_auditor is not None:
        report = fairness_auditor.compute_fairness_report()
        
        c_sum1, c_sum2, c_sum3 = st.columns(3)
        c_sum1.metric("Audited Portfolio Size", f"{report['summary']['total_audited_records']} Loans")
        c_sum2.metric("Overall Portfolio Approval Rate", f"{report['summary']['overall_approval_rate']}%")
        c_sum3.metric("RBI Four-Fifths Threshold", "80.0% Parity")

        st.markdown("---")
        st.markdown("##### **1. Geographic Fairness (Rural/Gramin vs. Urban Parity)**")
        geo = report['geographic_fairness']
        
        g1, g2, g3 = st.columns([1, 1, 1.5])
        g1.metric("Rural Approval Rate", f"{geo['rural_approval_rate']}%")
        g2.metric("Urban Approval Rate", f"{geo['urban_approval_rate']}%")
        g3.metric(
            "Disparate Impact Ratio (DIR)",
            f"{geo['disparate_impact_ratio']}",
            delta=geo['status_badge'],
            delta_color="normal" if geo['is_compliant'] else "inverse"
        )
        
        st.markdown("##### **2. Gender Fairness (Female vs. Male Parity)**")
        gen = report['gender_fairness']
        gen1, gen2, gen3 = st.columns([1, 1, 1.5])
        gen1.metric("Female Approval Rate", f"{gen['female_approval_rate']}%")
        gen2.metric("Male Approval Rate", f"{gen['male_approval_rate']}%")
        gen3.metric(
            "Disparate Impact Ratio (DIR)",
            f"{gen['disparate_impact_ratio']}",
            delta=gen['status_badge'],
            delta_color="normal" if gen['is_compliant'] else "inverse"
        )

        # Visual Comparison Bar Chart
        st.markdown("##### **Demographic Parity Visualizer**")
        chart_data = pd.DataFrame({
            'Category': ['Rural (Gramin)', 'Semi-Urban', 'Urban', 'Female (Women SHG)', 'Male'],
            'Approval Rate (%)': [
                geo['rural_approval_rate'],
                geo['semiurban_approval_rate'],
                geo['urban_approval_rate'],
                gen['female_approval_rate'],
                gen['male_approval_rate']
            ]
        })
        st.bar_chart(chart_data.set_index('Category'))

        st.markdown("---")
        st.markdown("##### **Applicant SHAP Attribution Decomposition**")
        if xai_engine is not None:
            impacts = result['feature_impacts']
            sorted_feats = sorted(impacts.items(), key=lambda x: x[1])
            f_names = [f[0] for f in sorted_feats]
            f_vals = [f[1] for f in sorted_feats]
            
            fig, ax = plt.subplots(figsize=(8, 3.5))
            colors_list = ['#16A34A' if v > 0 else '#DC2626' for v in f_vals]
            ax.barh(f_names, f_vals, color=colors_list)
            ax.set_xlabel("SHAP Marginal Impact (Log-Odds Contribution)")
            ax.set_title("Exact Feature Attribution for Current Applicant")
            ax.grid(axis='x', linestyle='--', alpha=0.6)
            st.pyplot(fig)

# ----------------- TAB 3: ACCURACY REPORT -----------------
with tab_metrics:
    st.markdown("#### 📊 " + ("Model Accuracy & Validation Benchmarks" if not is_hindi else "मॉडल सटीकता व मूल्यांकन रिपोर्ट"))
    
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    report_path = os.path.join(BASE_DIR, "models", "accuracy_report.json")
    if os.path.exists(report_path):
        with open(report_path, 'r') as f:
            acc_data = json.load(f)
        
        m = acc_data['metrics']
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Overall Accuracy", f"{m['accuracy']*100:.2f}%")
        col_m2.metric("ROC-AUC Score", f"{m['roc_auc']:.4f}")
        col_m3.metric("Precision", f"{m['precision']*100:.2f}%")
        col_m4.metric("Recall", f"{m['recall']*100:.2f}%")
        
        st.markdown("---")
        st.markdown("##### **Confusion Matrix on Holdout Test Set**")
        cm = acc_data['confusion_matrix']
        cm_df = pd.DataFrame(
            [[cm['true_negatives'], cm['false_positives']],
             [cm['false_negatives'], cm['true_positives']]],
            columns=['Predicted Rejected', 'Predicted Approved'],
            index=['Actual Rejected', 'Actual Approved']
        )
        st.table(cm_df)

        st.json(acc_data)
    else:
        st.info("Accuracy report will appear once training completes.")
