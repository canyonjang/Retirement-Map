import pandas as pd
import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title="Retirement Planner Clinic · 4주차", page_icon="🩺", layout="wide")

CLASSES = ["인하대", "숙대1", "숙대2"]
PHASES = [
    "대기",
    "학생입장",
    "정보수집 트리아지",
    "부족자금 진단",
    "플랜 구조대",
    "자산배분 처방",
    "공적연금 데스크",
    "결과",
    "종료",
]

T_STATUS = "retire_w4_status"
T_STUDENTS = "retire_w4_students"
T_RESPONSES = "retire_w4_responses"


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
        {"class_name": class_name, "phase": phase},
        on_conflict="class_name",
    ).execute()


def add_student(class_name: str, name: str):
    supabase.table(T_STUDENTS).upsert(
        {"class_name": class_name, "name": name},
        on_conflict="class_name,name",
    ).execute()


def active_classes():
    rows = supabase.table(T_STATUS).select("*").execute().data
    return [r["class_name"] for r in rows if r.get("phase") not in ("대기", "종료")]


def save_response(class_name: str, name: str, stage: str, payload: dict):
    supabase.table(T_RESPONSES).upsert(
        {
            "class_name": class_name,
            "name": name,
            "stage": stage,
            "payload": payload,
        },
        on_conflict="class_name,name,stage",
    ).execute()


def my_response(class_name: str, name: str, stage: str):
    rows = (
        supabase.table(T_RESPONSES).select("*")
        .eq("class_name", class_name)
        .eq("name", name)
        .eq("stage", stage)
        .execute().data
    )
    return rows[0] if rows else None


def all_responses(class_name: str, stage: str) -> pd.DataFrame:
    rows = (
        supabase.table(T_RESPONSES).select("*")
        .eq("class_name", class_name)
        .eq("stage", stage)
        .execute().data
    )
    return pd.DataFrame(rows)


def annuity_pv(payment_annual, annual_rate, years):
    if annual_rate == 0:
        return payment_annual * years
    return payment_annual * (1 - (1 + annual_rate) ** (-years)) / annual_rate


def fv_lump(pv_value, annual_rate, years):
    return pv_value * (1 + annual_rate) ** years


def pmt_for_fv(future_needed, annual_rate, years):
    if future_needed <= 0:
        return 0.0
    r = annual_rate / 12
    n = years * 12
    if r == 0:
        return future_needed / n
    return future_needed * r / ((1 + r) ** n - 1)


def case_values(retire_years=20, retirement_years=25, target_month=3_500_000,
                pension_month=1_500_000, current_assets=100_000_000,
                pre_return=0.04, post_return=0.03):
    annual_gap = max(0, (target_month - pension_month) * 12)
    total_lump = annuity_pv(annual_gap, post_return, retirement_years)
    asset_fv = fv_lump(current_assets, pre_return, retire_years)
    shortage = max(0, total_lump - asset_fv)
    monthly_saving = pmt_for_fv(shortage, pre_return, retire_years)
    return {
        "annual_gap": annual_gap,
        "total_lump": total_lump,
        "asset_fv": asset_fv,
        "shortage": shortage,
        "monthly_saving": monthly_saving,
    }


BASE = case_values()


def render_header(class_name, role):
    c1, c2 = st.columns([8, 2])
    with c1:
        st.title("🩺 Retirement Planner Clinic")
        st.caption(f"은퇴와 상속설계 · 4주차 · {class_name} · {role}")
    with c2:
        if st.button("로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()


# ==========================================================
# 로그인
# ==========================================================
if "role" not in st.session_state:
    st.title("🩺 Retirement Planner Clinic")
    st.caption("4주차 · 한 고객의 은퇴설계를 진단하고, 부족한 계획을 고쳐봅니다.")
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


# ==========================================================
# 학생
# ==========================================================
if role == "student":
    me = st.session_state.name
    if st.button("🔄 화면 새로고침", type="primary", use_container_width=True):
        st.rerun()

    st.caption(f"현재 단계: {phase}")

    if phase in ("대기", "학생입장"):
        st.info("접속되었습니다. 교수님이 다음 진료실을 열 때까지 기다려주세요.")
        st.stop()

    # ------------------------------------------------------
    # 1. 정보수집
    # ------------------------------------------------------
    if phase == "정보수집 트리아지":
        st.subheader("1. 정보수집 트리아지 · 빠진 정보를 찾아라")
        st.write(
            "고객 차트에는 **현재 나이 45세, 은퇴 희망 65세, 현재 은퇴자산 1억원, "
            "목표 은퇴생활비 월 350만원**만 적혀 있습니다."
        )
        st.write("실행 가능한 은퇴설계를 위해 추가로 확인해야 할 항목을 모두 고르세요.")

        correct_set = {
            "예상 은퇴기간(또는 기대수명)",
            "예상 물가상승률",
            "은퇴자산의 세후투자수익률",
            "예상 공적연금액",
        }
        options = [
            "예상 은퇴기간(또는 기대수명)",
            "예상 물가상승률",
            "은퇴자산의 세후투자수익률",
            "예상 공적연금액",
            "최근 한 달 코스피 수익률",
            "친구가 추천한 펀드의 수익률",
        ]

        old = my_response(my_class, me, "triage")
        if old:
            p = old["payload"]
            st.success(f"제출 완료 · {p['score']} / 4")
            st.write("내 선택:", ", ".join(p["selected"]))
            st.info("은퇴기간, 물가, 세후투자수익률, 공적연금 예상액은 은퇴설계의 핵심 가정·정보입니다.")
        else:
            with st.form("triage_form"):
                selected = st.multiselect("추가로 확인할 항목", options)
                submitted = st.form_submit_button("🔒 트리아지 제출", type="primary")
                if submitted:
                    selected_set = set(selected)
                    score = len(selected_set & correct_set) - len(selected_set - correct_set)
                    score = max(0, score)
                    save_response(my_class, me, "triage", {
                        "selected": selected,
                        "score": score,
                        "perfect": selected_set == correct_set,
                    })
                    st.rerun()

    # ------------------------------------------------------
    # 2. 부족자금 진단
    # ------------------------------------------------------
    elif phase == "부족자금 진단":
        st.subheader("2. 부족자금 진단 · 3주차 계산을 실제 설계에 적용")
        st.write(
            "고객: 현재 45세, 65세 은퇴, 은퇴기간 25년, 목표 생활비 월 350만원, "
            "예상 공적연금 월 150만원, 현재 은퇴자산 1억원."
        )
        st.write("가정: 은퇴 전 세후수익률 연 4%, 은퇴 후 세후수익률 연 3%.")
        st.caption("계산을 단순화하기 위해 물가 조정은 이미 목표금액에 반영된 것으로 둡니다.")

        old = my_response(my_class, me, "gap_diagnosis")
        exact = BASE["monthly_saving"] / 10_000  # 만원
        if old:
            p = old["payload"]
            st.success(
                f"내 추정 {p['guess']:.0f}만원/월 · 계산값 {p['exact']:.1f}만원/월 · "
                f"오차 {p['error_abs']:.1f}만원"
            )
            st.metric("총은퇴일시금", f"{BASE['total_lump']/100_000_000:.2f}억원")
            st.metric("현재 자산의 은퇴시점 미래가치", f"{BASE['asset_fv']/100_000_000:.2f}억원")
            st.metric("추가로 필요한 은퇴일시금", f"{BASE['shortage']/100_000_000:.2f}억원")
        else:
            guess = st.slider("필요한 추가 월저축액을 추정하세요(만원)", 0, 100, 40, step=1)
            if st.button("🔒 진단 제출", type="primary"):
                save_response(my_class, me, "gap_diagnosis", {
                    "guess": guess,
                    "exact": round(exact, 4),
                    "error_abs": round(abs(guess - exact), 4),
                })
                st.rerun()

    # ------------------------------------------------------
    # 3. 플랜 구조대
    # ------------------------------------------------------
    elif phase == "플랜 구조대":
        st.subheader("3. 플랜 구조대 · 월저축 여력 45만원 안으로 구하라")
        st.write(
            f"현재 설계의 필요 월저축액은 약 **{BASE['monthly_saving']/10_000:.1f}만원**인데, "
            "고객이 실제로 저축할 수 있는 금액은 **월 45만원**입니다."
        )
        st.write("다음 중 하나를 선택해 계획을 수정하세요.")

        choices = {
            "A": ("은퇴시기를 2년 늦춘다", case_values(retire_years=22, retirement_years=23)),
            "B": ("목표 은퇴생활비를 월 350만원 → 330만원으로 조정한다", case_values(target_month=3_300_000)),
            "C": ("다른 조건은 그대로 두고 예상수익률만 연 4% → 5%로 높여 잡는다", case_values(pre_return=0.05)),
        }

        old = my_response(my_class, me, "plan_rescue")
        if old:
            p = old["payload"]
            if p["feasible"] and p["prudent"]:
                st.success("구조 성공: 저축여력 안에 들어왔고, 단순히 낙관적 수익률 가정에 기대지 않았습니다.")
            elif p["feasible"]:
                st.warning("계산상 구조는 성공하지만, 예상수익률을 높여 잡는 것만으로 문제를 해결하는 것은 보수적 은퇴설계와 맞지 않습니다.")
            else:
                st.error("아직 월저축 여력 45만원을 초과합니다.")
            st.write(f"내 선택: **{p['choice_text']}**")
            st.metric("수정 후 필요 월저축액", f"{p['monthly_saving_man']:.1f}만원")
        else:
            with st.form("rescue_form"):
                choice = st.radio(
                    "수정안",
                    [f"{k}. {v[0]}" for k, v in choices.items()],
                    index=None,
                )
                submitted = st.form_submit_button("🚑 이 수정안으로 구조", type="primary")
                if submitted:
                    if choice is None:
                        st.warning("수정안을 선택해주세요.")
                    else:
                        key = choice[0]
                        text, result = choices[key]
                        monthly_man = result["monthly_saving"] / 10_000
                        feasible = monthly_man <= 45
                        prudent = key != "C"
                        save_response(my_class, me, "plan_rescue", {
                            "choice": key,
                            "choice_text": text,
                            "monthly_saving_man": round(monthly_man, 4),
                            "feasible": feasible,
                            "prudent": prudent,
                        })
                        st.rerun()

    # ------------------------------------------------------
    # 4. 자산배분 처방
    # ------------------------------------------------------
    elif phase == "자산배분 처방":
        st.subheader("4. 자산배분 처방 · 조건을 모두 만족시켜라")
        st.write(
            "52세, 은퇴까지 13년 남은 중간 수준 위험성향 고객입니다. "
            "아래 조건을 모두 만족하는 포트폴리오를 만드세요."
        )
        st.info(
            "조건: 주식 ≤ 50% · 채권 ≥ 30% · 현금 ≥ 10% · 대체자산 ≤ 20% · "
            "가정 기대수익률 ≥ 4.0% · 합계 100%"
        )
        st.caption("수업용 단순화 가정 기대수익률: 주식 7%, 채권 3%, 현금 2%, 대체자산 5%")

        old = my_response(my_class, me, "allocation")
        if old:
            p = old["payload"]
            st.success("처방 승인 완료")
            st.write(
                f"주식 {p['stock']}% · 채권 {p['bond']}% · 현금 {p['cash']}% · "
                f"대체자산 {p['alt']}%"
            )
            st.metric("가정 기대수익률", f"{p['expected_return']:.2f}%")
        else:
            c1, c2, c3, c4 = st.columns(4)
            stock = c1.slider("주식(%)", 0, 100, 40, step=5)
            bond = c2.slider("채권(%)", 0, 100, 35, step=5)
            cash = c3.slider("현금(%)", 0, 100, 15, step=5)
            alt = c4.slider("대체자산(%)", 0, 100, 10, step=5)

            total = stock + bond + cash + alt
            er = stock*0.07 + bond*0.03 + cash*0.02 + alt*0.05
            valid = (
                total == 100
                and stock <= 50
                and bond >= 30
                and cash >= 10
                and alt <= 20
                and er >= 4.0
            )

            st.metric("합계", f"{total}%")
            st.metric("가정 기대수익률", f"{er:.2f}%")

            if valid:
                st.success("✅ 모든 조건 충족 — 처방 가능")
            else:
                st.warning("아직 모든 조건을 만족하지 못했습니다.")

            if st.button("💊 이 포트폴리오 처방", type="primary", disabled=not valid):
                save_response(my_class, me, "allocation", {
                    "stock": stock,
                    "bond": bond,
                    "cash": cash,
                    "alt": alt,
                    "expected_return": round(er, 4),
                })
                st.rerun()

    # ------------------------------------------------------
    # 5. 공적연금 데스크
    # ------------------------------------------------------
    elif phase == "공적연금 데스크":
        st.subheader("5. 2026 공적연금 데스크 · 3명의 고객을 처리하라")
        st.caption("2026년 현재 제도를 기준으로 합니다. 제출 후 정답을 공개합니다.")

        old = my_response(my_class, me, "pension_desk")
        if old:
            p = old["payload"]
            st.success(f"제출 완료 · {p['score']} / 3")

            st.markdown("#### 고객 1 · 사업장가입자")
            st.write("기준소득월액 300만원, 2026년 보험료율 9.5%")
            st.write(f"내 선택: {p['q1']} · 정답: **14만 2,500원**")

            st.markdown("#### 고객 2 · 크레딧")
            st.write(f"내 선택: {p['q2']} · 정답: **첫째아 12개월 / 군복무 최대 12개월**")

            st.markdown("#### 고객 3 · 조기·연기")
            st.write(f"내 선택: {p['q3']} · 정답: **5년 조기 70만원 / 5년 연기 136만원**")
        else:
            with st.form("pension_desk_form"):
                st.markdown("### 고객 1")
                q1 = st.radio(
                    "기준소득월액 300만원인 사업장가입자의 2026년 근로자 본인 부담 월보험료는?",
                    ["13만 5,000원", "14만 2,500원", "28만 5,000원", "30만원"],
                    index=None,
                    key="w4q1",
                )

                st.write("---")
                st.markdown("### 고객 2")
                q2 = st.radio(
                    "2026년부터 확대된 국민연금 크레딧의 조합으로 맞는 것은?",
                    [
                        "첫째아 없음 / 군복무 6개월",
                        "첫째아 12개월 / 군복무 최대 12개월",
                        "첫째아 6개월 / 군복무 최대 18개월",
                        "둘 다 24개월",
                    ],
                    index=None,
                    key="w4q2",
                )

                st.write("---")
                st.markdown("### 고객 3")
                q3 = st.radio(
                    "정상 노령연금이 월 100만원이라고 단순 가정할 때, 5년 조기수령과 5년 연기의 월액 조합은?",
                    [
                        "70만원 / 136만원",
                        "70만원 / 130만원",
                        "75만원 / 136만원",
                        "80만원 / 130만원",
                    ],
                    index=None,
                    key="w4q3",
                )

                submitted = st.form_submit_button("🔒 세 고객 처리 완료", type="primary")
                if submitted:
                    if any(x is None for x in [q1, q2, q3]):
                        st.warning("세 문제에 모두 답해주세요.")
                    else:
                        c1 = q1 == "14만 2,500원"
                        c2 = q2 == "첫째아 12개월 / 군복무 최대 12개월"
                        c3 = q3 == "70만원 / 136만원"
                        save_response(my_class, me, "pension_desk", {
                            "q1": q1, "q2": q2, "q3": q3,
                            "q1_correct": c1, "q2_correct": c2, "q3_correct": c3,
                            "score": int(c1) + int(c2) + int(c3),
                        })
                        st.rerun()

    elif phase == "결과":
        st.subheader("6. 나의 Retirement Planner Clinic 기록")
        stages = [
            ("정보수집", "triage"),
            ("부족자금", "gap_diagnosis"),
            ("플랜구조", "plan_rescue"),
            ("자산배분", "allocation"),
            ("공적연금", "pension_desk"),
        ]
        cols = st.columns(5)
        for col, (label, key) in zip(cols, stages):
            col.metric(label, "완료" if my_response(my_class, me, key) else "미완료")

    elif phase == "종료":
        st.success("4주차 Retirement Planner Clinic이 종료되었습니다.")


# ==========================================================
# 교수
# ==========================================================
else:
    st.subheader("교수 통제소")

    c1, c2, c3 = st.columns([4, 2, 2])
    new_phase = c1.selectbox("진행 단계", PHASES, index=PHASES.index(phase))
    if c2.button("✅ 단계 적용", type="primary", use_container_width=True):
        set_phase(my_class, new_phase)
        st.rerun()
    if c3.button("🔄 새로고침", use_container_width=True):
        st.rerun()

    students = supabase.table(T_STUDENTS).select("*").eq("class_name", my_class).execute().data
    st.metric("접속 학생", f"{len(students)}명")
    st.write("---")

    if phase == "정보수집 트리아지":
        df = all_responses(my_class, "triage")
        st.subheader("정보수집 트리아지 결과")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            scores = pd.Series([(p or {}).get("score", 0) for p in df["payload"]])
            st.metric("평균 점수", f"{scores.mean():.2f} / 4")
            st.bar_chart(scores.value_counts().sort_index())

    elif phase == "부족자금 진단":
        df = all_responses(my_class, "gap_diagnosis")
        st.subheader("부족자금 진단 결과")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for _, r in df.iterrows():
                p = r["payload"] or {}
                rows.append({
                    "이름": r["name"],
                    "추정 월저축(만원)": p.get("guess"),
                    "계산값(만원)": p.get("exact"),
                    "오차(만원)": p.get("error_abs"),
                })
            rank = pd.DataFrame(rows).sort_values(["오차(만원)", "이름"])
            st.dataframe(rank, use_container_width=True, hide_index=True)

    elif phase == "플랜 구조대":
        df = all_responses(my_class, "plan_rescue")
        st.subheader("플랜 구조대 결과")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for _, r in df.iterrows():
                p = r["payload"] or {}
                rows.append({
                    "이름": r["name"],
                    "선택": p.get("choice"),
                    "수정안": p.get("choice_text"),
                    "필요 월저축(만원)": p.get("monthly_saving_man"),
                    "저축여력 내": "O" if p.get("feasible") else "X",
                    "보수적 가정": "O" if p.get("prudent") else "X",
                })
            result = pd.DataFrame(rows)
            st.dataframe(result, use_container_width=True, hide_index=True)
            st.bar_chart(result["선택"].value_counts())

    elif phase == "자산배분 처방":
        df = all_responses(my_class, "allocation")
        st.subheader("자산배분 처방 결과")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for _, r in df.iterrows():
                p = r["payload"] or {}
                rows.append({
                    "이름": r["name"],
                    "주식": p.get("stock"),
                    "채권": p.get("bond"),
                    "현금": p.get("cash"),
                    "대체": p.get("alt"),
                    "기대수익률": p.get("expected_return"),
                })
            result = pd.DataFrame(rows)
            st.dataframe(result, use_container_width=True, hide_index=True)
            avg = result[["주식", "채권", "현금", "대체"]].mean()
            st.bar_chart(avg)

    elif phase == "공적연금 데스크":
        df = all_responses(my_class, "pension_desk")
        st.subheader("공적연금 데스크 결과")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for _, r in df.iterrows():
                p = r["payload"] or {}
                rows.append({
                    "이름": r["name"],
                    "보험료": "O" if p.get("q1_correct") else "X",
                    "크레딧": "O" if p.get("q2_correct") else "X",
                    "조기·연기": "O" if p.get("q3_correct") else "X",
                    "총점": p.get("score", 0),
                })
            result = pd.DataFrame(rows).sort_values(["총점", "이름"], ascending=[False, True])
            st.dataframe(result, use_container_width=True, hide_index=True)
            st.bar_chart(result["총점"].value_counts().sort_index())

    elif phase == "결과":
        stages = [
            ("정보수집", "triage"),
            ("부족자금", "gap_diagnosis"),
            ("플랜구조", "plan_rescue"),
            ("자산배분", "allocation"),
            ("공적연금", "pension_desk"),
        ]
        rows = [{"활동": label, "제출 인원": len(all_responses(my_class, key))} for label, key in stages]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with st.expander("⚠️ 데이터 관리"):
        if st.button("이 분반 4주차 응답 삭제"):
            supabase.table(T_RESPONSES).delete().eq("class_name", my_class).execute()
            st.rerun()

        if st.button("이 분반 4주차 전체 초기화"):
            supabase.table(T_RESPONSES).delete().eq("class_name", my_class).execute()
            supabase.table(T_STUDENTS).delete().eq("class_name", my_class).execute()
            set_phase(my_class, "대기")
            st.rerun()
