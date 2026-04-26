import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime, date

# --- CONFIG ---
# בצע Publish to web לגיליון שלך כ-CSV והדבק כאן את הלינק
SHEET_URL = "1DkbiMERQ8-X3f0odkjVpWl2xc965oV1h2_6jVkM7ouM" 
FX_API_URL = "https://open.er-api.com/v6/latest/USD"
BANK_DEPOSIT_START = date(2026, 3, 16)
BANK_DEPOSIT_PRINCIPAL = 230000
BANK_ANNUAL_INTEREST = 0.048

st.set_page_config(page_title="Investment Tracker Pro", layout="wide")

# ימין לשמאל
st.markdown("""<style> .main { direction: rtl; text-align: right; } </style>""", unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def get_fx_rate():
    try:
        r = requests.get(FX_API_URL, timeout=5).json()
        return r["rates"]["ILS"]
    except:
        return 3.7 # Fallback

@st.cache_data(ttl=600)
def load_data(url):
    df = pd.read_csv(url)
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    return df

def calc_logic(df, fx):
    # חישוב DCA
    def sum_dca(val, fx_rate):
        try:
            d = json.loads(val.replace("'", '"'))
            total = 0
            for k, v in d.items():
                if "USD" in k: total += v * fx_rate
                else: total += v
            return total
        except: return 0

    df['DCA_ILS'] = df['DCA_JSON'].apply(lambda x: sum_dca(x, fx))
    df['Cum_DCA'] = df['DCA_ILS'].cumsum()
    
    # חישוב שווי
    df['Total_USD'] = df['IBKR_USD'] + df['BLINK_USD'] + df['KRAKEN_USD']
    df['Total_ILS_Assets'] = (df['Total_USD'] * fx) + df['IRISH_ILS']
    
    # ריבית פיקדון
    def bank_val(d):
        if d < BANK_DEPOSIT_START: return 0
        days = (d - BANK_DEPOSIT_START).days
        return BANK_DEPOSIT_PRINCIPAL * ((1 + 0.048/365)**days)
    
    df['Bank_Deposit'] = df['Date'].apply(bank_val)
    df['Portfolio_Value'] = df['Total_ILS_Assets'] + df['Bank_Deposit']
    
    # הוספת הפיקדון לסך ההפקדות החל מהתאריך הרלוונטי
    df['Invested_Capital'] = df['Cum_DCA'] + df['Date'].apply(lambda d: BANK_DEPOSIT_PRINCIPAL if d >= BANK_DEPOSIT_START else 0)
    
    df['Profit'] = df['Portfolio_Value'] - df['Invested_Capital']
    df['Return_Pct'] = (df['Profit'] / df['Invested_Capital']) * 100
    return df

# --- UI ---
st.title("💰 מעקב תיק השקעות אחוד")
fx = get_fx_rate()

if SHEET_URL != "YOUR_LINK_HERE":
    raw_data = load_data(SHEET_URL)
    df = calc_logic(raw_data, fx)
    latest = df.iloc[-1]
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("שווי כולל", f"₪{latest['Portfolio_Value']:,.0f}")
    c2.metric("רווח/הפסד נקי", f"₪{latest['Profit']:,.0f}", f"{latest['Return_Pct']:.2f}%")
    c3.metric("סך הפקדות (DCA)", f"₪{latest['Invested_Capital']:,.0f}")
    c4.metric("שער USD/ILS", f"{fx:.3f}")

    st.subheader("גרף צמיחה: שווי מול הפקדות")
    st.line_chart(df.set_index('Date')[['Portfolio_Value', 'Invested_Capital']])
    
    st.subheader("פילוח נכסים נוכחי")
    pie_data = {
        "IBKR": latest['IBKR_USD']*fx, "Blink": latest['BLINK_USD']*fx,
        "Kraken": latest['KRAKEN_USD']*fx, "Irish": latest['IRISH_ILS'],
        "Deposit": latest['Bank_Deposit']
    }
    st.bar_chart(pd.Series(pie_data))
    
    st.subheader("פירוט שבועי")
    st.dataframe(df[['Date', 'Portfolio_Value', 'Profit', 'Return_Pct']].sort_values('Date', ascending=False))
else:
    st.warning("אנא הזן את קישור ה-CSV מ-Google Sheets בקוד.")