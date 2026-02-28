import streamlit as st
import pandas as pd
import requests
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

UPBIT_DAP_URL = "https://uptax-notice.s3.ap-northeast-2.amazonaws.com/daily-average-prices.xlsx"

st.set_page_config(page_title="BTC 증여 최적 시점 분석", layout="wide")

st.title("📊 BTC 증여 최적 시점 분석 대시보드")

@st.cache_data(ttl=3600)
def load_data():
    response = requests.get(UPBIT_DAP_URL)
    df = pd.read_excel(response.content)

    # 업비트 공시파일은 보통 이런 컬럼을 포함
    # date / asset / daily_average_price 형식
    df.columns = [str(c).strip().lower() for c in df.columns]

    # BTC만 필터
    df = df[df.iloc[:,1].astype(str).str.upper() == "BTC"]

    # 날짜 + 가격 컬럼 고정 위치 사용
    df = df[[df.columns[0], df.columns[2]]]
    df.columns = ["date", "dap"]

    df["date"] = pd.to_datetime(df["date"])
    df["dap"] = pd.to_numeric(df["dap"], errors="coerce")

    df = df.sort_values("date").dropna()

    return df

df = load_data()

window = st.slider("선행 평균 기간 (일)", 7, 60, 30)

df["pre"] = df["dap"].rolling(window).mean()

st.subheader("📈 DAP vs PRE")

fig, ax = plt.subplots(figsize=(12,6))
ax.plot(df["date"], df["dap"], label="DAP", alpha=0.5)
ax.plot(df["date"], df["pre"], label=f"PRE ({window}일 평균)", linewidth=2)
ax.legend()
plt.xticks(rotation=45)
st.pyplot(fig)

st.subheader("🏆 최근 후보일 최저 PRE TOP 10")

recent_days = 30
recent_df = df.tail(recent_days).copy()
recent_df = recent_df.sort_values("pre")

top10 = recent_df.head(10)

for _, row in top10.iterrows():
    st.write(
        f"📅 {row['date'].date()} | PRE: {round(row['pre'],2)} KRW"
    )

st.subheader("📉 최근 하락 추세 분석")

recent_prices = df["dap"].tail(14).values
if len(recent_prices) >= 14:
    x = np.arange(len(recent_prices))
    slope = np.polyfit(x, recent_prices, 1)[0]

    if slope < 0:
        st.success(f"하락 추세 지속 중 (기울기 {round(slope,2)}) → 기다릴 가치 있음")
    else:
        st.warning(f"반등 추세 가능성 (기울기 {round(slope,2)}) → 빠른 증여 고려")

st.caption("데이터 출처: 업비트 일평균가액 공시")
