import itertools
import hashlib
import pandas as pd
import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title="Money Time Machine · 3주차", page_icon="⏳", layout="wide")

CLASSES = ["인하대", "숙대1", "숙대2"]
PHASES = [
    "대기",
    "학생입장",
    "TVM 타임머신",
    "현금흐름 게임",
    "수익률 탐정",
    "기대수익률 대결",
    "요구수익률 금고",
    "결과",
    "종료",
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


def fv(pv_value, annual_rate, years, m=1):
    return pv_value * (1 + annual_rate / m) ** (years * m)


def pv(future_value, annual_rate, years, m=1):
    return future_value / (1 + annual_rate / m) ** (years * m)


def annuity_pv(payment, nominal_annual_rate, months, due=False):
    r = nominal_annual_rate / 12
    if r == 0:
        value = payment * months
    else:
        value = payment * (1 - (1 + r) ** (-months)) / r
    if due:
        value *= (1 + r)
    return value


def cashflow_pv(schedule, annual_rate):
    return sum(amount / ((1 + annual_rate) ** year) for year, amount in schedule)


def geometric_mean(returns):
    gross = 1.0
    for r in returns:
        gross *= (1 + r)
    if gross < 0:
        return None
    return gross ** (1 / len(returns)) - 1


def final_wealth(start, returns):
    value = start
    for r in returns:
        value *= (1 + r)
    return value


def score_from_error(error_pct):
    return max(0.0, 100.0 - error_pct)


RETURN_SCENARIOS = [
    {
        "name": "A",
        "target_avg": 10,
        "min_r": -80,
        "max_r": 80,
        "step": 5,
        "fixed": {1: 20},
        "rule": "2년차 수익률은 +20%로 고정",
    },
    {
        "name": "B",
        "target_avg": 5,
        "min_r": -60,
        "max_r": 60,
        "step": 5,
        "negative_count": 1,
        "rule": "세 해 중 손실인 해는 정확히 1번",
    },
    {
        "name": "C",
        "target_avg": 15,
        "min_r": -50,
        "max_r": 70,
        "step": 5,
        "fixed": {0: -20},
        "rule": "1년차 수익률은 -20%로 고정",
    },
    {
        "name": "D",
        "target_avg": 0,
        "min_r": -50,
        "max_r": 50,
        "step": 5,
        "zero_count": 1,
        "rule": "세 해 중 수익률 0%인 해는 정확히 1번",
    },
    {
        "name": "E",
        "target_avg": 10,
        "min_r": -40,
        "max_r": 60,
        "step": 5,
        "fixed": {2: 0},
        "rule": "3년차 수익률은 0%로 고정",
    },
    {
        "name": "F",
        "target_avg": 5,
        "min_r": -70,
        "max_r": 50,
        "step": 5,
        "fixed": {0: 40},
        "rule": "1년차 수익률은 +40%로 고정",
    },
]


def get_student_scenario(class_name: str, name: str):
    token = f"{class_name}|{name}".encode("utf-8")
    idx = int(hashlib.sha256(token).hexdigest()[:8], 16) % len(RETURN_SCENARIOS)
    return RETURN_SCENARIOS[idx]


def scenario_valid(values, scenario):
    if abs(sum(values) / 3 - scenario["target_avg"]) > 1e-9:
        return False

    fixed = scenario.get("fixed", {})
    for idx, target in fixed.items():
        if values[idx] != target:
            return False

    if "negative_count" in scenario:
        if sum(v < 0 for v in values) != scenario["negative_count"]:
            return False

    if "zero_count" in scenario:
        if sum(v == 0 for v in values) != scenario["zero_count"]:
            return False

    return True


def scenario_optimum(scenario):
    values = list(range(scenario["min_r"], scenario["max_r"] + 1, scenario["step"]))
    best_value = None
    best_combo = None

    for combo in itertools.product(values, repeat=3):
        if not scenario_valid(combo, scenario):
            continue
        wealth = final_wealth(100, [v / 100 for v in combo])
        if best_value is None or wealth < best_value - 1e-12:
            best_value = wealth
            best_combo = combo

    return best_value, best_combo


def render_header(class_name, role):
    c1, c2 = st.columns([8, 2])
    with c1:
        st.title("⏳ Money Time Machine")
        st.caption(f"은퇴와 상속설계 · 3주차 · {class_name} · {role}")
    with c2:
        if st.button("로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()


# ==========================================================
# 로그인
# ==========================================================
if "role" not in st.session_state:
    st.title("⏳ Money Time Machine")
    st.caption("3주차 · 시간과 수익률을 '맞히고, 찾고, 비교하는' 실험 게임")
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
# 학생 화면
# ==========================================================
if role == "student":
    me = st.session_state.name

    if st.button("🔄 화면 새로고침", type="primary", use_container_width=True):
        st.rerun()

    st.caption(f"현재 단계: {phase}")

    if phase in ("대기", "학생입장"):
        st.info("접속되었습니다. 교수님이 다음 게임을 열 때까지 기다려주세요.")
        st.stop()

    # ------------------------------------------------------
    # TVM 타임머신
    # ------------------------------------------------------
    if phase == "TVM 타임머신":
        st.subheader("1. TVM 타임머신")

        # ===== Mission A =====
        st.markdown("### 🎯 미션 A · 월복리-연복리 격차 100만원에 최대한 가깝게 맞혀라")
        st.caption(
            "현재금액·명목 연이율·기간을 바꾸면서 두 미래가치의 차이를 탐색하세요. "
            "제출은 한 번이며, 100만원에 가까울수록 높은 점수입니다."
        )

        old_gap = my_response(my_class, me, "tvm_gap")
        if old_gap:
            p = old_gap["payload"]
            st.success(
                f"제출 완료 · 격차 {p['gap']:,.2f}만원 · 목표와의 차이 {p['error_abs']:,.2f}만원 "
                f"· 점수 {p['score']:.1f}"
            )
            st.write(
                f"내 조건: 현재금액 {p['principal']:,}만원 · 명목 연이율 {p['rate_pct']:.1f}% · "
                f"기간 {p['years']}년"
            )
        else:
            c1, c2, c3 = st.columns(3)
            principal = c1.slider("현재금액(만원)", 500, 3000, 1000, step=100)
            rate_pct = c2.slider("명목 연이율(%)", 2.0, 10.0, 6.0, step=0.5)
            years = c3.slider("기간(년)", 5, 30, 20)

            r = rate_pct / 100
            annual_fv = fv(principal, r, years, 1)
            monthly_fv = fv(principal, r, years, 12)
            gap = monthly_fv - annual_fv
            target_gap = 100.0
            error_abs = abs(gap - target_gap)
            error_pct = error_abs / target_gap * 100
            score = score_from_error(error_pct)

            st.metric("현재 월복리 - 연복리 격차", f"{gap:,.2f}만원")
            st.progress(min(gap / target_gap, 1.0))
            if gap < target_gap:
                st.info(f"목표까지 {target_gap-gap:,.2f}만원 부족합니다.")
            elif gap > target_gap:
                st.warning(f"목표를 {gap-target_gap:,.2f}만원 초과했습니다.")
            else:
                st.success("정확히 100만원입니다!")

            if st.button("🔒 이 조건으로 미션 A 제출", type="primary"):
                save_response(my_class, me, "tvm_gap", {
                    "principal": principal,
                    "rate_pct": rate_pct,
                    "years": years,
                    "annual_fv": round(annual_fv, 4),
                    "monthly_fv": round(monthly_fv, 4),
                    "gap": round(gap, 4),
                    "error_abs": round(error_abs, 4),
                    "score": round(score, 4),
                })
                st.rerun()

        st.write("---")

        # ===== Mission B =====
        st.markdown("### 🎯 미션 B · 현재가치 스나이퍼")
        future_target = 10000.0  # 만원 = 1억원
        rate_pct2 = 5.0
        years2 = 20
        exact_pv = pv(future_target, rate_pct2 / 100, years2, 1)

        st.info(
            f"**20년 후 1억원**이 필요합니다. 연복리 **5%**를 적용할 때, "
            "지금 얼마가 있으면 될지 먼저 추정해보세요."
        )

        old_pv = my_response(my_class, me, "pv_sniper")
        if old_pv:
            p = old_pv["payload"]
            st.success(
                f"내 추정 {p['guess']:,.0f}만원 · 정답 {p['exact_pv']:,.2f}만원 · "
                f"오차 {p['error_abs']:,.2f}만원 · 오차율 {p['error_pct']:.2f}%"
            )
            if p["error_pct"] <= 1:
                st.balloons()
                st.write("🎯 **Bull's-eye! 오차 1% 이내입니다.**")
        else:
            guess = st.slider("내 추정 현재가치(만원)", 1000, 8000, 4000, step=100)
            st.caption("제출 전에는 정확한 현재가치를 보여주지 않습니다.")

            if st.button("🔒 이 금액으로 미션 B 제출", type="primary"):
                error_pct2 = abs(guess - exact_pv) / exact_pv * 100
                error_abs2 = abs(guess - exact_pv)
                save_response(my_class, me, "pv_sniper", {
                    "future_target": future_target,
                    "rate_pct": rate_pct2,
                    "years": years2,
                    "guess": guess,
                    "exact_pv": round(exact_pv, 4),
                    "error_abs": round(error_abs2, 4),
                    "error_pct": round(error_pct2, 4),
                })
                st.rerun()

    # ------------------------------------------------------
    # 현금흐름 게임
    # ------------------------------------------------------
    elif phase == "현금흐름 게임":
        st.subheader("2. 현금흐름 대결 · 3라운드")
        st.caption("각 라운드에서 연 5% 할인 기준 현재가치가 더 큰 현금흐름을 고르세요. 제출 전에는 정답이 공개되지 않습니다.")

        rounds = [
            {
                "title": "라운드 1",
                "A_text": "A: 1년 후 300만원 + 3년 후 200만원",
                "A_cf": [(1, 300), (3, 200)],
                "B_text": "B: 1년 후 100만원 + 2년 후 150만원 + 3년 후 250만원",
                "B_cf": [(1, 100), (2, 150), (3, 250)],
            },
            {
                "title": "라운드 2",
                "A_text": "A: 2년 후 500만원",
                "A_cf": [(2, 500)],
                "B_text": "B: 1년 후 200만원 + 3년 후 300만원",
                "B_cf": [(1, 200), (3, 300)],
            },
            {
                "title": "라운드 3",
                "A_text": "A: 1년 후 150만원 + 2년 후 150만원 + 3년 후 200만원",
                "A_cf": [(1, 150), (2, 150), (3, 200)],
                "B_text": "B: 1년 후 250만원 + 2년 후 100만원 + 3년 후 150만원",
                "B_cf": [(1, 250), (2, 100), (3, 150)],
            },
        ]

        rate = 0.05
        old = my_response(my_class, me, "cashflow_game")

        if old:
            p = old["payload"]
            st.success(f"제출 완료 · {p['score']} / 3 정답")
            for i, rd in enumerate(rounds, start=1):
                pv_a = cashflow_pv(rd["A_cf"], rate)
                pv_b = cashflow_pv(rd["B_cf"], rate)
                correct = "A" if pv_a > pv_b else "B"
                mine = p[f"round{i}"]
                st.markdown(f"#### {rd['title']}")
                st.write(rd["A_text"])
                st.write(rd["B_text"])
                if mine == correct:
                    st.success(f"내 선택 {mine} · 정답")
                else:
                    st.error(f"내 선택 {mine} · 정답 {correct}")
                st.caption(f"A의 현재가치 {pv_a:,.2f}만원 · B의 현재가치 {pv_b:,.2f}만원")
        else:
            with st.form("cashflow_battle_form"):
                answers = []
                for i, rd in enumerate(rounds, start=1):
                    st.markdown(f"### 🎯 {rd['title']}")
                    st.write(rd["A_text"])
                    st.write(rd["B_text"])
                    ans = st.radio(
                        "현재가치가 더 큰 쪽",
                        ["A", "B"],
                        index=None,
                        horizontal=True,
                        key=f"cash_round_{i}",
                    )
                    answers.append(ans)
                    st.write("---")

                submitted = st.form_submit_button("🔒 3라운드 제출", type="primary")
                if submitted:
                    if any(a is None for a in answers):
                        st.warning("세 라운드 모두 선택해주세요.")
                    else:
                        correct_answers = []
                        for rd in rounds:
                            pv_a = cashflow_pv(rd["A_cf"], rate)
                            pv_b = cashflow_pv(rd["B_cf"], rate)
                            correct_answers.append("A" if pv_a > pv_b else "B")
                        score = sum(a == c for a, c in zip(answers, correct_answers))
                        save_response(my_class, me, "cashflow_game", {
                            "round1": answers[0],
                            "round2": answers[1],
                            "round3": answers[2],
                            "score": score,
                        })
                        st.rerun()

    # ------------------------------------------------------
    # 수익률 탐정
    # ------------------------------------------------------
    elif phase == "수익률 탐정":
        st.subheader("3. 수익률 탐정 · 나만의 제약조건")
        scenario = get_student_scenario(my_class, me)
        optimum, best_combo = scenario_optimum(scenario)

        st.info(
            f"내 미션: **3년 산술평균을 {scenario['target_avg']}%로 맞추면서 최종자산을 최소화**하세요. "
            f"추가 조건: **{scenario['rule']}**"
        )
        st.caption(
            f"각 수익률은 {scenario['min_r']}%~{scenario['max_r']}%, {scenario['step']}% 단위입니다. "
            "학생마다 제약조건이 다릅니다."
        )

        old = my_response(my_class, me, "return_detective")

        if old:
            p = old["payload"]
            st.success(
                f"제출 완료 · 수익률 {p['returns_pct']} · 최종자산 {p['final_wealth']:.2f} · "
                f"이론적 최솟값과의 차이 {p['gap_pct']:.2f}%"
            )
            chart_df = pd.DataFrame({
                "연도": [0, 1, 2, 3],
                "자산": p["wealth_path"],
            }).set_index("연도")
            st.line_chart(chart_df)
            st.caption("연도 0이 시작이므로 그래프의 맨 왼쪽이 시작자산 100입니다.")
            st.metric("내 조건의 이론적 최솟값", f"{p['optimum']:.2f}")
        else:
            vals = []
            cols = st.columns(3)
            fixed = scenario.get("fixed", {})

            for i in range(3):
                if i in fixed:
                    cols[i].metric(f"{i+1}년차 수익률", f"{fixed[i]:+d}% (고정)")
                    vals.append(fixed[i])
                else:
                    default = min(max(scenario["target_avg"], scenario["min_r"]), scenario["max_r"])
                    v = cols[i].slider(
                        f"{i+1}년차 수익률(%)",
                        scenario["min_r"],
                        scenario["max_r"],
                        default,
                        step=scenario["step"],
                        key=f"return_{scenario['name']}_{i}",
                    )
                    vals.append(v)

            avg = sum(vals) / 3
            valid = scenario_valid(tuple(vals), scenario)
            current_wealth = final_wealth(100, [v / 100 for v in vals])

            st.metric("현재 산술평균", f"{avg:.2f}%")
            if valid:
                st.success("✅ 모든 제약조건 충족")
                st.metric("현재 최종자산", f"{current_wealth:.2f}")
            else:
                st.warning("아직 제약조건을 모두 만족하지 못했습니다.")

            if st.button("🔒 이 조합으로 제출", type="primary", disabled=not valid):
                value = 100.0
                path = [value]
                for r in [v / 100 for v in vals]:
                    value *= (1 + r)
                    path.append(round(value, 4))

                gap_pct = (current_wealth - optimum) / optimum * 100 if optimum else 0.0
                save_response(my_class, me, "return_detective", {
                    "scenario": scenario["name"],
                    "rule": scenario["rule"],
                    "target_avg": scenario["target_avg"],
                    "returns_pct": vals,
                    "arithmetic_pct": avg,
                    "geometric_pct": round(geometric_mean([v / 100 for v in vals]) * 100, 4),
                    "final_wealth": round(current_wealth, 4),
                    "optimum": round(optimum, 4),
                    "gap_pct": round(gap_pct, 4),
                    "wealth_path": path,
                })
                st.rerun()

    # ------------------------------------------------------
    # 기대수익률 대결
    # ------------------------------------------------------
    elif phase == "기대수익률 대결":
        st.subheader("4. 기대수익률 대결")
        st.write("두 자산의 기대수익률은 같습니다. **더 위험한 자산**을 찾아 제출하세요.")

        probs = [0.25, 0.50, 0.25]
        a = [0.50, 0.05, -0.40]
        b = [0.20, 0.05, -0.10]
        exp_a = sum(p * r for p, r in zip(probs, a))
        exp_b = sum(p * r for p, r in zip(probs, b))

        display_df = pd.DataFrame({
            "경제상황": ["호황", "보통", "불황"],
            "확률": ["25%", "50%", "25%"],
            "자산 A 수익률": ["+50%", "+5%", "-40%"],
            "자산 B 수익률": ["+20%", "+5%", "-10%"],
        })
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        old = my_response(my_class, me, "expected_game")
        if old:
            p = old["payload"]
            if p["correct"]:
                st.success("정답입니다. 자산 A의 변동 범위가 더 큽니다.")
            else:
                st.error("자산 A가 더 위험합니다.")
            st.write(f"자산 A 기대수익률: **{p['exp_a_pct']:.1f}%**")
            st.write(f"자산 B 기대수익률: **{p['exp_b_pct']:.1f}%**")
            st.info("기대수익률이 같더라도 가능한 수익률의 분산·변동 범위가 다르면 위험은 달라질 수 있습니다.")
        else:
            with st.form("expected_form"):
                pick = st.radio("더 위험한 자산", ["자산 A", "자산 B"], index=None)
                submit = st.form_submit_button("🔒 제출", type="primary")
                if submit:
                    if pick is None:
                        st.warning("자산을 선택해주세요.")
                    else:
                        save_response(my_class, me, "expected_game", {
                            "pick": pick,
                            "correct": pick == "자산 A",
                            "exp_a_pct": round(exp_a * 100, 4),
                            "exp_b_pct": round(exp_b * 100, 4),
                        })
                        st.rerun()

    # ------------------------------------------------------
    # 요구수익률 금고
    # ------------------------------------------------------
    elif phase == "요구수익률 금고":
        st.subheader("5. 요구수익률 금고 · 조립 → 역산 → 투자판단")
        st.caption("세 금고는 서로 다른 방식으로 풀어야 합니다. 각 금고 1점, 총 3점입니다.")

        old = my_response(my_class, me, "required_vault")

        if old:
            p = old["payload"]
            st.success(f"제출 완료 · {p['score']} / 3개 금고 열림")

            if p["m1_correct"]:
                st.write(f"🔓 금고 1 · 조립: 내 답 {p['m1']:.1f}%")
            else:
                st.write(f"🔒 금고 1 · 조립: 내 답 {p['m1']:.1f}% · 정답 9.0%")

            if p["m2_correct"]:
                st.write(f"🔓 금고 2 · 역산: 내 답 {p['m2']:.1f}%")
            else:
                st.write(f"🔒 금고 2 · 역산: 내 답 {p['m2']:.1f}% · 정답 3.0%")

            if p["m3_correct"]:
                st.write(f"🔓 금고 3 · 투자판단: 내 선택 {p['m3']}")
            else:
                st.write(f"🔒 금고 3 · 투자판단: 내 선택 {p['m3']} · 정답 자산 A")

            st.info(
                "금고 1은 요구수익률을 직접 조립하고, 금고 2는 위험보상률을 거꾸로 찾고, "
                "금고 3은 기대수익률과 요구수익률을 비교해 투자 매력도를 판단합니다."
            )
        else:
            with st.form("required_vault_form"):
                st.markdown("### 🔐 금고 1 · 조립")
                st.write("실질무위험수익률 2% · 기대물가상승률 3% · 위험보상률 4%")
                m1 = st.number_input(
                    "요구수익률(%)",
                    min_value=0.0, max_value=30.0, step=0.5,
                    key="vault_m1",
                )

                st.write("---")
                st.markdown("### 🔐 금고 2 · 역산")
                st.write("요구수익률 8% · 실질무위험수익률 2% · 기대물가상승률 3%")
                m2 = st.number_input(
                    "위험보상률(%)",
                    min_value=0.0, max_value=20.0, step=0.5,
                    key="vault_m2",
                )

                st.write("---")
                st.markdown("### 🔐 금고 3 · 투자판단")
                st.write("자산 A: 기대수익률 8%, 요구수익률 6%")
                st.write("자산 B: 기대수익률 8%, 요구수익률 10%")
                m3 = st.radio(
                    "이 투자자에게 상대적으로 더 매력적인 자산은?",
                    ["자산 A", "자산 B", "둘 다 같음"],
                    index=None,
                    key="vault_m3",
                )

                submitted = st.form_submit_button("🔒 세 금고 제출", type="primary")
                if submitted:
                    if m3 is None:
                        st.warning("금고 3의 답을 선택해주세요.")
                    else:
                        m1_correct = abs(m1 - 9.0) < 1e-9
                        m2_correct = abs(m2 - 3.0) < 1e-9
                        m3_correct = m3 == "자산 A"
                        score = int(m1_correct) + int(m2_correct) + int(m3_correct)

                        save_response(my_class, me, "required_vault", {
                            "m1": m1,
                            "m2": m2,
                            "m3": m3,
                            "m1_correct": m1_correct,
                            "m2_correct": m2_correct,
                            "m3_correct": m3_correct,
                            "score": score,
                        })
                        st.rerun()

    # ------------------------------------------------------
    # 결과
    # ------------------------------------------------------
    elif phase == "결과":
        st.subheader("6. 3주차 활동 기록")
        stages = [
            ("복리격차", "tvm_gap"),
            ("PV 스나이퍼", "pv_sniper"),
            ("현금흐름", "cashflow_game"),
            ("수익률 탐정", "return_detective"),
            ("기대수익률", "expected_game"),
            ("요구수익률", "required_vault"),
        ]
        cols = st.columns(3)
        for i, (label, key) in enumerate(stages):
            cols[i % 3].metric(label, "완료" if my_response(my_class, me, key) else "미완료")

    elif phase == "종료":
        st.success("3주차 Money Time Machine 활동이 종료되었습니다.")


# ==========================================================
# 교수 화면
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

    if phase == "TVM 타임머신":
        st.subheader("🎯 미션 A · 복리격차 순위")
        df = all_responses(my_class, "tvm_gap")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for _, r in df.iterrows():
                p = r["payload"] or {}
                rows.append({
                    "이름": r["name"],
                    "현재금액": p.get("principal"),
                    "이율(%)": p.get("rate_pct"),
                    "기간": p.get("years"),
                    "격차(만원)": p.get("gap"),
                    "목표와 차이": p.get("error_abs"),
                    "점수": p.get("score"),
                })
            rank = pd.DataFrame(rows).sort_values(["목표와 차이", "이름"])
            st.dataframe(rank, use_container_width=True, hide_index=True)

        st.subheader("🎯 미션 B · PV 스나이퍼 순위")
        df2 = all_responses(my_class, "pv_sniper")
        if df2.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for _, r in df2.iterrows():
                p = r["payload"] or {}
                rows.append({
                    "이름": r["name"],
                    "추정(만원)": p.get("guess"),
                    "정답(만원)": p.get("exact_pv"),
                    "오차(만원)": p.get("error_abs"),
                    "오차율(%)": p.get("error_pct"),
                })
            rank = pd.DataFrame(rows).sort_values(["오차율(%)", "오차(만원)", "이름"])
            st.dataframe(rank, use_container_width=True, hide_index=True)

    elif phase == "현금흐름 게임":
        df = all_responses(my_class, "cashflow_game")
        st.subheader("현금흐름 대결 결과")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for _, r in df.iterrows():
                p = r["payload"] or {}
                rows.append({
                    "이름": r["name"],
                    "1R": p.get("round1"),
                    "2R": p.get("round2"),
                    "3R": p.get("round3"),
                    "정답수": p.get("score"),
                })
            result = pd.DataFrame(rows).sort_values(["정답수", "이름"], ascending=[False, True])
            st.dataframe(result, use_container_width=True, hide_index=True)
            st.bar_chart(result["정답수"].value_counts().sort_index())

    elif phase == "수익률 탐정":
        df = all_responses(my_class, "return_detective")
        st.subheader("수익률 탐정 순위 · 자기 조건의 최솟값에 가까울수록 성공")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for _, r in df.iterrows():
                p = r["payload"] or {}
                rows.append({
                    "이름": r["name"],
                    "미션": p.get("scenario"),
                    "제약조건": p.get("rule"),
                    "목표 산술평균(%)": p.get("target_avg"),
                    "수익률 조합": str(p.get("returns_pct")),
                    "최종자산": p.get("final_wealth"),
                    "이론적 최솟값": p.get("optimum"),
                    "최솟값과 차이(%)": p.get("gap_pct"),
                })
            rank = pd.DataFrame(rows).sort_values(["최솟값과 차이(%)", "이름"])
            st.dataframe(rank, use_container_width=True, hide_index=True)

    elif phase == "기대수익률 대결":
        df = all_responses(my_class, "expected_game")
        st.subheader("기대수익률 대결")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            picks = pd.Series([(p or {}).get("pick") for p in df["payload"]]).value_counts()
            st.bar_chart(picks)
            correct = sum(bool((p or {}).get("correct")) for p in df["payload"])
            st.metric("정답률", f"{correct / len(df) * 100:.1f}%")

    elif phase == "요구수익률 금고":
        df = all_responses(my_class, "required_vault")
        st.subheader("요구수익률 금고")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for _, r in df.iterrows():
                p = r["payload"] or {}
                rows.append({
                    "이름": r["name"],
                    "조립": "O" if p.get("m1_correct") else "X",
                    "역산": "O" if p.get("m2_correct") else "X",
                    "투자판단": "O" if p.get("m3_correct") else "X",
                    "총점": p.get("score", 0),
                })
            result = pd.DataFrame(rows).sort_values(["총점", "이름"], ascending=[False, True])
            st.dataframe(result, use_container_width=True, hide_index=True)
            st.bar_chart(result["총점"].value_counts().sort_index())

    elif phase == "결과":
        stages = [
            ("복리격차", "tvm_gap"),
            ("PV 스나이퍼", "pv_sniper"),
            ("현금흐름", "cashflow_game"),
            ("수익률 탐정", "return_detective"),
            ("기대수익률", "expected_game"),
            ("요구수익률", "required_vault"),
        ]
        rows = [{"활동": label, "제출 인원": len(all_responses(my_class, key))} for label, key in stages]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with st.expander("⚠️ 데이터 관리"):
        if st.button("이 분반 3주차 응답 삭제"):
            supabase.table(T_RESPONSES).delete().eq("class_name", my_class).execute()
            st.rerun()

        if st.button("이 분반 3주차 전체 초기화"):
            supabase.table(T_RESPONSES).delete().eq("class_name", my_class).execute()
            supabase.table(T_STUDENTS).delete().eq("class_name", my_class).execute()
            set_phase(my_class, "대기")
            st.rerun()
