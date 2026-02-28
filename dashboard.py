import streamlit as st
import pandas as pd
import requests
import numpy as np
import matplotlib.pyplot as plt
from datetime import date, timedelta

UPBIT_DAP_URL = "https://uptax-notice.s3.ap-northeast-2.amazonaws.com/daily-average-prices.xlsx"

st.set_page_config(page_title="BTC 증여 최적 시점 분석", layout="wide")
st.title("📊 BTC 증여 최적 시점 분석 대시보드")

@st.cache_data(ttl=3600)
def load_btc_dap_from_sheetnames():
    r = requests.get(UPBIT_DAP_URL, timeout=30)
    r.raise_for_status()

    xls = pd.ExcelFile(r.content)

    rows = []
    # 시트명이 '2021-12-01' 같은 날짜 형태
    for sheet in xls.sheet_names:
        try:
            d = pd.to_datetime(sheet, errors="raise").date()
        except Exception:
            continue

        df = xls.parse(sheet_name=sheet)
        if df is None or df.empty:
            continue

        # 컬럼명 정리
        df.columns = [str(c).strip() for c in df.columns]

        # 현재 확인된 구조: ['심볼', '일평균가']
        if "심볼" not in df.columns or "일평균가" not in df.columns:
            # 혹시 공백/철자 변형 대비
            sym_col = next((c for c in df.columns if "심볼" in c), None)
            price_col = next((c for c in df.columns if "평균" in c), None)
            if not sym_col or not price_col:
                continue
        else:
            sym_col, price_col = "심볼", "일평균가"

        # BTC만 추출
        sub = df[[sym_col, price_col]].copy()
        sub[sym_col] = sub[sym_col].astype(str).str.upper().str.strip()

        btc = sub[sub[sym_col] == "BTC"]
        if btc.empty:
            continue

        dap = pd.to_numeric(btc[price_col].iloc[0], errors="coerce")
        if pd.isna(dap):
            continue

        rows.append({"date": pd.to_datetime(d), "dap": float(dap)})

    out = pd.DataFrame(rows).sort_values("date").dropna()
    return out

df = load_btc_dap_from_sheetnames()

if df.empty:
    st.error("BTC 데이터를 찾지 못했습니다. 업비트 엑셀 구조/심볼명이 변경됐을 수 있습니다.")
    st.stop()

# --- UI 설정
window = st.slider("선행 평균 기간 (일)", 7, 60, 30)
candidate_days = st.slider("최근 후보일 범위 (일)", 7, 60, 30)

df["pre"] = df["dap"].rolling(window).mean()

# --- 그래프
st.subheader("📈 DAP vs PRE")
fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(df["date"], df["dap"], label="DAP(일평균가액)", alpha=0.5)
ax.plot(df["date"], df["pre"], label=f"PRE({window}일 평균)", linewidth=2)
ax.legend()
plt.xticks(rotation=45)
st.pyplot(fig)

# --- 후보일 TOP10
st.subheader(f"🏆 최근 {candidate_days}일 후보 중 PRE 최저 TOP 10")
recent_df = df.tail(candidate_days).copy().sort_values("pre")
top10 = recent_df.head(10)

for _, row in top10.iterrows():
    st.write(f"📅 {row['date'].date()} | PRE: {round(float(row['pre']), 2)} KRW")

# --- 추세(14일)
st.subheader("📉 최근 14일 하락 추세(기울기)")
recent_prices = df["dap"].tail(14).values
if len(recent_prices) >= 14:
    x = np.arange(len(recent_prices))
    slope = np.polyfit(x, recent_prices, 1)[0]
    if slope < 0:
        st.success(f"하락 추세 지속 (slope={round(float(slope), 2)}) → 기다릴 가치 ↑")
    else:
        st.warning(f"반등/횡보 가능 (slope={round(float(slope), 2)}) → 증여 타이밍 점검")

st.caption("데이터 출처: 업비트 일평균가액 공시 (시트명=날짜, 컬럼=심볼/일평균가)")
