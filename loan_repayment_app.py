import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import google.generativeai as genai

USD_TO_INR = 83.5

def fmt(value, is_inr):
    if is_inr:
        if value >= 1_00_00_000:
            return f"₹{value/1_00_00_000:.2f} Cr"
        elif value >= 1_00_000:
            return f"₹{value/1_00_000:.2f} L"
        else:
            return f"₹{value:,.0f}"
    else:
        return f"${value:,.2f}"

def calculate_achievements(loan_amount, monthly_payment, interest_rate, months):
    achievements = []
    time_achievements = {
        3: "Quarter Year Milestone 🌱", 6: "Half Year Champion 🌿",
        12: "One Year Strong 🌳", 24: "Two Year Warrior 🏆",
        36: "Three Year Victor 👑", 60: "Five Year Master 🎯",
        120: "Decade Dedication 💫"
    }
    amount_achievements = {
        0.1: "10% Progress Pioneer 🎯", 0.25: "Quarter Way Hero 🌟",
        0.5: "Halfway Champion 🏆", 0.75: "Three-Quarter Milestone 💫",
        0.9: "90% Achievement Unlocked 👑", 1.0: "Loan Conquered! 🎉"
    }
    remaining_balance = loan_amount
    monthly_rate = interest_rate / 1200
    for month in range(1, months + 1):
        interest = remaining_balance * monthly_rate
        principal = monthly_payment - interest
        remaining_balance -= principal
        if month in time_achievements:
            achievements.append({
                'month': month, 'title': time_achievements[month], 'type': 'time',
                'description': f"Successfully made payments for {month} months!",
                'amount_paid': loan_amount - remaining_balance,
                'percentage': ((loan_amount - remaining_balance) / loan_amount) * 100
            })
        progress = (loan_amount - remaining_balance) / loan_amount
        for threshold, title in amount_achievements.items():
            if progress >= threshold and not any(a['title'] == title for a in achievements):
                achievements.append({
                    'month': month, 'title': title, 'type': 'amount',
                    'description': f"Paid off {threshold*100:.0f}% of your loan!",
                    'amount_paid': loan_amount - remaining_balance,
                    'percentage': progress * 100
                })
    return sorted(achievements, key=lambda x: x['month'])

def suggest_repayment_period(loan_amount, monthly_income, monthly_expenses, interest_rate):
    annual_income = monthly_income * 12
    disposable_income = monthly_income - monthly_expenses
    loan_to_income_ratio = loan_amount / annual_income
    if loan_to_income_ratio <= 1:
        base_period = 60
    elif loan_to_income_ratio <= 2:
        base_period = 120
    elif loan_to_income_ratio <= 3:
        base_period = 180
    else:
        base_period = 240
    disposable_income_ratio = disposable_income / monthly_income
    if disposable_income_ratio > 0.5:
        base_period = max(base_period * 0.8, 36)
    elif disposable_income_ratio < 0.2:
        base_period = min(base_period * 1.2, 360)
    if interest_rate > 10:
        base_period = min(base_period * 1.1, 360)
    elif interest_rate < 5:
        base_period = max(base_period * 0.9, 36)
    return round(base_period)

def calculate_monthly_payment(loan_amount, interest_rate, months):
    r = interest_rate / 1200
    if r == 0:
        return loan_amount / months
    return loan_amount * (r * (1 + r)**months) / ((1 + r)**months - 1)

def calculate_affordability(monthly_payment, monthly_income, monthly_expenses):
    dti_ratio = monthly_payment / monthly_income
    total_burden = (monthly_payment + monthly_expenses) / monthly_income
    savings_potential = monthly_income - monthly_expenses - monthly_payment
    affordability_score = 0
    if dti_ratio < 0.28:
        affordability_score += 33
    elif dti_ratio < 0.43:
        affordability_score += 20
    if total_burden < 0.7:
        affordability_score += 33
    elif total_burden < 0.8:
        affordability_score += 20
    if savings_potential > monthly_income * 0.2:
        affordability_score += 34
    elif savings_potential > 0:
        affordability_score += 20
    return {
        'dti_ratio': dti_ratio, 'total_burden': total_burden,
        'savings_potential': savings_potential, 'affordability_score': affordability_score
    }

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Loan Repayment Predictor", layout="wide")
st.title("🏦 Loan Repayment Timeline Predictor")

# ── CURRENCY TOGGLE — big and visible at top ──────────────────────────────────
st.markdown("### 💱 Select Currency")
col_usd, col_inr, col_empty = st.columns([1, 1, 4])
with col_usd:
    usd_btn = st.button("🇺🇸  USD  ($)", use_container_width=True)
with col_inr:
    inr_btn = st.button("🇮🇳  INR  (₹)", use_container_width=True)

# Store currency in session state so it persists
if "currency" not in st.session_state:
    st.session_state.currency = "USD"
if usd_btn:
    st.session_state.currency = "USD"
if inr_btn:
    st.session_state.currency = "INR"

is_inr = st.session_state.currency == "INR"
sym    = "₹" if is_inr else "$"
curr_label = "INR (₹)" if is_inr else "USD ($)"

# Highlight active currency
if is_inr:
    st.success("🇮🇳 **Indian Rupee (INR)** selected — amounts in ₹ | Large values shown as Lakhs (L) and Crores (Cr)")
else:
    st.info("🇺🇸 **US Dollar (USD)** selected")

st.markdown("---")

# ── Inputs ────────────────────────────────────────────────────────────────────
if is_inr:
    default_loan     = 2000000    # 20 Lakh
    default_income   = 100000     # 1 Lakh/month
    default_expenses = 40000
    loan_min, loan_max, loan_step = 10000, 100000000, 10000
    inc_min,  inc_max,  inc_step  = 5000,  5000000,   1000
    exp_step = 1000
else:
    default_loan     = 250000
    default_income   = 15000
    default_expenses = 5000
    loan_min, loan_max, loan_step = 1000, 1000000, 1000
    inc_min,  inc_max,  inc_step  = 1000, 100000,  100
    exp_step = 100

col1, col2 = st.columns(2)

with col1:
    st.subheader("Loan Details")
    loan_amount   = st.number_input(
        f"Loan Amount ({sym})",
        min_value=loan_min, max_value=loan_max,
        value=default_loan, step=loan_step
    )
    interest_rate = st.slider("Interest Rate (%)", min_value=1.0, max_value=20.0, value=8.0, step=0.1)
    start_date    = st.date_input("Start Date", datetime.now())

with col2:
    st.subheader("Financial Information")
    monthly_income = st.number_input(
        f"Monthly Income ({sym})",
        min_value=inc_min, max_value=inc_max,
        value=default_income, step=inc_step
    )
    monthly_expenses = st.number_input(
        f"Monthly Expenses ({sym})",
        min_value=0, max_value=int(monthly_income),
        value=min(default_expenses, int(monthly_income)),
        step=exp_step
    )

# INR helper display
if is_inr:
    c1, c2, c3 = st.columns(3)
    c1.metric("Loan Amount", fmt(loan_amount, True))
    c2.metric("Monthly Income", fmt(monthly_income, True))
    c3.metric("Monthly Expenses", fmt(monthly_expenses, True))

# ── Calculate button ──────────────────────────────────────────────────────────
if st.button("Calculate Repayment Options", type="primary"):

    suggested_months = suggest_repayment_period(loan_amount, monthly_income, monthly_expenses, interest_rate)
    terms = {
        'Short':       max(suggested_months - 60, 36),
        'Recommended': suggested_months,
        'Long':        min(suggested_months + 60, 360)
    }

    options = {}
    for term_name, months in terms.items():
        mp  = calculate_monthly_payment(loan_amount, interest_rate, months)
        ti  = mp * months - loan_amount
        aff = calculate_affordability(mp, monthly_income, monthly_expenses)
        options[term_name] = {'months': months, 'monthly_payment': mp, 'total_interest': ti, 'affordability': aff}

    # ── Options cards ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📊 Repayment Options")
    cols = st.columns(3)

    for idx, (term_name, data) in enumerate(options.items()):
        with cols[idx]:
            st.markdown(f"### {term_name} Term")
            st.metric("Repayment Period",
                      f"{data['months']} months",
                      f"({data['months']/12:.1f} years)")
            st.metric("Monthly EMI",
                      fmt(data['monthly_payment'], is_inr),
                      f"{(data['monthly_payment']/monthly_income*100):.1f}% of income")
            if is_inr:
                st.caption(f"≈ ${data['monthly_payment']/USD_TO_INR:,.0f} USD/month")
            st.metric("Total Interest",
                      fmt(data['total_interest'], is_inr),
                      f"{(data['total_interest']/loan_amount*100):.1f}% of principal")
            st.progress(data['affordability']['affordability_score'] / 100)
            st.markdown(f"Affordability Score: **{data['affordability']['affordability_score']}%**")

    # ── Comparison chart ──────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📈 Monthly EMI Comparison")
    df_comp = pd.DataFrame([{
        'Term': t,
        'Monthly EMI': d['monthly_payment'],
        'Total Interest': d['total_interest'],
        'Total Cost': d['monthly_payment'] * d['months']
    } for t, d in options.items()])

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name='Monthly EMI',
        x=df_comp['Term'],
        y=df_comp['Monthly EMI'],
        text=df_comp['Monthly EMI'].apply(lambda x: fmt(x, is_inr)),
        textposition='auto',
    ))
    fig.update_layout(title="Monthly EMI Comparison", yaxis_title=f"Amount ({sym})", showlegend=True)
    st.plotly_chart(fig, use_container_width=True)

    # ── Pie + Cash flow ───────────────────────────────────────────────────────
    rec   = options['Recommended']
    mp    = rec['monthly_payment']
    mnths = rec['months']

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        fig_pie = go.Figure(data=[go.Pie(
            labels=['Principal', 'Interest'],
            values=[loan_amount, mp * mnths - loan_amount],
            hole=.3
        )])
        fig_pie.update_layout(title="Total Payment Breakdown")
        st.plotly_chart(fig_pie, use_container_width=True)

    with chart_col2:
        cf_data = pd.DataFrame({
            'Category': ['Income', 'Expenses', 'Loan EMI', 'Remaining'],
            'Amount': [monthly_income, monthly_expenses, mp,
                       monthly_income - monthly_expenses - mp]
        })
        fig_bar = px.bar(cf_data, x='Category', y='Amount',
                         title="Monthly Cash Flow",
                         labels={'Amount': f'Amount ({sym})'})
        st.plotly_chart(fig_bar, use_container_width=True)

    # ── Financial health ──────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("💹 Financial Health Analysis")
    h1, h2, h3 = st.columns(3)
    dti    = rec['affordability']['dti_ratio']
    burden = rec['affordability']['total_burden']
    sav    = rec['affordability']['savings_potential']

    with h1:
        st.metric("Debt-to-Income Ratio", f"{dti*100:.1f}%", "Good" if dti < 0.43 else "High")
    with h2:
        st.metric("Total Monthly Burden", f"{burden*100:.1f}%", "Good" if burden < 0.8 else "High")
    with h3:
        st.metric("Monthly Savings Potential", fmt(sav, is_inr), "After EMI")

    # ── Achievements ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🏆 Loan Payment Achievements")
    term_achievements = {
        t: calculate_achievements(loan_amount, d['monthly_payment'], interest_rate, d['months'])
        for t, d in options.items()
    }

    term_tabs = st.tabs(list(options.keys()))
    for tab, term_name in zip(term_tabs, options.keys()):
        with tab:
            ach  = term_achievements[term_name]
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=[a['month'] for a in ach],
                y=[a['percentage'] for a in ach],
                mode='markers+text',
                marker=dict(size=20, symbol='star',
                            color=['gold' if a['type'] == 'amount' else 'silver' for a in ach]),
                text=[a['title'].split()[0] for a in ach],
                textposition='top center',
                name='Achievements'
            ))
            prog_m = list(range(0, options[term_name]['months'] + 1))
            prog_v = [min(100 * i * options[term_name]['monthly_payment'] / loan_amount, 100) for i in prog_m]
            fig2.add_trace(go.Scatter(x=prog_m, y=prog_v, mode='lines',
                                      line=dict(color='rgba(0,100,255,0.3)'), name='Loan Progress'))
            fig2.update_layout(title=f"Achievement Timeline — {term_name} Term",
                               xaxis_title="Months", yaxis_title="Loan Progress (%)",
                               yaxis_range=[0, 105])
            st.plotly_chart(fig2, use_container_width=True)

            with st.expander("View Detailed Achievements"):
                for a in ach:
                    month_val = a['month']
                    years_val = round(a['month'] / 12, 1)
                    amount_val = fmt(a['amount_paid'], is_inr)
                    pct_val = round(a['percentage'], 1)
                    desc_val = a['description']
                    title_val = a['title']
                    st.markdown(f"### {title_val}")
                    st.markdown(f"- **Month:** {month_val} ({years_val} years)")
                    st.markdown(f"- **Amount Paid:** {amount_val}")
                    st.markdown(f"- **Progress:** {pct_val}%")
                    st.markdown(f"- {desc_val}")
                    st.markdown("---")

            upcoming = next((a for a in ach if a['month'] > 1), None)
            if upcoming:
                st.markdown("### 🎯 Next Achievement")
                st.info(f"**{upcoming['title']}** — unlocks in {upcoming['month']-1} months "
                        f"({upcoming['percentage']:.1f}% done, {fmt(upcoming['amount_paid'], is_inr)} paid)")

    # ── Recommendations ───────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("💡 Recommendations")
    score = rec['affordability']['affordability_score']
    if score >= 80:
        st.success("✅ This loan is within your affordable range.")
    elif score >= 60:
        st.warning("⚠️ This loan is manageable but may strain your finances.")
    else:
        st.error("❌ This loan may be difficult with your current financial situation.")

    recs = []
    if dti > 0.43:    recs.append("Consider a longer term to reduce monthly EMI")
    if burden > 0.8:  recs.append("Look for ways to reduce monthly expenses")
    if sav < monthly_income * 0.1: recs.append("Build an emergency fund before taking this loan")
    if recs:
        st.markdown("**Suggested Actions:**")
        for r in recs:
            st.markdown(f"- {r}")

    # INR-specific tips
    if is_inr:
        st.markdown("---")
        st.subheader("🇮🇳 India-Specific Tips")
        st.info("""
**Tax Benefits:**
- **Section 24(b):** Home loan interest deduction up to ₹2 L/year
- **Section 80C:** Principal repayment deduction up to ₹1.5 L/year
- **PMAY / CLSS:** First-time buyers may get interest subsidy under Pradhan Mantri Awas Yojana

**Smart Repayment:**
- Even ₹5,000–₹10,000 extra per month as prepayment can cut your tenure by years
- Compare EAR (Effective Annual Rate), not just the headline rate, across banks
- SBI, HDFC, ICICI home loan rates typically range 8.5%–9.5% — negotiate!
""")

# ── AI Recommendations ────────────────────────────────────────────────────────
st.markdown("---")
import os
api_key = os.environ.get("GOOGLE_API_KEY")

def generate_response(prompt):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        return model.start_chat().send_message(prompt).text
    except Exception as e:
        return f"Error: {e}"

st.write("Get AI-powered repayment advice based on your inputs")
if st.button("Get AI Recommendation"):
    cur_word = "Indian Rupees (INR)" if is_inr else "US Dollars (USD)"
    prompt = (
        f"A user has a loan of {fmt(loan_amount, is_inr)} ({cur_word}) at {interest_rate}% interest. "
        f"Their monthly income is {fmt(monthly_income, is_inr)} and expenses are {fmt(monthly_expenses, is_inr)}. "
        f"What repayment strategies do you recommend to avoid financial trouble? "
        + ("Mention Indian tax benefits like Section 24(b), 80C, and PMAY if relevant." if is_inr else "")
    )
    st.write(generate_response(prompt))