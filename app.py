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

# --- CSS & RTL ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;700&family=Assistant:wght@300;400;700&display=swap');
    .main { direction: rtl; }
    html, body, [class*="css"], .stText, .stMarkdown { 
        font-family: 'Assistant', sans-serif; 
        direction: rtl; text-align: right; 
    }
    .stApp { background-color: #080808; color: #d1d1d1; }
    h1, h2, h3 { color: #00e5ff !important; font-weight: 700; }
    div[data-testid="stMetric"] {
        background-color: #111111;
        border-right: 4px solid #00e5ff;
        border-radius: 4px;
        padding: 15px;
    }
    div[data-testid="stMetricValue"] { color: #00ff41 !important; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def get_current_fx():
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD").json()
        return r["rates"]["ILS"]
    except: return 3.7

def calc_bank_value(current_date):
    if current_date < DEPOSIT_1_START: return 0
    if current_date < DEPOSIT_2_START:
        days = (current_date - DEPOSIT_1_START).days
        return DEPOSIT_1_PRINCIPAL * ((1 + DEPOSIT_1_INTEREST/365)**days)
    days = (current_date - DEPOSIT_2_START).days
    return DEPOSIT_2_PRINCIPAL * ((1 + DEPOSIT_2_INTEREST/365)**days)

@st.cache_data(ttl=600)
def load_and_process(url, current_fx):
    try:
        df = pd.read_csv(url)
        df.columns = [c.strip() for c in df.columns]
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        if 'FX_Rate' not in df.columns: df['FX_Rate'] = current_fx
        
        def sum_dca(val, fx_rate):
            if pd.isna(val) or val == "{}" or val == "": return 0
            d = json.loads(str(val).replace("'", '"'))
            return sum(float(v) * fx_rate if "USD" in k.upper() else float(v) for k, v in d.items())

        df['DCA_ILS'] = df.apply(lambda row: sum_dca(row['DCA_JSON'], row['FX_Rate']), axis=1)
        df['Cum_DCA'] = df['DCA_ILS'].cumsum()
        df['Bank_Val'] = df['Date'].apply(calc_bank_value)
        df['Portfolio_Value'] = ((df['IBKR_USD'] + df['BLINK_USD'] + df['KRAKEN_USD']) * df['FX_Rate']) + df['IRISH_ILS'] + df['Bank_Val']
        df['Invested_Capital'] = df['Cum_DCA'] + df['Date'].apply(lambda d: DEPOSIT_2_PRINCIPAL if d >= DEPOSIT_2_START else DEPOSIT_1_PRINCIPAL)
        
        df['Return_Abs'] = df['Portfolio_Value'] - df['Invested_Capital']
        df['Return_Pct'] = (df['Return_Abs'] / df['Invested_Capital']) * 100
        return df
    except: return None

# --- UI EXECUTION ---
st.title("📊 My Investment Portfolio")
fx_now = get_current_fx()
df = load_and_process(SHEET_URL, fx_now)

if df is not None:
    latest = df.iloc[-1]
    
    # 1. בורר טווחי זמן לתשואה
    st.subheader("📈 ביצועי תשואה")
    time_frame = st.selectbox("בחר טווח זמן לתצוגה:", ["Daily", "Weekly", "Monthly", "YTD"], index=1)
    
    # חישוב תשואות לפי טווח
    today = latest['Date']
    lookback_map = {
        "Daily": today - timedelta(days=1),
        "Weekly": today - timedelta(days=7),
        "Monthly": today - timedelta(days=30),
        "YTD": date(today.year, 1, 1)
    }
    
    past_row = df[df['Date'] <= lookback_map[time_frame]].iloc[-1] if not df[df['Date'] <= lookback_map[time_frame]].empty else df.iloc[0]
    diff_ils = latest['Portfolio_Value'] - past_row['Portfolio_Value']
    diff_pct = ((latest['Portfolio_Value'] / past_row['Portfolio_Value']) - 1) * 100

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("שווי כולל", f"₪{int(latest['Portfolio_Value']):,}")
    c2.metric(f"תשואה {time_frame}", f"₪{int(diff_ils):,}", f"{diff_pct:.2f}%")
    c3.metric("רווח כולל (All Time)", f"₪{int(latest['Return_Abs']):,}", f"{latest['Return_Pct']:.2f}%")
    c4.metric("שער USD/ILS", f"{fx_now:.3f}")

    st.markdown("---")

    # 2. גרף השוואת מדדים (Benchmarking)
    st.subheader("💹 השוואה למדדי שוק (תשואה מצטברת %)")
    bench_options = {
        "S&P 500 (SPY)": "SPY",
        "Nasdaq (QQQ)": "QQQ",
        "Russell 2000 (IWM)": "IWM",
        "Bitcoin": "BTC-USD",
        "Ethereum": "ETH-USD",
        "TA-125": "^TA125.TA",
        "TA-35": "^TA35.TA"
    }
    selected_bench = st.multiselect("הוסף/הסר מדדים להשוואה:", list(bench_options.keys()), default=["S&P 500 (SPY)"])

    fig_bench = go.Figure()
    
    # נרמול התיק שלי לתשואה באחוזים (התחלה ב-0%)
    my_returns = ((df['Portfolio_Value'] / df['Portfolio_Value'].iloc[0]) - 1) * 100
    fig_bench.add_trace(go.Scatter(x=df['Date'], y=my_returns, name="התיק שלי", line=dict(color='#00e5ff', width=4)))

    if selected_bench:
        for b in selected_bench:
            ticker = bench_options[b]
            b_data = yf.download(ticker, start=df['Date'].iloc[0])['Close']
            if not b_data.empty:
                b_returns = ((b_data / b_data.iloc[0]) - 1) * 100
                fig_bench.add_trace(go.Scatter(x=b_data.index, y=b_returns, name=b, line=dict(width=1.5, dash='dot')))

    fig_bench.update_layout(
        hovermode="x unified",
        xaxis_title="תאריך (שבועות)",
        yaxis_title="תשואה מצטברת (%)",
        xaxis=dict(tickformat="%b %d", dtick=604800000.0), # הצגה לפי שבועות
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_color="#fff"
    )
    st.plotly_chart(fig_bench, use_container_width=True)

    # 3. פילוח נכסים (עוגה ופירוט)
    st.subheader("📊 פילוח מכשירים")
    cp1, cp2 = st.columns([1.5, 1])
    with cp1:
        labels = ["IBKR", "Blink", "Kraken", "קרן אירית", "פקדון"]
        vals = [latest['IBKR_USD']*latest['FX_Rate'], latest['BLINK_USD']*latest['FX_Rate'], latest['KRAKEN_USD']*latest['FX_Rate'], latest['IRISH_ILS'], latest['Bank_Val']]
        fig_p = px.pie(names=labels, values=vals, hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
        fig_p.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color="#fff")
        st.plotly_chart(fig_p, use_container_width=True)
    with cp2:
        st.info(f"💵 **IBKR:** ${int(latest['IBKR_USD']):,}")
        st.info(f"💵 **Blink:** ${int(latest['BLINK_USD']):,}")
        st.info(f"₿ **Kraken:** ${int(latest['KRAKEN_USD']):,}")
        st.info(f"🇮🇱 **קרן אירית:** ₪{int(latest['IRISH_ILS']):,}")
        st.info(f"🏦 **פקדון:** ₪{int(latest['Bank_Val']):,}")

    # 4. טבלה היסטורית
    st.subheader("📜 יומן שבועי")
    st.dataframe(df.sort_values('Date', ascending=False).style.format({
        'Portfolio_Value': '₪{:,.0f}',
        'Return_Abs': '₪{:,.0f}',
        'Return_Pct': '{:.2f}%',
        'FX_Rate': '{:.3f}'
    }), use_container_width=True, hide_index=True)