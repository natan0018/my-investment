import streamlit as st
import pandas as pd
import requests
import json
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf
from datetime import datetime, date

# --- CONFIG ---
# הקישור המעודכן שלך
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTLlubNZGApf3LWUI3n0hRN6SNkyBdJmvNltHv_lLOO5FiAnnPG5NjvUAGRGE15N0sJ4q0VPFd_TjrE/pub?output=csv" 

# נתוני פקדונות לפי התקופות שציינת
DEPOSIT_1_START = date(2025, 3, 1)
DEPOSIT_1_PRINCIPAL = 200000
DEPOSIT_1_INTEREST = 0.045

DEPOSIT_2_START = date(2026, 3, 16)
DEPOSIT_2_PRINCIPAL = 230000
DEPOSIT_2_INTEREST = 0.048

st.set_page_config(page_title="Cyber-Invest Elite v5", layout="wide")

# --- RTL & CYBER DARK CSS (Professional Trading Style) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Assistant:wght@300;400;700&display=swap');
    
    .main { direction: rtl; }
    html, body, [class*="css"], .stText, .stMarkdown { 
        font-family: 'Assistant', sans-serif; 
        direction: rtl; 
        text-align: right; 
    }
    .stApp { background-color: #080808; color: #d1d1d1; }
    
    /* כותרות בסגנון ניאון כחול */
    h1, h2, h3 { font-family: 'Orbitron', sans-serif; color: #00e5ff !important; text-shadow: 0 0 8px rgba(0,229,255,0.3); }
    
    /* עיצוב כרטיסי המדדים */
    div[data-testid="stMetric"] {
        background-color: #111111;
        border-right: 4px solid #00e5ff;
        border-radius: 4px;
        padding: 15px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.5);
    }
    div[data-testid="stMetricValue"] { color: #00ff41 !important; font-family: 'Orbitron', sans-serif; }
    
    /* עיצוב תיבות מידע צדדיות */
    .stInfo { background-color: #0f171e; border: 1px solid #1b2a35; color: #00e5ff; border-radius: 8px; }
    
    /* הסתרת אינדקס בטבלאות */
    [data-testid="stElementToolbar"] { display: none; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def get_current_fx():
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD").json()
        return r["rates"]["ILS"]
    except: return 3.7

def calc_bank_value(current_date):
    """חישוב ערך הפקדון המשולב בהתאם לתאריך"""
    if current_date < DEPOSIT_1_START:
        return 0
    # תקופת פקדון ראשון (200k)
    if current_date < DEPOSIT_2_START:
        days = (current_date - DEPOSIT_1_START).days
        return DEPOSIT_1_PRINCIPAL * ((1 + DEPOSIT_1_INTEREST/365)**days)
    # תקופת פקדון שני (230k)
    days = (current_date - DEPOSIT_2_START).days
    return DEPOSIT_2_PRINCIPAL * ((1 + DEPOSIT_2_INTEREST/365)**days)

@st.cache_data(ttl=600)
def load_and_process(url, current_fx):
    try:
        df = pd.read_csv(url)
        df.columns = [c.strip() for c in df.columns]
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        
        # שימוש בשער דולר מהגיליון או בשער נוכחי כגיבוי
        if 'FX_Rate' not in df.columns: df['FX_Rate'] = current_fx
            
        def sum_dca(val, fx_rate):
            if pd.isna(val) or val == "{}" or val == "": return 0
            d = json.loads(str(val).replace("'", '"'))
            return sum(float(v) * fx_rate if "USD" in k.upper() else float(v) for k, v in d.items())

        df['DCA_ILS'] = df.apply(lambda row: sum_dca(row['DCA_JSON'], row['FX_Rate']), axis=1)
        df['Cum_DCA'] = df['DCA_ILS'].cumsum()
        
        # חישוב שווי כולל כולל הפקדון המשתנה
        df['Bank_Val'] = df['Date'].apply(calc_bank_value)
        df['Portfolio_Value'] = ((df['IBKR_USD'] + df['BLINK_USD'] + df['KRAKEN_USD']) * df['FX_Rate']) + df['IRISH_ILS'] + df['Bank_Val']
        
        # הון מושקע רלוונטי לכל תקופה
        df['Invested_Capital'] = df['Cum_DCA'] + df['Date'].apply(lambda d: DEPOSIT_2_PRINCIPAL if d >= DEPOSIT_2_START else DEPOSIT_1_PRINCIPAL)
        
        # חישובי שינויים
        df['Weekly_Change_ILS'] = df['Portfolio_Value'].diff().fillna(0)
        df['Weekly_Change_Pct'] = df['Portfolio_Value'].pct_change().fillna(0) * 100
        df['Profit'] = df['Portfolio_Value'] - df['Invested_Capital']
        df['Return_Pct'] = (df['Profit'] / df['Invested_Capital']) * 100
        df['Norm_Portfolio'] = (df['Portfolio_Value'] / df['Portfolio_Value'].iloc[0]) * 100
        return df
    except: return None

# --- UI EXECUTION ---
st.title("💠 CYBER-FINANCE ELITE v5")
fx_now = get_current_fx()

if "google.com" in SHEET_URL:
    df = load_and_process(SHEET_URL, fx_now)
    if df is not None:
        latest = df.iloc[-1]

        # 1. נתוני התיק האישי (KPIs)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("שווי כולל", f"₪{int(latest['Portfolio_Value']):,}")
        c2.metric("רווח/הפסד כולל", f"₪{int(latest['Profit']):,}", f"{latest['Return_Pct']:.2f}%")
        c3.metric("שינוי שבועי", f"₪{int(latest['Weekly_Change_ILS']):,}", f"{latest['Weekly_Change_Pct']:.2f}%")
        c4.metric("USD/ILS", f"{fx_now:.3f}")

        st.markdown("---")

        # 2. מדדי שוק (Market Pulse)
        st.subheader("🌐 GLOBAL MARKET PULSE")
        m_tickers = {"S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Bitcoin": "BTC-USD"}
        cols = st.columns(3)
        for i, (name, sym) in enumerate(m_tickers.items()):
            try:
                m_data = yf.Ticker(sym).history(period="1d")
                price, change = m_data['Close'].iloc[-1], ((m_data['Close'].iloc[-1] - m_data['Open'].iloc[-1])/m_data['Open'].iloc[-1])*100
                cols[i].metric(name, f"{price:,.0f}", f"{change:.2f}%")
            except: pass

        st.markdown("---")

        # 3. פילוח נכסים ושווי מפורט
        st.subheader("📊 פילוח מכשירים ומומנטום")
        col_pie, col_details = st.columns([1.5, 1])
        
        with col_pie:
            labels = ["IBKR", "Blink", "Kraken", "קרן אירית", "פקדון בנקאי"]
            values = [latest['IBKR_USD']*latest['FX_Rate'], latest['BLINK_USD']*latest['FX_Rate'], latest['KRAKEN_USD']*latest['FX_Rate'], latest['IRISH_ILS'], latest['Bank_Val']]
            fig_pie = px.pie(names=labels, values=values, hole=0.6, 
                             color_discrete_sequence=['#00e5ff', '#00ff41', '#7000ff', '#007bff', '#222'])
            fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color="#fff", showlegend=True)
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_details:
            st.info(f"💵 **IBKR:** ${int(latest['IBKR_USD']):,}")
            st.info(f"💵 **Blink:** ${int(latest['BLINK_USD']):,}")
            st.info(f"₿ **Kraken:** ${int(latest['KRAKEN_USD']):,}")
            st.info(f"🇮🇱 **קרן אירית:** ₪{int(latest['IRISH_ILS']):,}")
            st.info(f"🏦 **פקדון משולב:** ₪{int(latest['Bank_Val']):,}")

        # 4. גרף צמיחה
        st.subheader("📈 מומנטום תיק (Base 100)")
        fig_trend = go.Figure()
        fig_trend.add_trace(go.Scatter(x=df['Date'], y=df['Norm_Portfolio'], name='התיק שלי', 
                                     line=dict(color='#00e5ff', width=4)))
        fig_trend.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="#fff")
        st.plotly_chart(fig_trend, use_container_width=True)

        # 5. טבלה היסטורית
        st.subheader("📝 יומן נתונים ושינויים שבועיים")
        h_df = df[['Date', 'Portfolio_Value', 'Weekly_Change_ILS', 'Weekly_Change_Pct', 'FX_Rate']].copy()
        h_df.columns = ['תאריך', 'שווי תיק', 'שינוי (₪)', 'שינוי (%)', 'שער דולר']
        
        st.dataframe(h_df.sort_values('תאריך', ascending=False).style.format({
            'שווי תיק': lambda x: f"₪{int(x):,}",
            'שינוי (₪)': lambda x: f"₪{int(x):,}",
            'שינוי (%)': "{:.2f}%",
            'שער דולר': "{:.3f}"
        }), use_container_width=True, hide_index=True)

else:
    st.warning("אנא וודא שהקישור ל-CSV תקין.")