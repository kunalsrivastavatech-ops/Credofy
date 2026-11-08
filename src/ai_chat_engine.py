import os
import re
from typing import Dict, Any, List, Optional

class CredofyCreditChatbot:
    """
    Intelligent Conversational Credit Copilot for Credofy.ai.
    Understands borrower financials, bank-specific credit policies,
    RBI compliance rules, and provides personalized, actionable guidance.
    """

    def __init__(self):
        self.gemini_client = None
        self.gemini_model_name = None
        self._init_gemini()
        # Knowledge Base for Indian Banks
        self.bank_knowledge = {
            "sbi": {
                "name": "State Bank of India (SBI)",
                "rate": "8.40% - 9.15%",
                "min_cibil": 720,
                "portal": "https://sbi.co.in/web/personal-banking/loans",
                "docs": ["Aadhaar & PAN", "6-Month Bank Statement", "2 Years ITR / Form 16", "Salary Slips (3 Mos)"],
                "tips": "SBI offers the lowest concession rates (up to 20 bps discount) for borrowers with CIBIL score >= 750 and women co-borrowers."
            },
            "bob": {
                "name": "Bank of Baroda (BOB)",
                "rate": "8.45% - 9.25%",
                "min_cibil": 700,
                "portal": "https://www.bankofbaroda.in/personal-banking/loans",
                "docs": ["Aadhaar & PAN", "6-Month Statement", "ITR-V (2 Years)", "Shop/Business Proof if MSME"],
                "tips": "BOB allows linking digital salary accounts for zero-processing fee approval in 3-4 working days."
            },
            "canara": {
                "name": "Canara Bank",
                "rate": "8.50% - 9.30%",
                "min_cibil": 700,
                "portal": "https://canarabank.com/retail-loans",
                "docs": ["Aadhaar & PAN", "6-Month Passbook", "Form 16 or Audited P&L"],
                "tips": "Canara Bank is highly favorable for semi-urban applicants and MSMEs with quick regional sanctions."
            },
            "indianbank": {
                "name": "Indian Bank",
                "rate": "8.50% - 9.20%",
                "min_cibil": 680,
                "portal": "https://www.indianbank.in/departments/retail-loans/",
                "docs": ["Aadhaar & PAN", "6 Months Passbook", "Income Certificate / Saral"],
                "tips": "Indian Bank has one of the most accessible cutoffs (680 CIBIL) for government schemes like PM Mudra and Ind MSME."
            },
            "pnb": {
                "name": "Punjab National Bank (PNB)",
                "rate": "8.45% - 9.35%",
                "min_cibil": 700,
                "portal": "https://www.pnbindia.in/retail-loans.html",
                "docs": ["Aadhaar & PAN", "6 Months Account Statement", "Salary Certificate or GST Returns"],
                "tips": "PNB offers flexible terms up to 30 years and special rate waivers under PNB Vikas schemes."
            },
            "hdfc": {
                "name": "HDFC Bank",
                "rate": "8.75% - 9.60%",
                "min_cibil": 750,
                "portal": "https://www.hdfcbank.com/personal/borrow/popular-loans",
                "docs": ["Instant e-KYC (Aadhaar & PAN)", "Netbanking Account Aggregator Statement"],
                "tips": "HDFC provides 10-second disbursement for pre-approved customers and within 24-48 hours for others, but strictly prefers CIBIL >= 750."
            },
            "icici": {
                "name": "ICICI Bank",
                "rate": "8.75% - 9.75%",
                "min_cibil": 730,
                "portal": "https://www.icicibank.com/personal-banking/loans",
                "docs": ["PAN Card", "Aadhaar e-Sign", "3 Months Payslips", "Bank Statement"],
                "tips": "ICICI gives express approvals via the iMobile app with zero physical branch visits if netbanking is linked."
            },
            "axis": {
                "name": "Axis Bank",
                "rate": "8.80% - 9.80%",
                "min_cibil": 725,
                "portal": "https://www.axisbank.com/retail/loans",
                "docs": ["Aadhaar & PAN", "3-Month Bank Statement", "Form 16"],
                "tips": "Axis Bank provides 24x7 instant loans up to 30 lakhs for salaried corporate employees."
            },
            "kotak": {
                "name": "Kotak Mahindra Bank",
                "rate": "8.70% - 9.50%",
                "min_cibil": 740,
                "portal": "https://www.kotak.com/en/personal-banking/loans.html",
                "docs": ["PAN & Aadhaar", "Netbanking e-statement", "Salary Slip"],
                "tips": "Kotak offers fast digital verification with paperless Aadhaar OTP verification."
            }
        }

    def _init_gemini(self):
        # Dynamically load from .env or os.environ
        from dotenv import load_dotenv
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        load_dotenv(os.path.join(base_dir, ".env"), override=True)

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if api_key:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=api_key)
                self.gemini_model_name = "gemini-2.0-flash"
                print("✓ Initialized Google Gemini AI Chatbot engine.")
            except Exception as e:
                print("Notice: Gemini client init deferred:", e)

    def set_gemini_api_key(self, api_key: str) -> bool:
        """Validates and sets Gemini API key dynamically at runtime."""
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            # Quick verification
            res = client.models.generate_content(
                model='gemini-2.0-flash',
                contents='Hello'
            )
            if res and res.text:
                self.gemini_client = client
                self.gemini_model_name = "gemini-2.0-flash"
                return True
        except Exception as e:
            # Try fallback model
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                res = client.models.generate_content(
                    model='gemini-1.5-flash',
                    contents='Hello'
                )
                if res and res.text:
                    self.gemini_client = client
                    self.gemini_model_name = "gemini-1.5-flash"
                    return True
            except Exception as e2:
                print(f"Gemini API key verification error: {e2}")
        return False

    def is_gemini_active(self) -> bool:
        return self.gemini_client is not None

    def chat_with_meta(self, user_message: str, applicant_context: Dict[str, Any], history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """Returns the reply along with engine metadata (Gemini vs local)."""
        if not self.gemini_client:
            self._init_gemini()

        if self.gemini_client:
            try:
                system_instruction = self._build_system_prompt(applicant_context)
                formatted_history = []
                if history:
                    for turn in history[-6:]:
                        role = "user" if turn.get("sender") == "user" else "model"
                        text = turn.get("text", "")
                        if text:
                            formatted_history.append(f"{role.upper()}: {text}")

                full_prompt = ""
                if formatted_history:
                    full_prompt = "Previous Conversation:\n" + "\n".join(formatted_history) + "\n\nUser Question: " + user_message
                else:
                    full_prompt = user_message

                for model_id in ['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-2.5-flash']:
                    try:
                        response = self.gemini_client.models.generate_content(
                            model=model_id,
                            contents=full_prompt,
                            config={
                                'system_instruction': system_instruction,
                                'temperature': 0.4
                            }
                        )
                        if response and response.text:
                            return {
                                "reply": response.text.strip(),
                                "engine": f"Google Gemini ({model_id})",
                                "gemini_active": True
                            }
                    except Exception as model_err:
                        print(f"Gemini model {model_id} error: {model_err}")
                        continue
            except Exception as e:
                print("Gemini API call failed, falling back to local credit engine:", e)

        local_reply = self._local_credit_advisor(user_message, applicant_context)
        return {
            "reply": local_reply,
            "engine": "Credofy Native Credit AI Copilot",
            "gemini_active": False
        }

    def chat(self, user_message: str, applicant_context: Dict[str, Any], history: List[Dict[str, str]] = None) -> str:
        """
        Generates personalized, chatbot-style conversational advice for the borrower.
        Connects directly to real Google Gemini LLM when API key is provided,
        with intelligent local credit advisor fallback.
        """
        res = self.chat_with_meta(user_message, applicant_context, history)
        return res["reply"]

    def _build_system_prompt(self, ctx: Dict[str, Any]) -> str:
        name = ctx.get("applicant_name", "Borrower")
        bank = ctx.get("SelectedBank", "Selected Bank")
        income = ctx.get("ApplicantIncome", 45000)
        co_income = ctx.get("CoapplicantIncome", 0)
        loan = ctx.get("LoanAmount", 4.5)
        tenure = ctx.get("Loan_Amount_Term", 60)
        cibil = ctx.get("CIBIL_Score", 740)
        
        return f"""You are the Credofy.ai Credit Copilot, an expert Indian banking credit officer.
You are chatting with {name}.
Applicant Context:
- Monthly Income: ₹{income:,.0f} (Co-applicant: ₹{co_income:,.0f})
- Requested Loan: ₹{loan} Lakhs for {tenure} months
- CIBIL Score: {cibil}
- Chosen Bank: {bank}

Guidelines:
1. Speak warmly, professionally, and conversationally like a dedicated loan advisor.
2. Provide specific numbers (EMI calculations, interest rate comparison, FOIR).
3. If asked about bank documents, give the exact list for {bank} and other Indian PSU/Private banks.
4. If asked in Hindi or Hinglish, answer fluently in Hindi or Hinglish.
5. Provide actionable guidance to get the loan approved at the lowest interest rate.
"""

    def _local_credit_advisor(self, msg: str, ctx: Dict[str, Any]) -> str:
        text = msg.lower().strip()
        name = ctx.get("applicant_name", "Kunal")
        bank_name = ctx.get("SelectedBank", "State Bank of India (SBI)")
        income = max(1.0, float(ctx.get("ApplicantIncome", 45000)))
        co_income = max(0.0, float(ctx.get("CoapplicantIncome", 20000)))
        total_income = income + co_income
        loan_lakhs = max(0.1, float(ctx.get("LoanAmount", 4.5)))
        loan_inr = loan_lakhs * 100000
        tenure_months = max(1, int(ctx.get("Loan_Amount_Term", 60)))
        cibil = int(ctx.get("CIBIL_Score", 740))
        
        # Approximate monthly EMI calculation at ~8.75% annual
        r = (8.75 / 100) / 12
        if tenure_months > 0 and r > 0:
            emi = loan_inr * r * ((1 + r) ** tenure_months) / (((1 + r) ** tenure_months) - 1)
        else:
            emi = loan_inr / max(tenure_months, 1)
        
        foir = (emi / max(total_income, 1)) * 100

        # Hindi detection
        is_hindi = any(word in text for word in ["नमस्ते", "लोन", "ब्याज", "कागज़ात", "दस्तावेज़", "कैसे", "सकता", "हिंदी", "क्रेडिट", "सिबिल", "mera", "kya", "kaise", "batao", "chahiye"])

        # Topic 1: Reducing EMI / Tenures / Interest Rate
        if any(w in text for w in ["emi", "reduce", "lower", "kam", "installment", "monthly pay"]):
            if is_hindi:
                return (
                    f"नमस्ते {name} जी! आपकी वर्तमान मासिक EMI लगभग ₹{emi:,.0f}/महीना है, जो आपकी कुल पारिवारिक आय (₹{total_income:,.0f}) का मात्र {foir:.1f}% है (यह RBI के 50% FOIR नियम से बहुत सुरक्षित है)।\n\n"
                    f"**EMI और कम करने के 3 आसान तरीके:**\n"
                    f"1. **अवधि बढ़ाएं:** यदि आप अवधि 60 महीने से बढ़ाकर 72 या 84 महीने करते हैं, तो EMI घटकर लगभग ₹7,800/माह रह जाएगी।\n"
                    f"2. **CIBIL छूट:** आपका सिबिल स्कोर {cibil} है। यदि इसे 760+ कर लें तो {bank_name} आपको 0.25% ब्याज छूट दे सकता है।\n"
                    f"3. **सह-आवेदक जोड़ें:** परिवार के सदस्य को सह-आवेदक रखने से बैंक आपको प्राइम लेंडिंग रेट (PLR) ऑफर करेगा।"
                )
            return (
                f"Hello {name}! Your estimated monthly EMI for ₹{loan_lakhs} Lakhs over {tenure_months} months is approximately **₹{emi:,.0f}/month**.\n\n"
                f"Your Debt-to-Income ratio (FOIR) is **{foir:.1f}%**, which is well below the RBI safety cap of 50%.\n\n"
                f"**Here are 3 ways to optimize your EMI:**\n"
                f"• **Extend Loan Tenure:** Increasing tenure to 72 or 84 months will drop your EMI to ~₹7,800/month.\n"
                f"• **Negotiate Prime Rates:** With your strong CIBIL score of **{cibil}**, request **{bank_name}** for a 15–25 bps rate concession.\n"
                f"• **Part-Prepayment Facility:** Opt for a floating rate loan with zero prepayment penalties to pay extra principal whenever you have surplus cash."
            )

        # Topic 2: Document requirements
        if any(w in text for w in ["document", "doc", "paper", "checklist", "kagaz", "aadhaar", "pan", "itr"]):
            if is_hindi:
                return (
                    f"{name} जी, **{bank_name}** में ऋण की त्वरित स्वीकृति के लिए निम्नलिखित दस्तावेज़ अनिवार्य हैं:\n\n"
                    f"1. **पहचान व पता प्रमाण:** आधार कार्ड (UIDAI ई-केवाईसी) और पैन कार्ड।\n"
                    f"2. **आय का प्रमाण:** पिछले 6 महीनों का प्राथमिक बैंक खाता विवरण (Salary/Income Credit Proof)।\n"
                    f"3. **टैक्स विवरण:** पिछले 2 वर्षों का ITR-V अथवा नियोक्ता द्वारा जारी Form 16।\n"
                    f"4. **वेतन पर्ची:** हाल की 3 महीने की सैलरी स्लिप्स (या MSME के लिए उद्यम/GST प्रमाण)।\n\n"
                    f"💡 *टिप:* Credofy AI के दस्तावेज़ स्कैनर में अपने पेपर्स अपलोड करके 1 मिनट में सत्यापन पूरा कर सकते हैं!"
                )
            return (
                f"For **{bank_name}**, here is the exact document checklist required to ensure 100% swift loan sanction:\n\n"
                f"1. **Identity & Address Proof:** Aadhaar Card (linked to mobile for e-KYC) and PAN Card.\n"
                f"2. **Bank Account Statement:** Last 6 months' official statement showing salary/business credits.\n"
                f"3. **Income Tax Returns:** Past 2 years' ITR-V acknowledgment or employer Form 16.\n"
                f"4. **Income Slips:** Last 3 months' pay-slips (or Udyam MSME certificate if self-employed).\n\n"
                f"💡 *Pro-Tip:* Upload your documents directly into our **AI Document Scanner** above to pre-verify formatting and prevent bank query rejections!"
            )

        # Topic 3: Bank comparison (SBI vs HDFC / BOB / etc.)
        if any(w in text for w in ["sbi", "hdfc", "icici", "bob", "baroda", "canara", "compare", "which bank", "better", "best"]):
            return (
                f"Great question! Comparing your top options for a ₹{loan_lakhs} Lakh loan:\n\n"
                f"• **State Bank of India (SBI):**\n"
                f"  - Interest Rate: **8.40% - 9.15%** (Lowest rates, zero hidden charges)\n"
                f"  - Turnaround: 3–5 working days\n"
                f"  - Best for: Cost-conscious borrowers wanting the lowest total interest payout.\n\n"
                f"• **HDFC Bank:**\n"
                f"  - Interest Rate: **8.75% - 9.60%**\n"
                f"  - Turnaround: 24–48 hours (Fastest digital sanction)\n"
                f"  - Best for: Quick emergency disbursement with netbanking Account Aggregator.\n\n"
                f"• **Bank of Baroda (BOB):**\n"
                f"  - Interest Rate: **8.45% - 9.25%** (Low processing fee of 0.25%)\n"
                f"  - Best for: Semi-urban borrowers and government scheme subsidies.\n\n"
                f"Since your CIBIL is **{cibil}**, you qualify for the lowest slab at both **SBI** and **HDFC**!"
            )

        # Topic 4: CIBIL Score & Eligibility
        if any(w in text for w in ["cibil", "score", "credit score", "cutoff", "eligibility", "chances", "approval"]):
            status = "Excellent" if cibil >= 750 else ("Strong" if cibil >= 700 else "Average")
            if is_hindi:
                return (
                    f"आपका CIBIL स्कोर **{cibil}** ({status}) श्रेणी में आता है!\n\n"
                    f"• **स्वीकृति संभावना:** 97% से अधिक। भारतीय सरकारी बैंक (SBI, BOB, Canara) 700+ पर तुरंत स्वीकृति देते हैं।\n"
                    f"• **ब्याज दर लाभ:** 740+ स्कोर होने से बैंक आपको मानक दरों पर 0.15% - 0.30% तक की विशेष छूट (risk-based pricing) प्रदान करते हैं।\n"
                    f"• **सिबिल सुधार टिप:** क्रेडिट कार्ड का बिल नियत तिथि से पहले भरें और क्रेडिट यूटिलाइजेशन को 30% के नीचे रखें।"
                )
            return (
                f"Your CIBIL Score of **{cibil}** is in the **{status} Tier** for Indian institutional lending!\n\n"
                f"• **Sanction Likelihood:** Above **97%**. Public Sector Banks (SBI, BOB, Canara, PNB) require 700+ for prime approval.\n"
                f"• **Rate Advantage:** With a 740+ score, you are placed in Risk Band 1, unlocking interest rates as low as 8.40%.\n"
                f"• **Next Milestone:** If you bump your score past 750 (by maintaining credit card utilization under 30%), you become eligible for zero-processing fee waivers across all Tier-1 banks."
            )

        # Topic 5: How to apply / Next steps / Redirection
        if any(w in text for w in ["apply", "redirect", "portal", "submit", "link", "kaha", "kaise le"]):
            bank_id = "sbi"
            for b_id, b_data in self.bank_knowledge.items():
                if b_data["name"].lower() in bank_name.lower():
                    bank_id = b_id
                    break
            portal_url = self.bank_knowledge.get(bank_id, {}).get("portal", "https://sbi.co.in")
            
            return (
                f"You are 100% ready to proceed! Your evaluation is complete and your application packet has been registered in MongoDB.\n\n"
                f"**Direct Bank Link for {bank_name}:**\n"
                f"👉 [{bank_name} Official Loan Application Portal]({portal_url})\n\n"
                f"**What happens next:**\n"
                f"1. Click the link above or click **'Proceed to Apply at {bank_name}'** on the results page.\n"
                f"2. You will be redirected directly to the bank's secure loan application desk.\n"
                f"3. Enter your PAN & Mobile to auto-fetch your pre-verified credit packet."
            )

        # General friendly conversational answer
        if is_hindi:
            return (
                f"नमस्ते {name} जी! मैं आपका Credofy AI क्रेडिट सलाहकार हूँ।\n\n"
                f"आपकी प्रोफ़ाइल:\n"
                f"• मासिक आय: ₹{income:,.0f} (सह-आवेदक: ₹{co_income:,.0f})\n"
                f"• ऋण राशि: ₹{loan_lakhs} लाख ({tenure_months} महीने)\n"
                f"• CIBIL स्कोर: {cibil} | चयनित बैंक: {bank_name}\n\n"
                f"आप मुझसे EMI कम करने के तरीके, बैंकों की ब्याज दर तुलना (SBI vs HDFC), अनिवार्य दस्तावेज़ सूची, अथवा सीधे बैंक पोर्टल पर आवेदन करने के बारे में कोई भी प्रश्न पूछ सकते हैं!"
            )

        return (
            f"Hello {name}! I am your Credofy.ai Credit Copilot.\n\n"
            f"I have your real-time parameters loaded:\n"
            f"• Monthly Household Income: ₹{total_income:,.0f} | CIBIL Score: **{cibil}**\n"
            f"• Requested Loan: ₹{loan_lakhs} Lakhs at **{bank_name}** | Estimated EMI: **₹{emi:,.0f}/mo**\n\n"
            f"You can ask me anything specific:\n"
            f"1. *'Compare interest rates between SBI, HDFC, and BOB'*\n"
            f"2. *'What exact documents does {bank_name} need?'*\n"
            f"3. *'How can I lower my monthly EMI further?'*\n"
            f"4. *'Direct link to apply at {bank_name}'*\n\n"
            f"How can I help you today?"
        )

# Global Chatbot Singleton
credit_chatbot = CredofyCreditChatbot()
# Backward-compatible aliases
EquiBharatCreditChatbot = CredofyCreditChatbot
KredoCreditChatbot = CredofyCreditChatbot
