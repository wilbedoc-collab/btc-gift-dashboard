import streamlit as st
import pandas as pd
import requests
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

UPBIT_DAP_URL = "https://uptax-notice.s3.ap-northeast-2.amazonaws.com/daily-average-prices.xlsx"

st.set_page_config(page_title="BTC 증여 최적 시점 분석", layout="wide")

st.title("📊 BTC 증여 최적 시점 분석 대시보드")

@st.cache_data(ttl=3600)
def load_data():
    response = requests.get(UPBIT_DAP_URL)
    df = pd.read_excel(response.content)

    # 컬럼 정리
    df.columns = [str(c).strip().lower().replace(" ", "") for c in df.columns]

    # 날짜/자산/가격 컬럼 찾기
    date_col = [c for c in df.columns if "date" in c or "일" in c][0]
    asset_col = [c for c in df.columns if "asset" in c or "ticker" in c or "코인" in c][0]
    price_col = [c for c in df.columns if "평균" in c or "price" in c][0]

    df = df[[date_col, asset_col, price_col]]
    df.columns = ["date", "asset", "dap"]

    df = df[df["asset"].str.upper() == "BTC"]
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    df["dap"] = pd.to_numeric(df["dap"], errors="coerce")

    return df.dropna()

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

# 추세 점수
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
