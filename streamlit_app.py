"""
7주차 1번 수업: 탭 구조 복원 및 전체 기능 통합 대시보드
"""
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="사용자 행동 탐색 대시보드", layout="wide")
st.title("사용자 행동 탐색 대시보드")
st.caption("주별 세션 퍼널 | 플랫폼 · 유입 경로별 | 2025.07 ~ 2026.06")

### ------------------------------------------------------------
### AI 해설 사전 정의
### ------------------------------------------------------------
AI_NOTES = {
    "전체": "전체 기간 세션 수는 28840개이며 주문 전환율은 14.5%, 결제 전환율은 80.5%이다. 가장 낮은 단계 전환율은 조회에서 장바구니로 이어지는 단계로 41.4%를 기록했다. 2026년 4월 하순부터 5월 말까지 일부 기간 동안 지표가 흔들린 모습이 확인되어 원인 파악이 필요하다.",
    "Android": "Android 집단의 세션 수는 16053개로 전체의 과반을 차지하며 주문 전환율은 14.3%, 결제 전환율은 76.8%로 전체 평균과 유사하다. 가장 낮은 단계 전환율은 조회에서 장바구니로 이어지는 41.8%이다. 2026-04-20 주부터 2026-06-01 주까지 결제 전환율이 크게 낮아지는 현상이 이어졌으며 결제 실패 이벤트 수가 급증해 시스템 오류 여부 확인이 필요하다.",
    "iOS": "iOS 집단의 세션 수는 12787개이며 주문 전환율은 14.8%, 결제 전환율은 85.5%로 Android 대비 결제 전환율이 다소 높다. 가장 낮은 단계 전환율은 조회에서 장바구니로 이어지는 40.8%이다. 2026-05-04 주와 2026-06-15 주에 결제 전환율이 단발성으로 하락한 바 있으나 지속되지는 않은 것으로 보인다.",
    "organic": "organic 유입의 세션 수는 22489개로 가장 큰 비중을 차지하며 주문 전환율은 16.0%, 결제 전환율은 80.4%로 전체 평균 수준이다. 가장 낮은 단계 전환율은 조회에서 장바구니로 이어지는 41.4%이다. 전체 트렌드와 유사하게 움직여 자연 유입 사용자의 평소 패턴으로 보인다.",
    "paid_ad": "paid_ad 유입의 세션 수는 1595개이며 주문 전환율은 26.3%, 결제 전환율은 90.3%로 다른 유입 경로에 비해 매우 높다. 가장 낮은 단계 전환율은 조회에서 장바구니로 이어지는 53.7%이다. 광고를 통해 유입된 사용자의 구매 의도가 높아 전환율이 우수한 것으로 보인다.",
    "push": "push 유입의 세션 수는 4635개이며 주문 전환율은 3.2%, 결제 전환율은 63.8%로 다른 경로 대비 크게 낮다. 가장 낮은 단계 전환율은 방문에서 조회로 이어지는 단계로 28.4%이다. 2026-02-02 주부터 푸시 유입이 처음 나타났으며 타겟팅 최적화 검토가 필요하다.",
    "referral": "referral 유입의 세션 수는 121개로 500개 미만이며 주문 전환율과 결제 전환율 모두 0.0%이다. 가장 낮은 단계 전환율은 결제시작에서 주문으로 이어지는 0.0%이다. 표본 크기가 매우 작아 지표 변동성이 클 수 있으므로 추가 데이터 확인이 필요하다."
}

AI_SOURCE = "출력된 해설은 주별 플랫폼 유입경로 퍼널 데이터를 기반으로 작성되었습니다."

# ------------------------------------------------------------
# 0. 필요한 데이터만 추출 — 쓸 테이블과 컬럼만 메모리 DB에 올리고, 정제 테이블 events를 처음 한 번만 만듦
# ------------------------------------------------------------
DATA_DIR = "data"                         # 원본 CSV를 넣어 둔 폴더
NEEDED = {                                 # 이번 대시보드에 필요한 테이블과 컬럼
    "app_events": ["event_id", "event_datetime", "customer_id", "session_id",
                   "event_name", "platform", "traffic_source"],
}

@st.cache_resource
def get_db():                              # 필요한 컬럼만 메모리 DB에 올리고, 정제 테이블 events를 만듦 (처음 한 번만)
    con = sqlite3.connect(":memory:", check_same_thread=False)
    for name, cols in NEEDED.items():
        pd.read_csv(f"{DATA_DIR}/{name}.csv", usecols=cols).to_sql(name, con, index=False)
    # 5주차 제외 규칙: QA 계정 제외 · 중복 이벤트 제거
    con.execute("""
        CREATE TABLE events AS
        SELECT event_id, event_datetime, customer_id, session_id, event_name, platform, traffic_source
          FROM (SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY session_id, event_datetime, event_name
                                          ORDER BY event_id) AS dup
                  FROM app_events
                 WHERE customer_id NOT LIKE 'QA%')
         WHERE dup = 1
    """)
    # 세션별로 묶는 집계가 빨라지도록 session_id에 인덱스를 붙임 (없으면 첫 실행이 몇 분 걸릴 수 있음)
    con.execute("CREATE INDEX idx_events_session ON events(session_id)")
    return con

# ------------------------------------------------------------
# 1. 데이터 준비 — 정제된 events 테이블을 SQL로 집계
# ------------------------------------------------------------
@st.cache_data
def query(sql):                            # SQL을 실행해 표로 돌려줌
    return pd.read_sql(sql, get_db())

# 주 × 플랫폼 × 유입 경로별 세션 퍼널
SQL_WEEKLY_FUNNEL = """
WITH s AS (                                 -- 세션의 첫 이벤트로 플랫폼 · 유입 경로 · 주 정하기
    SELECT session_id, platform, traffic_source,
           DATE(MIN(event_datetime), 'weekday 0', '-6 days') AS 주시작일
      FROM events
     GROUP BY session_id
)
SELECT s.주시작일,
       s.platform         AS 플랫폼,
       s.traffic_source AS 유입경로,
       COUNT(DISTINCT e.session_id)                                                                 AS 세션수,
       COUNT(DISTINCT CASE WHEN e.event_name = 'view_restaurant' THEN e.session_id END)   AS 조회세션,
       COUNT(DISTINCT CASE WHEN e.event_name = 'add_to_cart'      THEN e.session_id END)   AS 장바구니세션,
       COUNT(DISTINCT CASE WHEN e.event_name = 'begin_checkout'   THEN e.session_id END)   AS 결제시작세션,
       COUNT(DISTINCT CASE WHEN e.event_name = 'order_complete'   THEN e.session_id END)   AS 주문세션,
       SUM(CASE WHEN e.event_name = 'payment_fail' THEN 1 ELSE 0 END)                       AS 결제실패
  FROM events e
  JOIN s ON e.session_id = s.session_id
 WHERE s.주시작일 < '2026-06-29'            -- 이틀치뿐인 마지막 주 제외
 GROUP BY 1, 2, 3
 ORDER BY 1, 2, 3
"""

@st.cache_data
def load_data():
    data = query(SQL_WEEKLY_FUNNEL)
    data["주시작일"] = pd.to_datetime(data["주시작일"]).dt.date
    return data

df = load_data()                           # 주 × 플랫폼 × 유입 경로별 세션 퍼널

# ------------------------------------------------------------
# 사이드바 필터 설정 (필터 초기화 번호 적용)
# ------------------------------------------------------------
st.sidebar.header("필터")

if "filter_version" not in st.session_state:
    st.session_state["filter_version"] = 0

v = st.session_state["filter_version"]

if st.sidebar.button("필터 초기화"):
    st.session_state["filter_version"] += 1
    st.rerun()

dates = sorted(df["주시작일"].unique())
selected_dates = st.sidebar.select_slider(
    "기간",
    options=dates,
    value=(dates[0], dates[-1]),
    key=f"period_{v}"
)

platforms = sorted(df["플랫폼"].unique())
selected_platforms = st.sidebar.multiselect(
    "플랫폼",
    options=platforms,
    default=platforms,
    key=f"platforms_{v}"
)

traffic_sources = sorted(df["유입경로"].unique())
selected_traffic_sources = st.sidebar.multiselect(
    "유입 경로",
    options=traffic_sources,
    default=traffic_sources,
    key=f"traffic_sources_{v}"
)

# 고급 설정 (평소 범위 기준 기간 + 세션 500개 미만 집단 제외 체크박스)
default_end_idx = min(25, len(dates) - 1)
with st.sidebar.expander("고급 설정"):
    baseline_dates = st.select_slider(
        "평소 범위 기준 기간",
        options=dates,
        value=(dates[0], dates[default_end_idx]),
        help="문제가 없던 기간을 고르세요. 이 기간의 주별 값 범위를 '평소 범위'로 씁니다.",
        key=f"baseline_{v}"
    )
    exclude_low_session = st.checkbox(
        "세션 500개 미만 집단 제외 (집단 비교 · 드릴다운)",
        value=False,
        key=f"exclude_low_{v}"
    )

# 집단 조건(플랫폼·유입경로)만 적용한 데이터 g 생성
g = df[
    (df["플랫폼"].isin(selected_platforms)) &
    (df["유입경로"].isin(selected_traffic_sources))
]

# 기존 f는 g에 기간 조건까지 더해 만듦
f = g[
    (g["주시작일"] >= selected_dates[0]) &
    (g["주시작일"] <= selected_dates[1])
]

# ------------------------------------------------------------
# 사이드바 맨 아래 다운로드 버튼 추가
# ------------------------------------------------------------
st.sidebar.html("<div style='margin-top: 30px;'></div>")
st.sidebar.subheader("데이터 다운로드")
dl_col1, dl_col2 = st.sidebar.columns(2)

with dl_col1:
    st.download_button(
        label="전체 다운로드",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="전체_데이터.csv",
        mime="text/csv",
        width="stretch"
    )

with dl_col2:
    st.download_button(
        label="부분 다운로드",
        data=f.to_csv(index=False).encode("utf-8-sig"),
        file_name="필터적용_데이터.csv",
        mime="text/csv",
        width="stretch"
    )

# f가 비어 있으면 경고 표시 후 중단
if f.empty:
    st.warning("선택한 조건에 해당하는 데이터가 없습니다. 필터를 바꿔 주세요.")
    st.stop()

# ------------------------------------------------------------
# 보고 있는 조건 표시 st.caption 추가
# ------------------------------------------------------------
all_dates_set = set(dates)
f_dates_set = set(sorted(f["주시작일"].unique()))
if f_dates_set == all_dates_set or (selected_dates[0] == dates[0] and selected_dates[1] == dates[-1]):
    period_str = "전체"
elif not selected_dates:
    period_str = "선택 없음"
else:
    period_str = f"{selected_dates[0]} ~ {selected_dates[1]}"

if not selected_platforms:
    platform_str = "선택 없음"
elif len(selected_platforms) == len(platforms):
    platform_str = "전체"
else:
    platform_str = ", ".join(selected_platforms)

if not selected_traffic_sources:
    traffic_str = "선택 없음"
elif len(selected_traffic_sources) == len(traffic_sources):
    traffic_str = "전체"
else:
    traffic_str = ", ".join(selected_traffic_sources)

st.caption(f"🔎 보고 있는 조건: 기간 ({period_str}) · 플랫폼 ({platform_str}) · 유입 경로 ({traffic_str})")

# ------------------------------------------------------------
# 탭 구성 (개요, 탐색, 액션)
# ------------------------------------------------------------
tab_overview, tab_explore, tab_action = st.tabs(["📊 개요", "🔍 탐색", "✅ 액션"])

with tab_overview:
    st.caption("이 탭에서 볼 수 있는 것: KPI 카드, 규칙 기반 숫자 해설, 전체 AI 해설, 주별 결제 전환율, 세션 퍼널, 유입 경로별 주문 전환율")

    # ------------------------------------------------------------
    # 2. KPI 카드
    # ------------------------------------------------------------
    def rate(a, b):
        return a / b * 100 if b else 0

    t = f[["세션수", "결제시작세션", "주문세션"]].sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("세션 수", f"{t['세션수']:,}개")
    c2.metric("주문 전환율 (방문 → 주문)", f"{rate(t['주문세션'], t['세션수']):.1f}%")
    c3.metric("결제 전환율 (결제 시작 → 주문)", f"{rate(t['주문세션'], t['결제시작세션']):.1f}%")

    # ------------------------------------------------------------
    # 규칙 기반 설명 문장 및 AI 해설 통합 컨테이너
    # ------------------------------------------------------------
    with st.container(border=True):
        st.markdown("**📏 지금 숫자 읽기**")

        f_weeks_count = f["주시작일"].nunique()
        g_baseline = g[(g["주시작일"] >= baseline_dates[0]) & (g["주시작일"] <= baseline_dates[1])]

        if f_weeks_count < 4:
            st.markdown("- 주문 전환율(방문 → 주문): 비교하려면 선택 기간을 4주 이상 골라 주세요")
            st.markdown("- 결제 전환율(결제 시작 → 주문): 비교하려면 선택 기간을 4주 이상 골라 주세요")
        elif len(g_baseline.groupby("주시작일").sum()) < 4:
            st.markdown("- 주문 전환율(방문 → 주문): 기준 기간을 이 집단의 데이터가 있는 시기로 옮겨 주세요")
            st.markdown("- 결제 전환율(결제 시작 → 주문): 기준 기간을 이 집단의 데이터가 있는 시기로 옮겨 주세요")
        else:
            sorted_f_dates = sorted(f["주시작일"].unique())
            recent_4weeks_dates = sorted_f_dates[-4:]
            recent_start_date = recent_4weeks_dates[0]
            
            f_recent = f[f["주시작일"].isin(recent_4weeks_dates)]
            t_recent = f_recent[["세션수", "결제시작세션", "주문세션"]].sum()
            
            current_order_rate = rate(t_recent["주문세션"], t_recent["세션수"])
            current_payment_rate = rate(t_recent["주문세션"], t_recent["결제시작세션"])
            
            g_weekly = g_baseline.groupby("주시작일")[["세션수", "결제시작세션", "주문세션"]].sum().reset_index()
            
            order_rates_weekly = []
            for _, row in g_weekly.iterrows():
                if row["세션수"] > 0:
                    order_rates_weekly.append(row["주문세션"] / row["세션수"] * 100)
                    
            payment_rates_weekly = []
            for _, row in g_weekly.iterrows():
                if row["결제시작세션"] > 0:
                    payment_rates_weekly.append(row["주문세션"] / row["결제시작세션"] * 100)
                    
            if len(order_rates_weekly) < 4 or len(payment_rates_weekly) < 4:
                st.markdown("- 주문 전환율(방문 → 주문): 기준 기간을 이 집단의 데이터가 있는 시기로 옮겨 주세요")
                st.markdown("- 결제 전환율(결제 시작 → 주문): 기준 기간을 이 집단의 데이터가 있는 시기로 옮겨 주세요")
            else:
                ord_min, ord_max = min(order_rates_weekly), max(order_rates_weekly)
                pay_min, pay_max = min(payment_rates_weekly), max(payment_rates_weekly)

                if current_order_rate < ord_min:
                    diff = ord_min - current_order_rate
                    msg_order = f"주문 전환율(방문 → 주문): {recent_start_date} 주부터 4주간 주문 전환율이 {current_order_rate:.1f}%로, 평소 범위({ord_min:.1f}% ~ {ord_max:.1f}%)보다 {diff:.1f}%p 낮습니다."
                elif current_order_rate > ord_max:
                    diff = current_order_rate - ord_max
                    msg_order = f"주문 전환율(방문 → 주문): {recent_start_date} 주부터 4주간 주문 전환율이 {current_order_rate:.1f}%로, 평소 범위({ord_min:.1f}% ~ {ord_max:.1f}%)보다 {diff:.1f}%p 높습니다."
                else:
                    msg_order = f"주문 전환율(방문 → 주문): {recent_start_date} 주부터 4주간 주문 전환율이 {current_order_rate:.1f}%로, 평소 범위({ord_min:.1f}% ~ {ord_max:.1f}%) 안에 있습니다."

                if current_payment_rate < pay_min:
                    diff = pay_min - current_payment_rate
                    msg_payment = f"결제 전환율(결제 시작 → 주문): {recent_start_date} 주부터 4주간 결제 전환율이 {current_payment_rate:.1f}%로, 평소 범위({pay_min:.1f}% ~ {pay_max:.1f}%)보다 {diff:.1f}%p 낮습니다."
                elif current_payment_rate > pay_max:
                    diff = current_payment_rate - pay_max
                    msg_payment = f"결제 전환율(결제 시작 → 주문): {recent_start_date} 주부터 4주간 결제 전환율이 {current_payment_rate:.1f}%로, 평소 범위({pay_min:.1f}% ~ {pay_max:.1f}%)보다 {diff:.1f}%p 높습니다."
                else:
                    msg_payment = f"결제 전환율(결제 시작 → 주문): {recent_start_date} 주부터 4주간 결제 전환율이 {current_payment_rate:.1f}%로, 평소 범위({pay_min:.1f}% ~ {pay_max:.1f}%) 안에 있습니다."

                st.markdown(f"- {msg_order}")
                st.markdown(f"- {msg_payment}")

        st.caption(f"📏 자동 계산 · 평소 범위 기준 기간 {baseline_dates[0]} ~ {baseline_dates[1]} (주별 값)")

        with st.expander("🤖 AI 해설 · 전체", expanded=False):
            st.write(AI_NOTES.get("전체", "이 집단의 해설은 아직 없습니다."))
            st.caption(AI_SOURCE)

    st.divider()

    # ------------------------------------------------------------
    # 3. 차트
    # ------------------------------------------------------------
    left, right = st.columns(2)

    # 3-1. 주별 결제 전환율 (플랫폼별)
    wp = f.groupby(["주시작일", "플랫폼"])[["결제시작세션", "주문세션"]].sum().reset_index()
    wp["결제전환율"] = (wp["주문세션"] / wp["결제시작세션"] * 100).round(1)
    fig1 = px.line(
        wp, x="주시작일", y="결제전환율", color="플랫폼", markers=True,
        title="주별 결제 전환율 (플랫폼별)",
        labels={"주시작일": "주시작일", "결제전환율": "결제 전환율 (%)", "플랫폼": "플랫폼"}
    )
    fig1.update_layout(yaxis_title="결제 전환율 (%)", xaxis_title="주시작일")
    left.plotly_chart(fig1, width="stretch")

    # 3-2. 세션 퍼널
    steps = {"1.방문": "세션수", "2.식당조회": "조회세션", "3.장바구니": "장바구니세션",
             "4.결제시작": "결제시작세션", "5.주문완료": "주문세션"}
    fun = pd.DataFrame({"단계": list(steps), "세션수": [f[c].sum() for c in steps.values()]})
    fig2 = px.funnel(
        fun, x="세션수", y="단계",
        title="세션 퍼널",
        labels={"세션수": "세션 수(개)", "단계": "퍼널 단계"}
    )
    fig2.update_layout(xaxis_title="세션 수(개)", yaxis_title="퍼널 단계")
    right.plotly_chart(fig2, width="stretch")

    # 3-3. 유입 경로별 주문 전환율
    ws = f.groupby("유입경로")[["세션수", "주문세션"]].sum().reset_index()
    ws["주문전환율"] = (ws["주문세션"] / ws["세션수"] * 100).round(1)
    ws = ws.sort_values("주문전환율")
    fig3 = px.bar(
        ws, x="주문전환율", y="유입경로", orientation="h", text_auto=".1f",
        hover_data={"세션수": True},
        title="유입 경로별 주문 전환율",
        labels={"주문전환율": "주문 전환율 (%)", "유입경로": "유입 경로", "세션수": "세션 수(개)"}
    )
    fig3.update_xaxes(range=[0, ws["주문전환율"].max() * 1.2] if not ws.empty else [0, 100])
    fig3.update_layout(xaxis_title="주문 전환율 (%)", yaxis_title="유입 경로")
    st.plotly_chart(fig3, width="stretch")

with tab_explore:
    st.caption("이 탭에서 볼 수 있는 것: 집단 비교(누적 전환율 퍼널, 단계 전환율 막대), 드릴다운 분석, 집단별 AI 해설")

    # ------------------------------------------------------------
    # 4. 집단 비교 영역
    # ------------------------------------------------------------
    st.subheader("집단 비교")
    group_col_label = st.radio("비교 기준", ["플랫폼", "유입경로"], horizontal=True)
    group_col = "플랫폼" if group_col_label == "플랫폼" else "유입경로"

    group_agg = f.groupby(group_col)[["세션수", "조회세션", "장바구니세션", "결제시작세션", "주문세션"]].sum().reset_index()

    if exclude_low_session:
        excluded_groups = group_agg[group_agg["세션수"] < 500][group_col].tolist()
        if excluded_groups:
            st.caption(f"제외한 집단: {', '.join(excluded_groups)} (세션 500개 미만)")
        group_agg = group_agg[group_agg["세션수"] >= 500]

    low_session_groups = group_agg[group_agg["세션수"] < 500][group_col].tolist()
    if not exclude_low_session and low_session_groups:
        st.caption(f"⚠️ 세션 수가 500개 미만인 집단({', '.join(low_session_groups)})이 있어 값이 크게 흔들릴 수 있습니다.")

    col_comp1, col_comp2 = st.columns(2)

    with col_comp1:
        funnel_melted = group_agg.melt(
            id_vars=[group_col],
            value_vars=["세션수", "조회세션", "장바구니세션", "결제시작세션", "주문세션"],
            var_name="단계",
            value_name="세션수값"
        )
        step_mapping = {
            "세션수": "1.방문",
            "조회세션": "2.식당조회",
            "장바구니세션": "3.장바구니",
            "결제시작세션": "4.결제시작",
            "주문세션": "5.주문완료"
        }
        funnel_melted["단계"] = funnel_melted["단계"].map(step_mapping)
        
        first_vals = group_agg.set_index(group_col)["세션수"]
        funnel_melted["첫단계세션수"] = funnel_melted[group_col].map(first_vals)
        funnel_melted["누적전환율"] = (funnel_melted["세션수값"] / funnel_melted["첫단계세션수"] * 100).round(1)
        
        fig_comp1 = px.funnel(
            funnel_melted,
            x="누적전환율",
            y="단계",
            color=group_col,
            title="집단별 누적 전환율 퍼널 (첫 단계 대비 %)",
            labels={"누적전환율": "누적 전환율 (%)", "단계": "퍼널 단계", group_col: group_col}
        )
        fig_comp1.update_layout(xaxis_title="누적 전환율 (%)", yaxis_title="퍼널 단계")
        st.plotly_chart(fig_comp1, width="stretch")

    with col_comp2:
        rate_rows = []
        for _, row in group_agg.iterrows():
            g_name = row[group_col]
            s_vis = row["세션수"]
            s_view = row["조회세션"]
            s_cart = row["장바구니세션"]
            s_chk = row["결제시작세션"]
            s_ord = row["주문세션"]
            
            rate_rows.append({
                group_col: g_name,
                "단계": "2.식당조회 (방문→조회)",
                "전환율": round(s_view / s_vis * 100, 1) if s_vis else 0,
                "직전 단계 세션 수(개)": s_vis
            })
            rate_rows.append({
                group_col: g_name,
                "단계": "3.장바구니 (조회→장바구니)",
                "전환율": round(s_cart / s_view * 100, 1) if s_view else 0,
                "직전 단계 세션 수(개)": s_view
            })
            rate_rows.append({
                group_col: g_name,
                "단계": "4.결제시작 (장바구니→결제)",
                "전환율": round(s_chk / s_cart * 100, 1) if s_cart else 0,
                "직전 단계 세션 수(개)": s_cart
            })
            rate_rows.append({
                group_col: g_name,
                "단계": "5.주문완료 (결제→주문)",
                "전환율": round(s_ord / s_chk * 100, 1) if s_chk else 0,
                "직전 단계 세션 수(개)": s_chk
            })
            
        df_rate = pd.DataFrame(rate_rows)
        
        fig_comp2 = px.bar(
            df_rate,
            x="단계",
            y="전환율",
            color=group_col,
            barmode="group",
            text_auto=".1f",
            hover_data={"직전 단계 세션 수(개)": True},
            title="집단별 단계 전환율 (직전 단계 대비 %)",
            labels={"전환율": "단계 전환율 (%)", "단계": "퍼널 단계", group_col: group_col}
        )
        fig_comp2.update_layout(yaxis_title="단계 전환율 (%)", xaxis_title="퍼널 단계")
        st.plotly_chart(fig_comp2, width="stretch")

    st.divider()

    # ------------------------------------------------------------
    # 5. 드릴다운: 언제부터, 무엇 때문일까 영역
    # ------------------------------------------------------------
    st.subheader("드릴다운: 언제부터, 무엇 때문일까")

    f_for_drill = f.copy()
    if exclude_low_session:
        group_totals = f.groupby(group_col)["세션수"].sum()
        valid_groups = group_totals[group_totals >= 500].index.tolist()
        f_for_drill = f[f[group_col].isin(valid_groups)]

    available_groups = sorted(f_for_drill[group_col].unique())

    col_dd1, col_dd2 = st.columns(2)
    with col_dd1:
        selected_group = st.selectbox("자세히 볼 집단", options=available_groups if available_groups else ["선택 가능한 집단 없음"])
    with col_dd2:
        selected_step_name = st.selectbox(
            "단계",
            options=["방문 → 식당조회", "식당조회 → 장바구니", "장바구니 → 결제시작", "결제시작 → 주문"]
        )

    if available_groups:
        step_column_mapping = {
            "방문 → 식당조회": ("조회세션", "세션수"),
            "식당조회 → 장바구니": ("장바구니세션", "조회세션"),
            "장바구니 → 결제시작": ("결제시작세션", "장바구니세션"),
            "결제시작 → 주문": ("주문세션", "결제시작세션")
        }
        num_col, den_col = step_column_mapping[selected_step_name]

        other_col = "유입경로" if group_col == "플랫폼" else "플랫폼"

        df_drill = f_for_drill[f_for_drill[group_col] == selected_group].groupby(["주시작일", other_col])[[num_col, den_col]].sum().reset_index()

        df_drill["전환율"] = df_drill.apply(
            lambda row: round(row[num_col] / row[den_col] * 100, 1) if row[den_col] > 0 else None,
            axis=1
        )

        fig_drill1 = px.line(
            df_drill,
            x="주시작일",
            y="전환율",
            color=other_col,
            markers=True,
            title=f"① {selected_group}의 주별 {selected_step_name} 전환율 — {other_col}별로 쪼개 보기",
            labels={"주시작일": "주시작일", "전환율": "전환율 (%)", other_col: other_col}
        )
        fig_drill1.update_layout(yaxis_title="전환율 (%)", xaxis_title="주시작일")
        st.plotly_chart(fig_drill1, width="stretch")
        st.caption("모든 갈래가 같은 시점에 함께 움직였다면, 그 축은 원인이 아닙니다.")

        f_copy = f_for_drill.copy()
        f_copy["대상집단"] = f_copy[group_col].apply(lambda x: selected_group if x == selected_group else "그 외")

        df_fail = f_copy.groupby(["주시작일", "대상집단"])["결제실패"].sum().reset_index()

        color_map = {selected_group: "#d62728", "그 외": "#7f7f7f"}

        fig_drill2 = px.bar(
            df_fail,
            x="주시작일",
            y="결제실패",
            color="대상집단",
            barmode="group",
            color_discrete_map=color_map,
            title=f"② 주별 결제 실패 건수 ({selected_group} vs 그 외)",
            labels={"주시작일": "주시작일", "결제실패": "결제 실패 이벤트 수(건)", "대상집단": "비교 집단"}
        )
        fig_drill2.update_layout(yaxis_title="결제 실패 이벤트 수(건)", xaxis_title="주시작일")
        st.plotly_chart(fig_drill2, width="stretch")
        st.caption("문제가 생긴 시점과 함께 움직였다면 원인 후보입니다. 함께 움직였다고 원인이 확정되지는 않습니다.")

        target = selected_group
        with st.expander(f"🤖 AI 해설 · {target}", expanded=False):
            if target in AI_NOTES:
                st.write(AI_NOTES[target])
            else:
                st.write("이 집단의 해설은 아직 없습니다.")
            st.caption(AI_SOURCE)
    else:
        st.info("조건에 부합하는 집단이 없습니다.")

with tab_action:
    st.caption("이 탭에서 볼 수 있는 것: 액션 및 개선 제안 카드 (다음 단계에서 추가 예정)")
    st.caption("액션 카드는 다음 단계에서 추가합니다.")