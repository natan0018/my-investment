import streamlit as st
import pandas as pd
import requests
import json
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf
from datetime import datetime, date, timedelta

# --- CONFIG ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTLlubNZGApf3LWUI3n0hRN6SNkyBdJmvNltHv_lLOO5FiAnnPG5NjvUAGRGE15N0sJ4q0VPFd_TjrE/pub?output=csv" 

DEPOSIT_1_START = date(2025, 3, 1)
DEPOSIT_1_PRINCIPAL = 200000
DEPOSIT_1_INTEREST = 0.045
DEPOSIT_2_START = date(2026, 3, 16)
DEPOSIT_2_PRINCIPAL = 230000
DEPOSIT_2_INTEREST = 0.048

st.set_page_config(page_title="My Investment Portfolio", layout="wide")

# --- CSS ---
st.markdown("""
    <style>
    .main { direction: rtl; }
    html, body, [class*="css"] { font-family: 'Assistant', sans-serif; direction: rtl; text-align: right; }
    .stApp { background-color: #050505; color: #e0e0e0; }
    div[data-testid="stMetric"] { background-color: #101010; border-right: 4px solid #00d4ff; border-radius: 4px; padding: 15px; }
    div[data-testid="stMetricValue"] { color: #00ff41 !important; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def get_historical_fx_rates(dates_list):
    """מושך שערי חליפין היסטוריים באופן אוטומטי"""
    try:
        start_date = min(dates_list)
        end_date = max(dates_list) + timedelta(days=4)
        # USDIILS=X הוא הטיקר לשער דולר שקל ב-Yahoo Finance
        data = yf.download("ILS=X", start=start_date, end=end_date, progress=False)['Close']
        # מחזיר סדרה של תאריכים ושערים
        return data
    except:
        return None

@st.cache_data(ttl=600)
def load_and_process(url):
    try:
        df = pd.read_csv(url)
        df.columns = [c.strip() for c in df.columns]
        df = df.dropna(subset=['Date'])
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        
        # --- אוטומציה של שער החליפין ---
        unique_dates = df['Date'].unique()
        fx_data = get_historical_fx_rates(unique_dates)
        
        def get_rate_for_date(d):
            try:
                # מחפש את השער הכי קרוב לתאריך (למקרה של סופ"ש שבו אין מסחר)
                return float(fx_data.asof(pd.Timestamp(d)))
            except:
                return 3.7 # Fallback במקרה של תקלה

        df['FX_Rate'] = df['Date'].apply(get_rate_for_date)
        # -----------------------------------

        def sum_dca(val, fx_rate):
            if pd.isna(val) or val == "{}" or val == "": return 0
            try:
                d = json.loads(str(val).replace("'", '"'))
                return sum(float(v) * fx_rate if "USD" in k.upper() else float(v) for k, v in d.items())
            except: return 0

        df['DCA_ILS'] = df.apply(lambda row: sum_dca(row['DCA_JSON'], row['FX_Rate']), axis=1)
        df['Cum_DCA'] = df['DCA_ILS'].cumsum()
        
        def calc_bank(d):
            if d < DEPOSIT_1_START: return 0
            if d < DEPOSIT_2_START:
                return DEPOSIT_1_PRINCIPAL * ((1 + 0.045/365)**(d - DEPOSIT_1_START).days)
            return DEPOSIT_2_PRINCIPAL * ((1 + 0.048/365)**(d - DEPOSIT_2_START).days)
        
        df['Bank_Val'] = df['Date'].apply(calc_bank)
        df['Portfolio_Value'] = ((df['IBKR_USD'].fillna(0) + df['BLINK_USD'].fillna(0) + df['KRAKEN_USD'].fillna(0)) * df['FX_Rate']) + df['IRISH_ILS'].fillna(0) + df['Bank_Val']
        df['Invested_Capital'] = df['Cum_DCA'] + df['Date'].apply(lambda d: DEPOSIT_2_PRINCIPAL if d >= DEPOSIT_2_START else DEPOSIT_1_PRINCIPAL)
        df['Return_Abs'] = df['Portfolio_Value'] - df['Invested_Capital']
        return df
    except: return None

# --- UI ---
st.title("🛡️ My Investment Portfolio")
df = load_and_process(SHEET_URL)

if df is not None:
    st.sidebar.header("הגדרות תצוגה")
    range_choice = st.sidebar.selectbox("בחר טווח זמן לתצוגה:", ["Daily", "Weekly", "Monthly", "Yearly", "YTD"], index=1)
    
    latest = df.iloc[-1]
    
    # חישוב תאריכים לטווח
    range_map = {"Daily": 1, "Weekly": 7, "Monthly": 30, "Yearly": 365, "YTD": (latest['Date'] - date(latest['Date'].year, 1, 1)).days}
    start_date = latest['Date'] - timedelta(days=range_map[range_choice])
    
    filtered_df = df[df['Date'] >= start_date].copy()
    if filtered_df.empty: filtered_df = df.tail(2)
    
    start_val = filtered_df.iloc[0]['Portfolio_Value']
    range_return_ils = latest['Portfolio_Value'] - start_val
    range_return_pct = ((latest['Portfolio_Value'] / start_val) - 1) * 100

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("שווי כולל", f"₪{int(latest['Portfolio_Value']):,}")
    c2.metric(f"תשואה ({range_choice})", f"₪{int(range_return_ils):,}", f"{range_return_pct:.2f}%")
    c3.metric("רווח כולל", f"₪{int(latest['Return_Abs']):,}")
    c4.metric("שער דולר (רציף)", f"{latest['FX_Rate']:.3f}")

    st.markdown("---")

    # גרף השוואה
    st.subheader(f"📊 ביצועים מול מדדים (טווח {range_choice})")
    bench_options = {"S&P 500": "SPY", "Nasdaq": "QQQ", "Bitcoin": "BTC-USD", "TA-125": "^TA125.TA"}
    selected = st.multiselect("הוסף מדדים:", list(bench_options.keys()), default=["S&P 500"])

    fig_bench = go.Figure()
    my_norm = ((filtered_df['Portfolio_Value'] / start_val) - 1) * 100
    fig_bench.add_trace(go.Scatter(x=filtered_df['Date'], y=my_norm, name="התיק שלי", line=dict(color='#00d4ff', width=4)))

    if selected:
        for s in selected:
            try:
                b_hist = yf.download(bench_options[s], start=start_date, progress=False)['Close']
                if not b_hist.empty:
                    b_norm = ((b_hist / b_hist.iloc[0]) - 1) * 100
                    fig_bench.add_trace(go.Scatter(x=b_hist.index, y=b_norm, name=s, line=dict(width=1.5, dash='dot')))
            except: pass

    fig_bench.update_layout(hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="#fff")
    st.plotly_chart(fig_bench, use_container_width=True)

    # פילוח
    st.subheader("📊 סטטוס נכסים")
    cp1, cp2 = st.columns([1.5, 1])
    with cp1:
        labels = ["IBKR", "Blink", "Kraken", "אירית", "פקדון"]
        vals = [latest['IBKR_USD']*latest['FX_Rate'], latest['BLINK_USD']*latest['FX_Rate'], latest['KRAKEN_USD']*latest['FX_Rate'], latest['IRISH_ILS'], latest['Bank_Val']]
        fig_p = px.pie(names=labels, values=vals, hole=0.5, color_discrete_sequence=['#003f5c', '#bc5090', '#ffa600', '#00ff41', '#ff6361'])
        st.plotly_chart(fig_p, use_container_width=True)
    with cp2:
        st.info(f"**IBKR:** ${int(latest['IBKR_USD']):,}")
        st.info(f"**Blink:** ${int(latest['BLINK_USD']):,}")
        st.info(f"**Kraken:** ${int(latest['KRAKEN_USD']):,}")
        st.info(f"**אירית:** ₪{int(latest['IRISH_ILS']):,}")
        st.info(f"**פקדון:** ₪{int(latest['Bank_Val']):,}")

    # יומן
    st.subheader("📅 יומן ביצועים")
    st.dataframe(filtered_df[['Date', 'Portfolio_Value', 'FX_Rate']].sort_values('Date', ascending=False).style.format({
        'Portfolio_Value': lambda x: f"₪{int(x):,}",
        'FX_Rate': "{:.3f}"
    }), use_container_width=True, hide_index=True)