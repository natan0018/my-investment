import streamlit as st
import pandas as pd
import requests
import json
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf
from datetime import datetime, date

# --- CONFIG ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTLlubNZGApf3LWUI3n0hRN6SNkyBdJmvNltHv_lLOO5FiAnnPG5NjvUAGRGE15N0sJ4q0VPFd_TjrE/pub?output=csv" 
FX_API_URL = "https://open.er-api.com/v6/latest/USD"
BANK_DEPOSIT_START = date(2026, 3, 16)
BANK_DEPOSIT_PRINCIPAL = 230000
BANK_ANNUAL_INTEREST = 0.048

st.set_page_config(page_title="Investment Tracker Pro V2", layout="wide")

# עיצוב RTL ושיפור ויזואלי
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Assistant', sans-serif; direction: rtl; text-align: right; }
    .stMetric { background-color: #f8f9fb; padding: 15px; border-radius: 12px; border: 1px solid #e1e4e8; }
    div[data-testid="stMetricValue"] { color: #2c3e50; font-size: 1.8rem !important; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def get_fx_rate():
    try:
        r = requests.get(FX_API_URL, timeout=5).json()
        return r["rates"]["ILS"]
    except: return 3.7

@st.cache_data(ttl=3600)
def get_market_data():
    # משיכת מדדים מובילים
    tickers = {"S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Bitcoin": "BTC-USD", "Ethereum": "ETH-USD"}
    data = {}
    for name, sym in tickers.items():
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="1d")
            price = hist['Close'].iloc[-1]
            change = ((price - hist['Open'].iloc[-1]) / hist['Open'].iloc[-1]) * 100
            data[name] = {"price": price, "change": change}
        except: data[name] = {"price": 0, "change": 0}
    return data

@st.cache_data(ttl=600)
def load_data(url):
    try:
        df = pd.read_csv(url)
        df.columns = [c.strip() for c in df.columns]
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        return df
    except: return None

def calc_logic(df, fx):
    def sum_dca(val, fx_rate):
        if pd.isna(val) or val == "" or val == "{}": return 0
        try:
            d = json.loads(str(val).replace("'", '"'))
            return sum(float(v) * fx_rate if "USD" in k.upper() else float(v) for k, v in d.items())
        except: return 0

    df['DCA_ILS'] = df['DCA_JSON'].apply(lambda x: sum_dca(x, fx))
    df['Cum_DCA'] = df['DCA_ILS'].cumsum()
    df['Total_USD'] = df['IBKR_USD'] + df['BLINK_USD'] + df['KRAKEN_USD']
    df['Bank_Deposit'] = df['Date'].apply(lambda d: BANK_DEPOSIT_PRINCIPAL * ((1 + 0.048/365)**(d - BANK_DEPOSIT_START).days) if d >= BANK_DEPOSIT_START else 0)
    df['Portfolio_Value'] = (df['Total_USD'] * fx) + df['IRISH_ILS'] + df['Bank_Deposit']
    df['Invested_Capital'] = df['Cum_DCA'] + df['Date'].apply(lambda d: BANK_DEPOSIT_PRINCIPAL if d >= BANK_DEPOSIT_START else 0)
    df['Profit'] = df['Portfolio_Value'] - df['Invested_Capital']
    df['Return_Pct'] = (df['Profit'] / df['Invested_Capital']) * 100
    return df

# --- UI ---
st.title("💰 דשבורד השקעות חכם")
fx = get_fx_rate()
m_data = get_market_data()

# שורת מדדים עולמיים
cols = st.columns(len(m_data))
for i, (name, val) in enumerate(m_data.items()):
    cols[i].metric(name, f"{val['price']:,.0f}", f"{val['change']:.2f}%")

st.markdown("---")

if "google.com" in SHEET_URL:
    raw_df = load_data(SHEET_URL)
    if raw_df is not None:
        df = calc_logic(raw_df, fx)
        latest = df.iloc[-1]

        # 1. סיכום תיק אישי
        st.subheader("תמונת מצב התיק")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("שווי כולל", f"₪{int(latest['Portfolio_Value']):,}")
        c2.metric("רווח/הפסד", f"₪{int(latest['Profit']):,}", f"{latest['Return_Pct']:.2f}%")
        c3.metric("הון מושקע", f"₪{int(latest['Invested_Capital']):,}")
        c4.metric("שער דולר", f"{fx:.2f}")

        # 2. פילוח נכסים
        col_pie, col_txt = st.columns([2, 1])
        with col_pie:
            labels = ["IBKR", "Blink", "Kraken", "קרן אירית", "פיקדון בנקאי"]
            values = [latest['IBKR_USD']*fx, latest['BLINK_USD']*fx, latest['KRAKEN_USD']*fx, latest['IRISH_ILS'], latest['Bank_Deposit']]
            fig_pie = px.pie(names=labels, values=values, hole=0.5, title="חלוקת נכסים אחוזית",
                             color_discrete_sequence=px.colors.qualitative.Safe)
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with col_txt:
            st.subheader("שווי במטבע מקור")
            st.info(f"**IBKR:** ${int(latest['IBKR_USD']):,}")
            st.info(f"**Blink:** ${int(latest['BLINK_USD']):,}")
            st.info(f"**Kraken:** ${int(latest['KRAKEN_USD']):,}")
            st.info(f"**קרן אירית:** ₪{int(latest['IRISH_ILS']):,}")
            st.info(f"**פיקדון:** ₪{int(latest['Bank_Deposit']):,}")

        # 3. גרף צמיחה
        st.subheader("צמיחת התיק לאורך זמן")
        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(x=df['Date'], y=df['Portfolio_Value'], name='שווי תיק (₪)', line=dict(color='#1f77b4', width=4)))
        fig_line.add_trace(go.Scatter(x=df['Date'], y=df['Invested_Capital'], name='הון מושקע (₪)', line=dict(color='#bdc3c7', dash='dash')))
        fig_line.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig_line, use_container_width=True)

        # 4. טבלה היסטורית
        st.subheader("היסטוריה שבועית")
        table_df = df[['Date', 'Portfolio_Value', 'Profit', 'Return_Pct']].copy()
        table_df['Portfolio_Value'] = table_df['Portfolio_Value'].apply(lambda x: f"₪{int(x):,}")
        table_df['Profit'] = table_df['Profit'].apply(lambda x: f"₪{int(x):,}")
        table_df['Return_Pct'] = table_df['Return_Pct'].map("{:.2f}%".format)
        st.dataframe(table_df.sort_values('Date', ascending=False), use_container_width=True, hide_index=True)