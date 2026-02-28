import streamlit as st
import pandas as pd
import requests
import numpy as np
import matplotlib.pyplot as plt

UPBIT_DAP_URL = "https://uptax-notice.s3.ap-northeast-2.amazonaws.com/daily-average-prices.xlsx"

st.set_page_config(page_title="BTC 증여 최적 시점 분석", layout="wide")
st.title("📊 BTC 증여 최적 시점 분석 대시보드")

def _pick_date_col(df: pd.DataFrame) -> str | None:
    """날짜로 변환 성공률이 가장 높은 컬럼을 date_col로 선택"""
    best_col, best_score = None, -1.0
    for c in df.columns:
        s = pd.to_datetime(df[c], errors="coerce")
        score = s.notna().mean()
        if score > best_score:
            best_score = score
            best_col = c
    # 너무 낮으면 날짜 컬럼으로 보기 어려움
    return best_col if best_score >= 0.5 else None

def _wide_format_to_btc(df: pd.DataFrame) -> pd.DataFrame | None:
    """가로형(날짜 + BTC컬럼 존재) 탐지/파싱"""
    date_col = _pick_date_col(df)
    if date_col is None:
        return None

    # 컬럼명에 BTC가 들어있는 컬럼 찾기
    btc_cols = [c for c in df.columns if "btc" in str(c).lower()]
    if not btc_cols:
        return None

    btc_col = btc_cols[0]
    out = df[[date_col, btc_col]].copy()
    out.columns = ["date", "dap"]
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["dap"] = pd.to_numeric(out["dap"], errors="coerce")
    out = out.dropna().sort_values("date")
    return out if len(out) > 10 else None

def _long_format_to_btc(df: pd.DataFrame) -> pd.DataFrame | None:
    """세로형(날짜/자산/가격) 탐지/파싱: 컬럼명을 추측하지 않고 '값' 기반으로 찾음"""
    date_col = _pick_date_col(df)
    if date_col is None:
        return None

    # asset 후보: 문자열 비율 높고, 값에 BTC가 포함되는 컬럼
    asset_cands = []
    for c in df.columns:
        if c == date_col:
            continue
        col = df[c].astype(str)
        str_ratio = col.notna().mean()
        has_btc = col.str.upper().str.contains("BTC", na=False).mean()
        # 문자열이 어느 정도 있고 BTC가 어느 정도 등장하면 후보
        if str_ratio > 0.7 and has_btc > 0.01:
            asset_cands.append((c, has_btc))
    if not asset_cands:
        return None
    asset_col = sorted(asset_cands, key=lambda x: x[1], reverse=True)[0][0]

    # price 후보: 숫자로 잘 변환되고 분산이 있는 컬럼
    price_cands = []
    for c in df.columns:
        if c in (date_col, asset_col):
            continue
        num = pd.to_numeric(df[c], errors="coerce")
        valid = num.notna().mean()
        if valid > 0.5:
            # 값이 거의 상수면 제외
            std = float(num.dropna().std()) if num.notna().sum() > 5 else 0.0
            price_cands.append((c, valid, std))
    if not price_cands:
        return None
    # 유효비율 우선, 표준편차 보조
    price_col = sorted(price_cands, key=lambda x: (x[1], x[2]), reverse=True)[0][0]

    out = df[[date_col, asset_col, price_col]].copy()
    out.columns = ["date", "asset", "dap"]
    out["asset"] = out["asset"].astype(str).str.upper().str.strip()
    out = out[out["asset"].str.contains("BTC", na=False)]
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["dap"] = pd.to_numeric(out["dap"], errors="coerce")
    out = out.dropna(subset=["date", "dap"]).sort_values("date")
    out = out[["date", "dap"]]
    return out if len(out) > 10 else None

@st.cache_data(ttl=3600)
def load_btc_dap():
    r = requests.get(UPBIT_DAP_URL, timeout=30)
    r.raise_for_status()

    # 업비트 파일이 시트 여러 개일 수 있어 전체 시트 훑기
    xls = pd.ExcelFile(r.content)
    last_debug = None

    for sheet in xls.sheet_names:
        raw = xls.parse(sheet_name=sheet)
        if raw is None or raw.empty:
            continue

        # wide 먼저 시도 → 실패하면 long
        wide = _wide_format_to_btc(raw)
        if wide is not None:
            return wide, {"sheet": sheet, "format": "wide", "columns": list(raw.columns)}

        long = _long_format_to_btc(raw)
        if long is not None:
            return long, {"sheet": sheet, "format": "long", "columns": list(raw.columns)}

        last_debug = {"sheet": sheet, "columns": list(raw.columns), "head": raw.head(3).to_dict()}

    # 전 시트 실패 시 디버그 정보 반환
    return None, last_debug

df, meta = load_btc_dap()

if df is None:
    st.error("업비트 엑셀 구조를 자동 인식하지 못했습니다. 아래 정보(컬럼/미리보기)를 확인해주세요.")
    st.write(meta)
    st.stop()

st.caption(f"파싱 성공 ✅ | sheet={meta.get('sheet')} | format={meta.get('format')}")

window = st.slider("선행 평균 기간 (일)", 7, 60, 30)
df["pre"] = df["dap"].rolling(window).mean()

st.subheader("📈 DAP vs PRE")
fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(df["date"], df["dap"], label="DAP(일평균가액)", alpha=0.5)
ax.plot(df["date"], df["pre"], label=f"PRE({window}일 평균)", linewidth=2)
ax.legend()
plt.xticks(rotation=45)
st.pyplot(fig)

st.subheader("🏆 최근 30일 후보 중 PRE 최저 TOP 10")
recent_df = df.tail(30).copy().sort_values("pre")
top10 = recent_df.head(10)

for _, row in top10.iterrows():
    st.write(f"📅 {row['date'].date()} | PRE: {round(float(row['pre']), 2)} KRW")

st.subheader("📉 최근 14일 하락 추세(기울기)")
recent_prices = df["dap"].tail(14).values
if len(recent_prices) >= 14:
    x = np.arange(len(recent_prices))
    slope = np.polyfit(x, recent_prices, 1)[0]
    if slope < 0:
        st.success(f"하락 추세 지속 (slope={round(float(slope), 2)}) → 기다릴 가치 ↑")
    else:
        st.warning(f"반등/횡보 가능 (slope={round(float(slope), 2)}) → 증여 타이밍 점검")

st.caption("데이터 출처: 업비트 일평균가액 공시")
