import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

class IFRS9ECLEngine:
    def __init__(self, portfolio_df):
        self.df = portfolio_df.copy()
        
    def stage_allocator(self):
        """Partitions assets into regulatory stages based on delinquency days past due (DPD)."""
        conditions = [
            (self.df['days_past_due'] <= 30),
            (self.df['days_past_due'] > 30) & (self.df['days_past_due'] <= 90),
            (self.df['days_past_due'] > 90)
        ]
        stages = [1, 2, 3]
        self.df['Stage'] = np.select(conditions, stages, default=1)
        return self.df

    def calculate_ecl(self, macro_scenario_factor=1.0):
        """Computes exact credit impairments mapping to 12-Month or Lifetime expectations."""
        self.stage_allocator()
        
        ecl_vector = []
        for idx, row in self.df.iterrows():
            # Apply forward-looking macroeconomic multiplier capped at 100% default probability
            pd_12m_adj = min(1.0, row['pd_12m'] * macro_scenario_factor)
            pd_life_adj = min(1.0, row['pd_lifetime'] * macro_scenario_factor)
            
            if row['Stage'] == 1:
                # Stage 1: Asset performing normally. Calculate 12-Month ECL.
                ecl = row['ead'] * row['lgd'] * pd_12m_adj
            elif row['Stage'] == 2:
                # Stage 2: Significant Increase in Credit Risk (SICR). Calculate Lifetime ECL.
                ecl = row['ead'] * row['lgd'] * pd_life_adj
            else:
                # Stage 3: Asset Impaired / Default state. PD becomes absolute.
                ecl = row['ead'] * row['lgd'] * 1.0
                
            ecl_vector.append(ecl)
            
        self.df['Calculated_ECL'] = ecl_vector
        return self.df

# --- STREAMLIT USER INTERFACE ---
st.set_page_config(page_title="IFRS 9 Credit Risk Engine", layout="wide")
st.title("IFRS 9 Expected Credit Loss (ECL) Impairment Engine")
st.markdown("Assess bank credit risk portfolios, evaluate Significant Increase in Credit Risk (SICR) triggers, and apply forward-looking Eurozone macroeconomic shock factors.")

st.sidebar.header("Eurozone Macro Forecast Controls")
st.markdown("The ECB and CSSF mandate forward-looking credit assessments. Adjust the macro multiplier below to simulate structural market changes:")
macro_multiplier = st.sidebar.slider("Macroeconomic Stress Multiplier (PD Scaling)", 1.0, 5.0, 1.5, step=0.1)

st.sidebar.subheader("Default Asset Ledger Configuration")
total_loans = st.sidebar.slider("Simulated Portfolio Corporate Count", 50, 500, 100)

# Generate synthetic bank portfolio dataset for modeling
np.random.seed(42)
ead_pool = np.random.uniform(100000, 5000000, total_loans) # Exposure at Default
lgd_pool = np.random.uniform(0.30, 0.60, total_loans)      # Loss Given Default (Collateralized)
pd_12m_pool = np.random.uniform(0.01, 0.05, total_loans)   # 12-Month Baseline PD
pd_life_pool = pd_12m_pool * np.random.uniform(3.0, 6.0, total_loans) # Lifetime Cumulative PD

# Randomly inject delinquency vectors to simulate portfolio distress
dpd_pool = np.random.choice([0, 10, 15, 45, 60, 120], size=total_loans, p=[0.70, 0.12, 0.08, 0.05, 0.03, 0.02])

raw_data = pd.DataFrame({
    'loan_id': [f"LN_{str(i).zfill(4)}" for i in range(1, total_loans + 1)],
    'ead': ead_pool,
    'lgd': lgd_pool,
    'pd_12m': pd_12m_pool,
    'pd_lifetime': pd_life_pool,
    'days_past_due': dpd_pool
})

# Run Credit Risk Calculations
engine = IFRS9ECLEngine(raw_data)
portfolio_calculated = engine.calculate_ecl(macro_scenario_factor=macro_multiplier)

total_portfolio_ead = portfolio_calculated['ead'].sum()
total_portfolio_ecl = portfolio_calculated['Calculated_ECL'].sum()
ecl_coverage_ratio = (total_portfolio_ecl / total_portfolio_ead) * 100

# Executive KPI Block
c1, c2, c3 = st.columns(3)
c1.metric("Total Outstanding Credit Exposure (EAD)", f"€{total_portfolio_ead:,.2f}")
c2.metric("Total Required Capital Provision (ECL)", f"€{total_portfolio_ecl:,.2f}")
c3.metric("Portfolio ECL Provision Coverage", f"{ecl_coverage_ratio:.2f}%")

st.markdown("---")
chart_col, details_col = st.columns([2, 1])

st.markdown(
    """
    <style>
    @import url('https://cdnfonts.com');
    
    /* Apply LaTeX font to the entire app body, markdown text, and paragraphs */
    html, body, [data-testid="stMarkdownContainer"] p {
        font-family: 'Latin Modern Roman', 'Computer Modern Roman', 'Times New Roman', serif !important;
        font-size: 17px !important;
    }
    
    /* Apply LaTeX font to headers to give it that academic paper layout */
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Latin Modern Roman', 'Computer Modern Roman', 'Times New Roman', serif !important;
        font-weight: bold !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)
with chart_col:
    st.subheader("Credit Quality Staging & Capital Allocation Matrix")
    
    # Calculate aggregated statistics for visual validation
    stage_summary = portfolio_calculated.groupby('Stage').agg({
        'ead': 'sum',
        'Calculated_ECL': 'sum'
    }).reset_index()
    
    fig = go.Figure()
    fig.add_trace(go.Bar(x=stage_summary['Stage'].map(lambda x: f"Stage {x}"), y=stage_summary['ead'], name='Total Credit Exposure (EAD)', marker_color='#1f77b4'))
    fig.add_trace(go.Bar(x=stage_summary['Stage'].map(lambda x: f"Stage {x}"), y=stage_summary['Calculated_ECL'], name='Allocated Credit Provision (ECL)', marker_color='#d62728'))
    
    fig.update_layout(barmode='group', xaxis_title="Regulatory Credit Classification", yaxis_title="Volume (€)", margin=dict(l=20, r=20, t=20, b=20), height=380)
    st.plotly_chart(fig, use_container_width=True)

with details_col:
    st.subheader("Asset Staging Concentration")
    stage_counts = portfolio_calculated['Stage'].value_counts()
    
    for s in [1, 2, 3]:
        count = stage_counts.get(s, 0)
        percentage = (count / total_loans) * 100
        stage_desc = {
            1: "Performing Normally (12-Mo ECL)",
            2: "Under Stressed Strain (Lifetime ECL)",
            3: "Technical Default (100% Realized PD)"
        }[s]
        
        st.markdown(f"**Stage {s} - {stage_desc}:**")
        st.write(f"Facility Count: `{count}` firms (`{percentage:.1f}%` of total ledger)")
        st.markdown("---")
