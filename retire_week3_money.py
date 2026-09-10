import pandas as pd
import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title="Money Time Machine · 3주차", page_icon="⏳", layout="wide")

CLASSES = ["인하대", "숙대1", "숙대2"]
PHASES = [
    "대기", "학생입장", "TVM 타임머신", "현금흐름 실험실",
    "수익률 탐정", "기대수익률 실험", "요구수익률 조립", "결과", "종료"
]

T_STATUS = "retire_w3_status"
T_STUDENTS = "retire_w3_students"
T_RESPONSES = "retire_w3_responses"


@st.cache_resource
def init_connection() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


supabase: Client = init_connection()
PROF_PASSWORD = st.secrets.get("PROF_PASSWORD", "")


def get_status(class_name: str) -> dict:
    rows = supabase.table(T_STATUS).select("*").eq("class_name", class_name).execute().data
    if not rows:
        supabase.table(T_STATUS).insert({"class_name": class_name, "phase": "대기"}).execute()
        return {"class_name": class_name, "phase": "대기"}
    return rows[0]


def set_phase(class_name: str, phase: str):
    supabase.table(T_STATUS).upsert(
        {"class_name": class_name, "phase": phase}, on_conflict="class_name"
    ).execute()


def add_student(class_name: str, name: str):
    supabase.table(T_STUDENTS).upsert(
        {"class_name": class_name, "name": name}, on_conflict="class_name,name"
    ).execute()


def active_classes():
    rows = supabase.table(T_STATUS).select("*").execute().data
    return [r["class_name"] for r in rows if r.get("phase") not in ("대기", "종료")]


def save_response(class_name: str, name: str, stage: str, payload: dict):
    supabase.table(T_RESPONSES).upsert(
        {"class_name": class_name, "name": name, "stage": stage, "payload": payload},
        on_conflict="class_name,name,stage",
    ).execute()


def my_response(class_name: str, name: str, stage: str):
    rows = (
        supabase.table(T_RESPONSES).select("*")
        .eq("class_name", class_name).eq("name", name).eq("stage", stage)
        .execute().data
    )
    return rows[0] if rows else None


def all_responses(class_name: str, stage: str) -> pd.DataFrame:
    rows = (
        supabase.table(T_RESPONSES).select("*")
        .eq("class_name", class_name).eq("stage", stage)
        .execute().data
    )
    return pd.DataFrame(rows)


def fv(pv_value, annual_rate, years, m=1):
    return pv_value * (1 + annual_rate / m) ** (years * m)


def pv(future_value, annual_rate, years, m=1):
    return future_value / (1 + annual_rate / m) ** (years * m)


def annuity_pv(payment, nominal_annual_rate, months, due=False):
    r = nominal_annual_rate / 12
    value = payment * months if r == 0 else payment * (1 - (1 + r) ** (-months)) / r
    return value * (1 + r) if due else value


def cashflow_pv(cashflows, annual_rate):
    return sum(amount / ((1 + annual_rate) ** year) for year, amount in cashflows)


def geometric_mean(returns):
    gross = 1.0
    for r in returns:
        gross *= (1 + r)
    return gross ** (1 / len(returns)) - 1


def final_wealth(start, returns):
    value = start
    for r in returns:
        value *= (1 + r)
    return value


def render_header(class_name, role):
    c1, c2 = st.columns([8, 2])
    with c1:
        st.title("⏳ Money Time Machine")
        st.caption(f"은퇴와 상속설계 · 3주차 · {class_name} · {role}")
    with c2:
        if st.button("로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()


# 로그인
if "role" not in st.session_state:
    st.title("⏳ Money Time Machine")
    st.caption("3주차 · 시간과 수익률이 돈의 값을 어떻게 바꾸는지 직접 실험합니다.")
    role = st.radio("접속 유형", ["학생", "교수"], horizontal=True)

    if role == "학생":
        name = st.text_input("이름")
        if st.button("입장하기", type="primary"):
            if not name.strip():
                st.error("이름을 입력해주세요.")
                st.stop()
            active = active_classes()
            if len(active) == 1:
                cn = active[0]
                add_student(cn, name.strip())
                st.session_state.update(role="student", name=name.strip(), class_name=cn)
                st.rerun()
            elif len(active) == 0:
                st.error("현재 열려 있는 강의실이 없습니다.")
            else:
                st.session_state["pending_name"] = name.strip()
                st.session_state["choose_class"] = True
                st.rerun()

        if st.session_state.get("choose_class"):
            cn = st.selectbox("열려 있는 분반", active_classes())
            if st.button("이 분반으로 입장"):
                nm = st.session_state.get("pending_name", "").strip()
                add_student(cn, nm)
                st.session_state.update(role="student", name=nm, class_name=cn)
                st.session_state.pop("choose_class", None)
                st.session_state.pop("pending_name", None)
                st.rerun()
    else:
        cn = st.selectbox("분반", CLASSES)
        pw = st.text_input("교수 비밀번호", type="password")
        if st.button("교수 통제소 입장", type="primary"):
            if PROF_PASSWORD and pw == PROF_PASSWORD:
                st.session_state.update(role="professor", class_name=cn)
                st.rerun()
            else:
                st.error("비밀번호가 틀렸거나 Secrets에 PROF_PASSWORD가 설정되지 않았습니다.")
    st.stop()


my_class = st.session_state.class_name
role = st.session_state.role
phase = get_status(my_class).get("phase", "대기")
render_header(my_class, "학생" if role == "student" else "교수")
st.write("---")


# 학생 화면
if role == "student":
    me = st.session_state.name
    if st.button("🔄 화면 새로고침", type="primary", use_container_width=True):
        st.rerun()
    st.caption(f"현재 단계: {phase}")

    if phase in ("대기", "학생입장"):
        st.info("접속되었습니다. 교수님이 다음 실험을 열 때까지 기다려주세요.")
        st.stop()

    if phase == "TVM 타임머신":
        st.subheader("1. TVM 타임머신")
        st.write("같은 명목 연이율이라도 **시간과 복리주기**가 바뀌면 미래가치가 달라집니다.")
        c1, c2, c3 = st.columns(3)
        principal = c1.slider("현재금액(만원)", 100, 5000, 1000, step=100)
        rate_pct = c2.slider("명목 연이율(%)", 1.0, 12.0, 6.0, step=0.5)
        years = c3.slider("기간(년)", 1, 30, 10)
        rate = rate_pct / 100

        comp = {"연복리": 1, "반기복리": 2, "분기복리": 4, "월복리": 12}
        rows = [{"복리주기": k, "미래가치(만원)": fv(principal, rate, years, m)} for k, m in comp.items()]
        st.bar_chart(pd.DataFrame(rows).set_index("복리주기"))

        annual_fv = fv(principal, rate, years, 1)
        monthly_fv = fv(principal, rate, years, 12)
        st.metric("월복리 - 연복리 차이", f"{monthly_fv - annual_fv:,.1f}만원")

        st.write("---")
        st.markdown("#### 같은 금액을 현재 ↔ 미래로 왕복해보기")
        target = st.number_input("미래 목표금액(만원)", min_value=100.0, value=2000.0, step=100.0)
        needed_now = pv(target, rate, years, 1)
        c4, c5 = st.columns(2)
        c4.metric("그 목표의 현재가치", f"{needed_now:,.1f}만원")
        c5.metric("다시 미래로 보내면", f"{fv(needed_now, rate, years, 1):,.1f}만원")

        if st.button("내 TVM 실험 저장", type="primary"):
            save_response(my_class, me, "tvm", {
                "principal": principal, "rate_pct": rate_pct, "years": years,
                "annual_fv": round(annual_fv, 4), "monthly_fv": round(monthly_fv, 4),
                "target": target, "needed_now": round(needed_now, 4)
            })
            st.success("저장했습니다.")

    elif phase == "현금흐름 실험실":
        st.subheader("2. 현금흐름 실험실")
        st.write("같은 월 지급액이라도 **기간 초인지 기간 말인지**에 따라 현재가치가 달라집니다.")
        payment, months, nominal = 100.0, 36, 0.06
        ordinary = annuity_pv(payment, nominal, months, due=False)
        due = annuity_pv(payment, nominal, months, due=True)

        guess = st.radio(
            "월 100만원씩 36개월, 명목 연 6%(월복리)라면 어느 쪽의 현재가치가 더 클까요?",
            ["매월 말 지급", "매월 초 지급"], index=None
        )
        if guess:
            c1, c2 = st.columns(2)
            c1.metric("매월 말 지급의 현재가치", f"{ordinary:,.2f}만원")
            c2.metric("매월 초 지급의 현재가치", f"{due:,.2f}만원")
            st.success(f"한 기간 먼저 받는 '매월 초 지급'이 {due - ordinary:,.2f}만원 더 큽니다.")

        st.write("---")
        st.markdown("#### 규칙적이지 않은 현금흐름")
        st.write("1년 후 100만원, 2년 후 200만원, 3년 후 150만원을 받는다면?")
        ir_pv = cashflow_pv([(1, 100), (2, 200), (3, 150)], 0.05)
        st.metric("연 5% 할인 시 현재가치", f"{ir_pv:,.2f}만원")
        st.caption("금액이 매번 다르므로 일정한 PMT가 아니라 개별 cash flow를 각각 할인해 합산합니다.")

        if st.button("내 현금흐름 실험 저장", type="primary"):
            save_response(my_class, me, "cashflow", {
                "guess": guess, "ordinary_pv": round(ordinary, 4),
                "due_pv": round(due, 4), "irregular_pv": round(ir_pv, 4)
            })
            st.success("저장했습니다.")

    elif phase == "수익률 탐정":
        st.subheader("3. 수익률 탐정")
        st.write("연도별 수익률을 바꾸면서 **산술평균, 기하평균, 실제 최종자산**이 어떻게 달라지는지 확인하세요.")
        st.caption("기본값 +100%, -50%, 0%는 산술평균은 양수지만 3년 뒤 자산은 원점으로 돌아오는 예입니다.")
        c1, c2, c3 = st.columns(3)
        r1 = c1.slider("1년차 수익률(%)", -90, 120, 100)
        r2 = c2.slider("2년차 수익률(%)", -90, 120, -50)
        r3 = c3.slider("3년차 수익률(%)", -90, 120, 0)
        returns = [r1/100, r2/100, r3/100]

        arithmetic = sum(returns) / 3
        geometric = geometric_mean(returns)
        end = final_wealth(100, returns)
        cols = st.columns(3)
        cols[0].metric("산술평균", f"{arithmetic*100:.2f}%")
        cols[1].metric("기하평균", f"{geometric*100:.2f}%")
        cols[2].metric("100에서 시작한 최종자산", f"{end:.2f}")

        wealth = [100]
        value = 100
        for r in returns:
            value *= (1+r)
            wealth.append(value)
        st.line_chart(pd.DataFrame({"자산": wealth}, index=["시작","1년","2년","3년"]))

        if st.button("내 수익률 실험 저장", type="primary"):
            save_response(my_class, me, "returns", {
                "returns_pct": [r1,r2,r3], "arithmetic_pct": round(arithmetic*100,4),
                "geometric_pct": round(geometric*100,4), "final_wealth": round(end,4)
            })
            st.success("저장했습니다.")

    elif phase == "기대수익률 실험":
        st.subheader("4. 기대수익률은 같은데 위험은 다르다")
        st.write("경제상황의 확률은 호황 25% · 보통 50% · 불황 25%라고 가정합니다.")
        states = pd.DataFrame({
            "경제상황": ["호황","보통","불황"], "확률": [0.25,0.50,0.25],
            "자산 A 수익률": [0.50,0.05,-0.40], "자산 B 수익률": [0.20,0.05,-0.10]
        })
        st.dataframe(states, use_container_width=True, hide_index=True)
        exp_a = (states["확률"]*states["자산 A 수익률"]).sum()
        exp_b = (states["확률"]*states["자산 B 수익률"]).sum()
        pick = st.radio("기대수익률을 보기 전에, 어느 자산이 더 위험해 보입니까?", ["자산 A","자산 B"], index=None)
        if pick:
            c1,c2 = st.columns(2)
            c1.metric("자산 A 기대수익률", f"{exp_a*100:.1f}%")
            c2.metric("자산 B 기대수익률", f"{exp_b*100:.1f}%")
            st.info("두 자산의 기대수익률은 같지만 A의 가능한 수익률 범위가 더 넓습니다. 기대수익률 하나만으로 위험을 판단할 수 없습니다.")

        if st.button("내 기대수익률 실험 저장", type="primary"):
            save_response(my_class, me, "expected", {"pick": pick, "exp_a_pct": exp_a*100, "exp_b_pct": exp_b*100})
            st.success("저장했습니다.")

    elif phase == "요구수익률 조립":
        st.subheader("5. 요구수익률 조립기")
        st.write("수업의 단순화된 build-up 방식으로 요구수익률을 조립해봅니다.")
        c1,c2,c3 = st.columns(3)
        real_rf = c1.slider("실질무위험수익률(%)", 0.0, 6.0, 2.0, step=0.5)
        inflation = c2.slider("기대물가상승률(%)", 0.0, 8.0, 3.0, step=0.5)
        risk_premium = c3.slider("위험보상률(%)", 0.0, 12.0, 4.0, step=0.5)
        approx_required = real_rf + inflation + risk_premium
        exact_nominal_rf = ((1+real_rf/100)*(1+inflation/100)-1)*100
        st.metric("단순화한 요구수익률 근사값", f"{approx_required:.2f}%")
        with st.expander("왜 '근사값'이라고 하나요?"):
            st.write("정확한 Fisher 관계는 (1+명목)=(1+실질)×(1+기대인플레이션)입니다. 금리가 낮을 때 단순 합과 차이가 작아 수업에서는 합으로 근사할 수 있습니다.")
            st.write(f"현재 입력값의 Fisher식 명목무위험수익률: **{exact_nominal_rf:.3f}%**")

        if st.button("내 요구수익률 조립 저장", type="primary"):
            save_response(my_class, me, "required", {
                "real_rf": real_rf, "expected_inflation": inflation,
                "risk_premium": risk_premium, "approx_required": approx_required,
                "fisher_nominal_rf": exact_nominal_rf
            })
            st.success("저장했습니다.")

    elif phase == "결과":
        st.subheader("6. 나의 Money Time Machine 기록")
        stages = [("TVM","tvm"),("현금흐름","cashflow"),("수익률","returns"),("기대수익률","expected"),("요구수익률","required")]
        cols = st.columns(5)
        for col,(label,key) in zip(cols,stages):
            col.metric(label, "완료" if my_response(my_class, me, key) else "미완료")
        st.info("이번 주 핵심: **돈의 가치는 시간과 할인율에 따라 달라지고, 여러 기간의 투자성과는 단순 평균만으로 설명되지 않으며, 기대수익률과 요구수익률은 서로 다른 질문에 답합니다.**")

    elif phase == "종료":
        st.success("3주차 Money Time Machine 활동이 종료되었습니다.")


# 교수 화면
else:
    st.subheader("교수 통제소")
    c1,c2,c3 = st.columns([4,2,2])
    new_phase = c1.selectbox("진행 단계", PHASES, index=PHASES.index(phase))
    if c2.button("✅ 단계 적용", type="primary", use_container_width=True):
        set_phase(my_class, new_phase)
        st.rerun()
    if c3.button("🔄 새로고침", use_container_width=True):
        st.rerun()

    students = supabase.table(T_STUDENTS).select("*").eq("class_name", my_class).execute().data
    st.metric("접속 학생", f"{len(students)}명")
    st.write("---")

    stage_map = {
        "TVM 타임머신":"tvm", "현금흐름 실험실":"cashflow", "수익률 탐정":"returns",
        "기대수익률 실험":"expected", "요구수익률 조립":"required"
    }

    if phase in stage_map:
        stage = stage_map[phase]
        df = all_responses(my_class, stage)
        st.subheader(f"실시간 결과 · {phase}")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            st.metric("제출 인원", f"{len(df)}명")
            if stage == "tvm":
                rows=[]
                for _,r in df.iterrows():
                    p=r["payload"] or {}
                    rows.append({"이름":r["name"],"이율(%)":p.get("rate_pct"),"기간(년)":p.get("years"),"연복리FV":p.get("annual_fv"),"월복리FV":p.get("monthly_fv")})
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            elif stage == "cashflow":
                s=pd.Series([(r["payload"] or {}).get("guess") for _,r in df.iterrows()]).dropna()
                if not s.empty: st.bar_chart(s.value_counts())
            elif stage == "returns":
                rows=[]
                for _,r in df.iterrows():
                    p=r["payload"] or {}
                    rows.append({"이름":r["name"],"수익률":str(p.get("returns_pct")),"산술평균(%)":p.get("arithmetic_pct"),"기하평균(%)":p.get("geometric_pct"),"최종자산":p.get("final_wealth")})
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            elif stage == "expected":
                s=pd.Series([(r["payload"] or {}).get("pick") for _,r in df.iterrows()]).dropna()
                if not s.empty: st.bar_chart(s.value_counts())
            elif stage == "required":
                rows=[]
                for _,r in df.iterrows():
                    p=r["payload"] or {}
                    rows.append({"이름":r["name"],"실질무위험(%)":p.get("real_rf"),"기대물가(%)":p.get("expected_inflation"),"위험보상(%)":p.get("risk_premium"),"요구수익률 근사(%)":p.get("approx_required")})
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    elif phase == "결과":
        st.subheader("3주차 활동 완료 현황")
        stages=[("TVM","tvm"),("현금흐름","cashflow"),("수익률","returns"),("기대수익률","expected"),("요구수익률","required")]
        st.dataframe(pd.DataFrame([{"활동":label,"제출 인원":len(all_responses(my_class,key))} for label,key in stages]), use_container_width=True, hide_index=True)
        st.info("마무리 질문: '산술평균이 높아도 실제 자산 성장이 낮을 수 있는 이유는?' '기대수익률이 같아도 투자위험이 다른 이유는?' '요구수익률의 구성요소는 각각 무엇에 대한 보상인가?'")

    with st.expander("⚠️ 데이터 관리"):
        if st.button("이 분반 3주차 응답 삭제"):
            supabase.table(T_RESPONSES).delete().eq("class_name", my_class).execute()
            st.rerun()
        if st.button("이 분반 3주차 전체 초기화"):
            supabase.table(T_RESPONSES).delete().eq("class_name", my_class).execute()
            supabase.table(T_STUDENTS).delete().eq("class_name", my_class).execute()
            set_phase(my_class, "대기")
            st.rerun()
