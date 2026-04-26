import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime, date

# --- CONFIG ---
# חשוב: הדבק כאן את הקישור המלא שמתחיל ב-https ומסתיים ב-output=csv
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTLlubNZGApf3LWUI3n0hRN6SNkyBdJmvNltHv_lLOO5FiAnnPG5NjvUAGRGE15N0sJ4q0VPFd_TjrE/pub?output=csv" 

FX_API_URL = "https://open.er-api.com/v6/latest/USD"
BANK_DEPOSIT_START = date(2026, 3, 16)
BANK_DEPOSIT_PRINCIPAL = 230000
BANK_ANNUAL_INTEREST = 0.048

st.set_page_config(page_title="Investment Tracker Pro", layout="wide")

# הגדרת כיווניות לימין
st.markdown("""
    <style>
    .main { direction: rtl; text-align: right; }
    div[data-testid="stMetricValue"] { text-align: right; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def get_fx_rate():
    try:
        r = requests.get(FX_API_URL, timeout=5).json()
        return r["rates"]["ILS"]
    except:
        return 3.7 # Fallback

@st.cache_data(ttl=600)
def load_data(url):
    try:
        df = pd.read_csv(url)
        # ניקוי שמות עמודות מרווחים מיותרים
        df.columns = [c.strip() for c in df.columns]
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        return df
    except Exception as e:
        st.error(f"שגיאה בטעינת הנתונים: {e}")
        return None

def calc_logic(df, fx):
    # חישוב DCA מתוך JSON
    def sum_dca(val, fx_rate):
        if pd.isna(val) or val == "" or val == "{}": return 0
        try:
            # תמיכה בגרש בודד או כפול
            cleaned_val = str(val).replace("'", '"')
            d = json.loads(cleaned_val)
            total = 0
            for k, v in d.items():
                if "USD" in k.upper(): total += float(v) * fx_rate
                else: total += float(v)
            return total
        except: return 0

    df['DCA_ILS'] = df['DCA_JSON'].apply(lambda x: sum_dca(x, fx))
    df['Cum_DCA'] = df['DCA_ILS'].cumsum()
    
    # חישוב שווי נכסים
    df['Total_USD'] = df['IBKR_USD'] + df['BLINK_USD'] + df['KRAKEN_USD']
    df['Total_ILS_Assets'] = (df['Total_USD'] * fx) + df['IRISH_ILS']
    
    # חישוב ריבית פיקדון
    def bank_val(d):
        if d < BANK_DEPOSIT_START: return 0
        days = (d - BANK_DEPOSIT_START).days
        return BANK_DEPOSIT_PRINCIPAL * ((1 + 0.048/365)**days)
    
    df['Bank_Deposit'] = df['Date'].apply(bank_val)
    df['Portfolio_Value'] = df['Total_ILS_Assets'] + df['Bank_Deposit']
    
    # הון מושקע (הפקדות + קרן הפיקדון)
    df['Invested_Capital'] = df['Cum_DCA'] + df['Date'].apply(lambda d: BANK_DEPOSIT_PRINCIPAL if d >= BANK_DEPOSIT_START else 0)
    
    df['Profit'] = df['Portfolio_Value'] - df['Invested_Capital']
    df['Return_Pct'] = (df['Profit'] / df['Invested_Capital']) * 100
    return df

# --- UI ---
st.title("💰 מעקב תיק השקעות אחוד")
fx = get_fx_rate()

if "google.com" in SHEET_URL: # בדיקה שהוכנס קישור
    raw_data = load_data(SHEET_URL)
    if raw_data is not None:
        df = calc_logic(raw_data, fx)
        latest = df.iloc[-1]
        
        # תצוגת KPI
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("שווי כולל", f"₪{latest['Portfolio_Value']:,.0f}")
        c2.metric("רווח/הפסד נקי", f"₪{latest['Profit']:,.0f}", f"{latest['Return_Pct']:.2f}%")
        c3.metric("סך הון מושקע", f"₪{latest['Invested_Capital']:,.0f}")
        c4.metric("שער USD/ILS", f"{fx:.3f}")

        st.markdown("---")
        
        # גרף צמיחה
        st.subheader("גרף צמיחה: שווי מול הפקדות")
        chart_df = df.set_index('Date')[['Portfolio_Value', 'Invested_Capital']]
        chart_df.columns = ['שווי תיק', 'הון מושקע']
        st.line_chart(chart_df)
        
        # פילוח נכסים
        st.subheader("פילוח נכסים נוכחי (בשקלים)")
        pie_data = {
            "IBKR": latest['IBKR_USD']*fx, 
            "Blink": latest['BLINK_USD']*fx,
            "Kraken": latest['KRAKEN_USD']*fx, 
            "קרן אירית": latest['IRISH_ILS'],
            "פיקדון בנקאי": latest['Bank_Deposit']
        }
        st.bar_chart(pd.Series(pie_data))
        
        # טבלה
        st.subheader("פירוט שבועי")
        display_df = df[['Date', 'Portfolio_Value', 'Profit', 'Return_Pct']].copy()
        display_df['Return_Pct'] = display_df['Return_Pct'].map("{:.2f}%".format)
        st.dataframe(display_df.sort_values('Date', ascending=False), use_container_width=True)
else:
    st.warning("אנא הזן קישור CSV תקין מתוך Google Sheets (Publish to Web).")