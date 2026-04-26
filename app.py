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
BANK_DEPOSIT_START = date(2026, 3, 16)
BANK_DEPOSIT_PRINCIPAL = 230000
BANK_ANNUAL_INTEREST = 0.048

st.set_page_config(page_title="Cyber-Invest Tracker v4", layout="wide")

# --- RTL & CYBERPUNK CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Assistant:wght@300;400;700&display=swap');
    
    .main { direction: rtl; }
    html, body, [class*="css"], .stText, .stMarkdown { 
        font-family: 'Assistant', sans-serif; 
        direction: rtl; 
        text-align: right; 
    }
    .stApp { background-color: #0a0a0c; color: #e0e0e0; }
    h1, h2, h3 { font-family: 'Orbitron', sans-serif; color: #00f2ff !important; text-shadow: 0 0 10px #00f2ff; }
    
    /* Metrics */
    div[data-testid="stMetric"] {
        background-color: #161b22;
        border: 1px solid #00f2ff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 0 10px rgba(0, 242, 255, 0.1);
        direction: rtl;
    }
    div[data-testid="stMetricValue"] { color: #ff00ff !important; font-family: 'Orbitron', sans-serif; }
    
    /* Tables */
    .stDataFrame { border: 1px solid #00f2ff; border-radius: 5px; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def get_current_fx():
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD").json()
        return r["rates"]["ILS"]
    except: return 3.7

@st.cache_data(ttl=3600)
def get_benchmark_data(start_date):
    tickers = {"S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Bitcoin": "BTC-USD"}
    bench_df = pd.DataFrame()
    for name, sym in tickers.items():
        data = yf.download(sym, start=start_date)['Close']
        # נרמול ל-100 לצורך השוואה
        bench_df[name] = (data / data.iloc[0]) * 100
    return bench_df

@st.cache_data(ttl=600)
def load_and_process(url, current_fx):
    try:
        df = pd.read_csv(url)
        df.columns = [c.strip() for c in df.columns]
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        
        # לוגיקת FX: אם יש עמודה בגיליון נשתמש בה, אחרת בשער הנוכחי
        if 'FX_Rate' not in df.columns:
            df['FX_Rate'] = current_fx
            
        def sum_dca(val, fx_rate):
            if pd.isna(val) or val == "{}" or val == "": return 0
            d = json.loads(str(val).replace("'", '"'))
            return sum(float(v) * fx_rate if "USD" in k.upper() else float(v) for k, v in d.items())

        df['DCA_ILS'] = df.apply(lambda row: sum_dca(row['DCA_JSON'], row['FX_Rate']), axis=1)
        df['Cum_DCA'] = df['DCA_ILS'].cumsum()
        
        # חישוב שווי
        df['Bank_Val'] = df['Date'].apply(lambda d: BANK_DEPOSIT_PRINCIPAL * ((1 + 0.048/365)**(d - BANK_DEPOSIT_START).days) if d >= BANK_DEPOSIT_START else 0)
        df['Portfolio_Value'] = ((df['IBKR_USD'] + df['BLINK_USD'] + df['KRAKEN_USD']) * df['FX_Rate']) + df['IRISH_ILS'] + df['Bank_Val']
        df['Invested_Capital'] = df['Cum_DCA'] + df['Date'].apply(lambda d: BANK_DEPOSIT_PRINCIPAL if d >= BANK_DEPOSIT_START else 0)
        
        # שינויים שבועיים
        df['Weekly_Change_ILS'] = df['Portfolio_Value'].diff().fillna(0)
        df['Weekly_Change_Pct'] = df['Portfolio_Value'].pct_change().fillna(0) * 100
        
        df['Profit'] = df['Portfolio_Value'] - df['Invested_Capital']
        df['Return_Pct'] = (df['Profit'] / df['Invested_Capital']) * 100
        
        # נרמול התיק להשוואה (Base 100)
        df['Norm_Portfolio'] = (df['Portfolio_Value'] / df['Portfolio_Value'].iloc[0]) * 100
        
        return df
    except Exception as e:
        st.error(f"Error: {e}")
        return None

# --- UI START ---
st.title("⚡ CYBER-INVEST TRACKER v4.0")
fx_now = get_current_fx()

if "google.com" in SHEET_URL:
    df = load_and_process(SHEET_URL, fx_now)
    if df is not None:
        latest = df.iloc[-1]

        # 1. נתוני התיק (עברו לראש הדף)
        st.subheader("📡 סטטוס תיק נוכחי")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("שווי כולל", f"₪{int(latest['Portfolio_Value']):,}")
        m2.metric("רווח/הפסד נקי", f"₪{int(latest['Profit']):,}", f"{latest['Return_Pct']:.2f}%")
        m3.metric("שינוי שבועי", f"₪{int(latest['Weekly_Change_ILS']):,}", f"{latest['Weekly_Change_Pct']:.2f}%")
        m4.metric("שער USD/ILS", f"{fx_now:.3f}")

        st.markdown("---")

        # 2. מדדים מובילים (עברו למקום השני)
        st.subheader("🌐 מדדי שוק גלובליים")
        m_tickers = {"S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Bitcoin": "BTC-USD", "Ethereum": "ETH-USD"}
        cols = st.columns(len(m_tickers))
        for i, (name, sym) in enumerate(m_tickers.items()):
            m_data = yf.Ticker(sym).history(period="1d")
            price = m_data['Close'].iloc[-1]
            change = ((price - m_data['Open'].iloc[-1]) / m_data['Open'].iloc[-1]) * 100
            cols[i].metric(name, f"{price:,.0f}", f"{change:.2f}%")

        st.markdown("---")

        # 3. גרף צמיחה והשוואה
        st.subheader("📈 אנליזה והשוואה למדדים (Base 100)")
        show_bench = st.checkbox("הצג השוואה למדדי שוק", value=True)
        
        fig_trend = go.Figure()
        # גרף התיק
        fig_trend.add_trace(go.Scatter(x=df['Date'], y=df['Norm_Portfolio'], name='התיק שלי', line=dict(color='#00f2ff', width=4)))
        
        if show_bench:
            bench_df = get_benchmark_data(df['Date'].iloc[0])
            for col in bench_df.columns:
                fig_trend.add_trace(go.Scatter(x=bench_df.index, y=bench_df[col], name=col, line=dict(width=1.5, dash='dot')))

        fig_trend.update_layout(hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="#e0e0e0")
        st.plotly_chart(fig_trend, use_container_width=True)

        # 4. טבלה היסטורית משופרת
        st.subheader("📝 יומן נתונים שבועי")
        history_df = df[['Date', 'Portfolio_Value', 'Weekly_Change_ILS', 'Weekly_Change_Pct', 'FX_Rate']].copy()
        
        # עיצוב הטבלה
        history_df['Portfolio_Value'] = history_df['Portfolio_Value'].apply(lambda x: f"₪{int(x):,}")
        history_df['Weekly_Change_ILS'] = history_df['Weekly_Change_ILS'].apply(lambda x: f"₪{int(x):,}")
        history_df['Weekly_Change_Pct'] = history_df['Weekly_Change_Pct'].map("{:.2f}%".format)
        history_df['FX_Rate'] = history_df['FX_Rate'].map("{:.3f}".format)
        
        history_df.columns = ['תאריך', 'שווי תיק', 'שינוי שקלי', 'שינוי אחוזי', 'שער דולר']
        st.dataframe(history_df.sort_values('תאריך', ascending=False), use_container_width=True, hide_index=True)

else:
    st.warning("אנא הזן קישור CSV תקין.")