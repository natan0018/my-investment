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

# --- CSS & CYBER DESIGN ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;400;700&display=swap');
    .main { direction: rtl; }
    html, body, [class*="css"], .stText, .stMarkdown { font-family: 'Assistant', sans-serif; direction: rtl; text-align: right; }
    .stApp { background-color: #050505; color: #e0e0e0; }
    div[data-testid="stMetric"] { background-color: #101010; border-right: 4px solid #00d4ff; border-radius: 4px; padding: 15px; }
    div[data-testid="stMetricValue"] { color: #00ff41 !important; font-size: 1.8rem !important; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def get_current_fx():
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5).json()
        return r["rates"]["ILS"]
    except:
        return 3.7

@st.cache_data(ttl=600)
def load_and_process(url, fx_now):
    try:
        df = pd.read_csv(url)
        df.columns = [c.strip() for c in df.columns]
        # הסרת שורות ריקות לחלוטין
        df = df.dropna(subset=['Date', 'IBKR_USD'])
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        
        # שימוש בשער מהגיליון או בשער נוכחי אם חסר
        if 'FX_Rate' not in df.columns:
            df['FX_Rate'] = fx_now
        df['FX_Rate'] = df['FX_Rate'].fillna(fx_now)
        
        def sum_dca(val, fx_rate):
            if pd.isna(val) or val == "{}" or val == "": return 0
            try:
                cleaned_val = str(val).replace("'", '"')
                d = json.loads(cleaned_val)
                total = 0
                for k, v in d.items():
                    if "USD" in k.upper(): total += float(v) * fx_rate
                    else: total += float(v)
                return total
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
        
        # הון מושקע לפי תקופות
        df['Invested_Capital'] = df['Cum_DCA'] + df['Date'].apply(lambda d: DEPOSIT_2_PRINCIPAL if d >= DEPOSIT_2_START else DEPOSIT_1_PRINCIPAL)
        
        df['Return_Abs'] = df['Portfolio_Value'] - df['Invested_Capital']
        df['Return_Pct'] = ((df['Portfolio_Value'] / df['Invested_Capital']) - 1) * 100
        return df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None

# --- UI ---
st.title("🛡️ My Investment Portfolio")
fx_now = get_current_fx()
df = load_and_process(SHEET_URL, fx_now)

if df is not None:
    latest = df.iloc[-1]
    
    # 1. בורר תשואה
    time_frame = st.sidebar.selectbox("טווח זמן לחישוב:", ["Daily", "Weekly", "Monthly", "YTD"], index=1)
    lookback_days = {"Daily": 1, "Weekly": 7, "Monthly": 30, "YTD": (latest['Date'] - date(latest['Date'].year, 1, 1)).days}
    
    past_date = latest['Date'] - timedelta(days=lookback_days[time_frame])
    past_row = df[df['Date'] <= past_date].iloc[-1] if not df[df['Date'] <= past_date].empty else df.iloc[0]
    
    diff_ils = latest['Portfolio_Value'] - past_row['Portfolio_Value']
    diff_pct = ((latest['Portfolio_Value'] / past_row['Portfolio_Value']) - 1) * 100

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("שווי כולל", f"₪{int(latest['Portfolio_Value']):,}")
    c2.metric(f"תשואה {time_frame}", f"₪{int(diff_ils):,}", f"{diff_pct:.2f}%")
    c3.metric("רווח כולל", f"₪{int(latest['Return_Abs']):,}", f"{latest['Return_Pct']:.2f}%")
    c4.metric("USD/ILS (Live)", f"{fx_now:.3f}")

    st.markdown("---")

    # 2. גרף השוואה למדדים (תיקון באגים)
    st.subheader("📊 ביצועים מול מדדי ייחוס (Base 0%)")
    bench_options = {"S&P 500": "SPY", "Nasdaq": "QQQ", "Bitcoin": "BTC-USD", "Ethereum": "ETH-USD", "TA-125": "^TA125.TA"}
    selected = st.multiselect("הוסף/הסר מדדים מהגרף:", list(bench_options.keys()), default=["S&P 500"])

    fig_bench = go.Figure()
    # תיק שלי - נרמול ל-0% בנקודת ההתחלה
    my_norm = ((df['Portfolio_Value'] / df['Portfolio_Value'].iloc[0]) - 1) * 100
    fig_bench.add_trace(go.Scatter(x=df['Date'], y=my_norm, name="התיק שלי", line=dict(color='#00d4ff', width=4)))

    if selected:
        for s in selected:
            try:
                b_ticker = yf.Ticker(bench_options[s])
                b_hist = b_ticker.history(start=df['Date'].min())['Close']
                if not b_hist.empty:
                    # נרמול המדד ל-0% ביום הראשון של התיק
                    b_norm = ((b_hist / b_hist.iloc[0]) - 1) * 100
                    fig_bench.add_trace(go.Scatter(x=b_hist.index, y=b_norm, name=s, line=dict(width=1.5, dash='dot')))
            except:
                pass

    fig_bench.update_layout(hovermode="x unified", xaxis_title="תאריך", yaxis_title="תשואה %", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="#fff")
    st.plotly_chart(fig_bench, use_container_width=True)

    # 3. פילוח נכסים
    st.subheader("📊 פילוח מכשירים")
    col_pie, col_details = st.columns([1.5, 1])
    with col_pie:
        labels = ["IBKR", "Blink", "Kraken", "קרן אירית", "פקדון בנקאי"]
        vals = [latest['IBKR_USD']*latest['FX_Rate'], latest['BLINK_USD']*latest['FX_Rate'], latest['KRAKEN_USD']*latest['FX_Rate'], latest['IRISH_ILS'], latest['Bank_Val']]
        fig_p = px.pie(names=labels, values=vals, hole=0.5, color_discrete_sequence=['#003f5c', '#58508d', '#bc5090', '#ff6361', '#ffa600'])
        fig_p.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color="#fff")
        st.plotly_chart(fig_p, use_container_width=True)
    
    with col_details:
        st.info(f"**IBKR:** ${int(latest['IBKR_USD']):,}")
        st.info(f"**Blink:** ${int(latest['BLINK_USD']):,}")
        st.info(f"**Kraken:** ${int(latest['KRAKEN_USD']):,}")
        st.info(f"**קרן אירית:** ₪{int(latest['IRISH_ILS']):,}")
        st.info(f"**פקדון:** ₪{int(latest['Bank_Val']):,}")

    # 4. יומן שבועי (תיקון שגיאת ה-Int)
    st.subheader("📅 יומן ביצועים שבועי")
    log_df = df[['Date', 'Portfolio_Value', 'Return_Pct', 'FX_Rate']].copy()
    
    # פונקציית עזר להצגה בטוחה של מספרים (מונעת קריסה בערכי NaN)
    def safe_int_format(x):
        try:
            return f"₪{int(x):,}" if pd.notnull(x) else "N/A"
        except: return "N/A"

    def safe_pct_format(x):
        return f"{x:.1f}%" if pd.notnull(x) else "0.0%"

    log_df.columns = ['תאריך', 'שווי (₪)', 'תשואה (%)', 'שער דולר']
    st.dataframe(log_df.sort_values('תאריך', ascending=False).style.format({
        'שווי (₪)': safe_int_format,
        'תשואה (%)': safe_pct_format,
        'שער דולר': "{:.3f}"
    }), use_container_width=True, hide_index=True)

else:
    st.warning("נא לוודא שקישור ה-CSV תקין ושיש נתונים בגיליון.")