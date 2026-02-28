import streamlit as st
import pandas as pd
import requests
import numpy as np
import matplotlib.pyplot as plt
from datetime import date, timedelta

UPBIT_DAP_URL = "https://uptax-notice.s3.ap-northeast-2.amazonaws.com/daily-average-prices.xlsx"

st.set_page_config(page_title="BTC 증여 최적 시점 분석", layout="wide")
st.title("📊 BTC 증여 최적 시점 분석 대시보드 (세무 기준 VAL 포함)")

@st.cache_data(ttl=3600)
def load_btc_dap_from_sheetnames():
    r = requests.get(UPBIT_DAP_URL, timeout=30)
    r.raise_for_status()

    xls = pd.ExcelFile(r.content)

    rows = []
    for sheet in xls.sheet_names:
        # 시트명이 날짜 형태일 때만 사용
        try:
            d = pd.to_datetime(sheet, errors="raise").date()
        except Exception:
            continue

        df = xls.parse(sheet_name=sheet)
        if df is None or df.empty:
            continue

        df.columns = [str(c).strip() for c in df.columns]

        # 컬럼 찾기(확정 구조: 심볼 / 일평균가)
        sym_col = "심볼" if "심볼" in df.columns else next((c for c in df.columns if "심볼" in c), None)
        price_col = "일평균가" if "일평균가" in df.columns else next((c for c in df.columns if "평균" in c), None)
        if not sym_col or not price_col:
            continue

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

def compute_pre_and_val(df: pd.DataFrame, window_days: int = 30):
    """
    df: columns [date, dap] (date는 datetime64)
    PRE(t) = mean(dap[t-window_days .. t])  -> 31일
    VAL(t) = mean(dap[t-window_days .. t+window_days]) -> 61일 (세무 평가액)
    """
    df = df.sort_values("date").reset_index(drop=True).copy()
    df["pre"] = df["dap"].rolling(window_days + 1).mean()

    # VAL: centered rolling (61일). 양쪽 데이터가 있어야 값이 생김.
    df["val"] = df["dap"].rolling(2 * window_days + 1, center=True).mean()
    return df

df = load_btc_dap_from_sheetnames()
if df.empty:
    st.error("BTC 데이터를 찾지 못했습니다. 업비트 엑셀 구조/심볼명이 변경됐을 수 있습니다.")
    st.stop()

window = st.slider("평균 기간 window (±일)", 7, 60, 30)
candidate_days = st.slider("최근 후보일 범위 (일)", 7, 90, 30)

df2 = compute_pre_and_val(df, window_days=window)

# --- 그래프
st.subheader("📈 DAP / PRE / VAL(세무 기준)")
fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(df2["date"], df2["dap"], label="DAP(일평균가액)", alpha=0.35)
ax.plot(df2["date"], df2["pre"], label=f"PRE(선행 {window}일)", linewidth=2)
ax.plot(df2["date"], df2["val"], label=f"VAL(세무: ±{window}일 평균)", linewidth=2)
ax.legend()
plt.xticks(rotation=45)
st.pyplot(fig)

# --- 후보일 구간
recent = df2.tail(candidate_days).copy()

# PRE TOP10
st.subheader(f"🏆 최근 {candidate_days}일 후보 중 PRE 최저 TOP 10 (실시간 의사결정용)")
pre_top = recent.dropna(subset=["pre"]).sort_values("pre").head(10)
for _, row in pre_top.iterrows():
    st.write(f"📅 {row['date'].date()} | PRE: {round(float(row['pre']), 2)} KRW")

# VAL TOP10 (VAL은 양쪽 데이터가 필요하므로 결측 제거)
st.subheader(f"🏆 최근 {candidate_days}일 후보 중 VAL 최저 TOP 10 (세무 평가액 기준)")
val_top = recent.dropna(subset=["val"]).sort_values("val").head(10)
if val_top.empty:
    st.info("현재 선택한 후보 구간에서는 VAL이 계산되지 않습니다. (미래 ±window 데이터가 부족)")
else:
    for _, row in val_top.iterrows():
        st.write(f"📅 {row['date'].date()} | VAL: {round(float(row['val']), 2)} KRW")

# --- 추세(14일)
st.subheader("📉 최근 14일 하락 추세(기울기, DAP 기준)")
recent_prices = df2["dap"].tail(14).values
if len(recent_prices) >= 14:
    x = np.arange(len(recent_prices))
    slope = np.polyfit(x, recent_prices, 1)[0]
    if slope < 0:
        st.success(f"하락 추세 지속 (slope={round(float(slope), 2)}) → 기다릴 가치 ↑")
    else:
        st.warning(f"반등/횡보 가능 (slope={round(float(slope), 2)}) → 증여 타이밍 점검")

st.caption("데이터 출처: 업비트 일평균가액 공시 (시트명=날짜, 컬럼=심볼/일평균가)")
