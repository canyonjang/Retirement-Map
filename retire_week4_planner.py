import pandas as pd
import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title="Retirement Planner Clinic · 4주차", page_icon="🩺", layout="wide")

CLASSES = ["인하대", "숙대1", "숙대2"]
PHASES = [
    "대기",
    "학생입장",
    "사례 정보 찾기",
    "부족자금 퍼즐",
    "플랜 구조대",
    "자산배분 실험실",
    "공적연금 핵심판단",
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
    st.caption("4주차 · 사례를 통해 은퇴설계의 핵심 절차를 직접 적용해봅니다.")
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
    if phase == "사례 정보 찾기":
        st.subheader("1. 사례 정보 찾기 · 무엇이 더 필요할까?")
        st.write(
            "다음은 **은퇴까지 20년 남은 가상 사례**입니다."
        )
        st.info(
            "현재 은퇴자산 1억원 · 현재가치 기준 희망 은퇴생활비 월 350만원"
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

        old = my_response(my_class, me, "case_info")
        if old:
            p = old["payload"]
            found = p.get("found_count", 0)
            extra = p.get("extra_count", 0)

            st.success(f"핵심정보 4개 중 **{found}개 발견**")
            if extra == 0:
                st.info("불필요한 정보는 선택하지 않았습니다.")
            else:
                st.warning(f"불필요한 정보도 **{extra}개 선택**했습니다.")

            st.write("내 선택:", ", ".join(p["selected"]))

            missed = p.get("missed", [])
            extras = p.get("extras", [])

            if missed:
                st.write("아직 찾지 못한 핵심정보:", ", ".join(missed))
            if extras:
                st.write("은퇴설계와 직접 관련 없는 선택:", ", ".join(extras))

            if found == 4 and extra == 0:
                st.success("필요한 정보만 정확하게 골라냈습니다.")
            elif found == 4:
                st.info(
                    "필요한 정보는 모두 찾았습니다. 이제 은퇴설계에 직접 필요한 정보와 "
                    "그렇지 않은 정보를 구분해보세요."
                )
            else:
                st.info(
                    "은퇴기간, 물가상승률, 세후투자수익률, 예상 공적연금액은 "
                    "은퇴설계의 핵심 정보·가정입니다. 특히 생활비가 '현재가치 기준'으로 "
                    "제시되어 있으므로 미래 생활비를 생각하려면 물가상승률 가정이 필요합니다."
                )
        else:
            with st.form("case_info_form"):
                selected = st.multiselect("추가로 확인할 항목", options)
                submitted = st.form_submit_button("🔒 제출", type="primary")
                if submitted:
                    selected_set = set(selected)
                    found_items = sorted(selected_set & correct_set)
                    extra_items = sorted(selected_set - correct_set)
                    missed_items = sorted(correct_set - selected_set)

                    save_response(my_class, me, "case_info", {
                        "selected": selected,
                        "found_count": len(found_items),
                        "extra_count": len(extra_items),
                        "found": found_items,
                        "extras": extra_items,
                        "missed": missed_items,
                        "perfect": selected_set == correct_set,
                    })
                    st.rerun()

    # ------------------------------------------------------
    # 2. 부족자금 진단
    # ------------------------------------------------------
    elif phase == "부족자금 퍼즐":
        st.subheader("2. 부족자금 퍼즐 · 복잡한 계산보다 구조를 보자")
        st.write("앱이 화폐의 시간가치를 반영해 **은퇴시점에 필요한 총은퇴일시금**을 계산했다고 가정합니다.")

        st.metric("은퇴시점에 필요한 총은퇴일시금", "4.2억원")

        old = my_response(my_class, me, "shortage_puzzle")
        if old:
            p = old["payload"]
            st.success(f"제출 완료 · {p['score']} / 2")
            st.write(f"① 추가로 필요한 은퇴일시금: 내 답 **{p['q1']}** · 정답 **2.0억원**")
            st.caption(
                "현재 은퇴저축의 미래가치 1.5억원 + 퇴직연금 예상자산 0.7억원 = "
                "은퇴에 사용할 예상자산 2.2억원. 비상자금 0.3억원은 은퇴자금으로 사용하지 않으므로 제외합니다."
            )
            st.write(
                "② 다음 단계: 내 답 **"
                + p["q2"]
                + "** · 정답 **필요한 저축액을 계산하고 실제 저축여력과 비교한다**"
            )
            st.info(
                "핵심은 단순히 가진 돈을 모두 더하는 것이 아니라, "
                "은퇴에 실제로 사용할 자산을 구분한 뒤 '필요자금 − 준비될 은퇴자산 = 부족자금'의 구조를 이해하는 것입니다."
            )
        else:
            with st.form("shortage_puzzle_form"):
                st.markdown("**① 추가로 필요한 은퇴일시금은?**")
                st.write("은퇴시점에 확보될 것으로 예상되는 자산은 다음과 같습니다.")
                st.write("- 현재 은퇴저축의 미래가치: **1.5억원**")
                st.write("- 퇴직연금 예상자산: **0.7억원**")
                st.write("- 별도로 보유한 비상자금: **0.3억원**")
                st.caption("단, 비상자금은 은퇴자금으로 사용하지 않습니다.")

                q1 = st.radio(
                    "추가로 필요한 은퇴일시금",
                    ["1.7억원", "2.0억원", "2.3억원", "2.7억원"],
                    index=None,
                )

                st.write("---")
                q2 = st.radio(
                    "② 부족자금을 확인한 뒤 은퇴설계에서 다음으로 할 일은?",
                    [
                        "필요한 저축액을 계산하고 실제 저축여력과 비교한다",
                        "최근 수익률이 가장 높은 상품을 바로 고른다",
                        "은퇴생활비 목표를 먼저 없앤다",
                        "현재 보유자산을 계산에서 제외한다",
                    ],
                    index=None,
                )
                submitted = st.form_submit_button("🧩 퍼즐 제출", type="primary")
                if submitted:
                    if q1 is None or q2 is None:
                        st.warning("두 문항에 모두 답해주세요.")
                    else:
                        c1_ok = q1 == "2.0억원"
                        c2_ok = q2 == "필요한 저축액을 계산하고 실제 저축여력과 비교한다"
                        save_response(my_class, me, "shortage_puzzle", {
                            "q1": q1,
                            "q2": q2,
                            "q1_correct": c1_ok,
                            "q2_correct": c2_ok,
                            "score": int(c1_ok) + int(c2_ok),
                        })
                        st.rerun()

    # ------------------------------------------------------
    # 3. 플랜 구조대
    # ------------------------------------------------------
    elif phase == "플랜 구조대":
        st.subheader("3. 플랜 구조대 · 숫자상 가능한 것과 좋은 가정을 구분하라")
        st.write(
            "은퇴까지 20년 남은 가상 사례입니다. 앱의 계산 결과 필요한 추가 저축액은 "
            f"월 **{BASE['monthly_saving']/10_000:.1f}만원**이지만, 실제 저축여력은 **월 45만원**입니다."
        )
        st.write("내가 먼저 검토할 수정안을 하나 선택하세요.")

        choices = {
            "A": ("은퇴시기를 2년 늦춘다", case_values(retire_years=22, retirement_years=23)),
            "B": ("목표 은퇴생활비를 월 350만원 → 330만원으로 조정한다", case_values(target_month=3_300_000)),
            "C": ("다른 조건은 그대로 두고 예상수익률만 연 4% → 5%로 높여 잡는다", case_values(pre_return=0.05)),
        }

        old = my_response(my_class, me, "plan_rescue")
        if old:
            p = old["payload"]
            st.write(f"내가 선택한 수정안: **{p['choice']}. {p['choice_text']}**")
            st.write("---")

            rows = []
            for key, (text, result) in choices.items():
                rows.append({
                    "수정안": key,
                    "내용": text,
                    "수정 후 필요 월저축액": f"{result['monthly_saving']/10_000:.1f}만원",
                    "월 45만원 이내": "O" if result["monthly_saving"]/10_000 <= 45 else "X",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            if p["choice"] in ("A", "B"):
                st.success(
                    "A와 B는 은퇴시기나 목표생활비처럼 실제 설계조건을 바꾸는 방법입니다. "
                    "어느 쪽이 더 나은지는 개인의 가치와 상황에 따라 달라질 수 있습니다."
                )
            else:
                st.warning(
                    "C도 계산상 필요저축액을 낮추지만, 실제 행동을 바꾸지 않고 "
                    "미래 수익률 가정만 높인 것입니다. 은퇴설계에서는 이런 낙관적 가정을 주의해야 합니다."
                )
        else:
            with st.form("rescue_form"):
                choice = st.radio(
                    "수정안",
                    [f"{k}. {v[0]}" for k, v in choices.items()],
                    index=None,
                )
                submitted = st.form_submit_button("🚑 이 수정안 선택", type="primary")
                if submitted:
                    if choice is None:
                        st.warning("수정안을 선택해주세요.")
                    else:
                        key = choice[0]
                        text, result = choices[key]
                        monthly_man = result["monthly_saving"] / 10_000
                        save_response(my_class, me, "plan_rescue", {
                            "choice": key,
                            "choice_text": text,
                            "monthly_saving_man": round(monthly_man, 4),
                        })
                        st.rerun()

    # ------------------------------------------------------
    # 4. 자산배분 처방
    # ------------------------------------------------------
    elif phase == "자산배분 실험실":
        st.subheader("4. 자산배분 실험실 · 같은 조건, 서로 다른 답")
        st.write(
            "주식·채권·현금·대체자산의 비중을 직접 조정하면서 "
            "**자산배분에 따라 기대수익률이 어떻게 달라지는지 확인해보세요.** "
            "아래 조건을 모두 충족시키면서 **기대수익률을 최대한 높여보세요.**"
        )
        st.info(
            "상황: 은퇴까지 15년 남았고, 중간 수준의 투자위험을 감수할 수 있음\n\n"
            "조건: 주식 ≤ 50% · 채권 ≥ 30% · 현금 ≥ 10% · 대체자산 ≤ 20% · "
            "가정 기대수익률 ≥ 4.0% · 합계 100%"
        )
        st.caption("수업용 단순화 가정 기대수익률: 주식 7%, 채권 3%, 현금 2%, 대체자산 5%")

        old = my_response(my_class, me, "allocation")
        if old:
            p = old["payload"]
            st.success("내 자산배분안 제출 완료")
            st.write(
                f"주식 {p['stock']}% · 채권 {p['bond']}% · 현금 {p['cash']}% · "
                f"대체자산 {p['alt']}%"
            )
            st.metric("가정 기대수익률", f"{p['expected_return']:.2f}%")
            st.info(
                "정답은 하나가 아닙니다. 같은 조건에서도 여러 자산배분안이 가능합니다. "
                "다른 학생들의 조합과 비교하면서 조건 안에서 기대수익률을 더 높일 수 있는지 생각해보세요."
            )
        else:
            c1, c2, c3, c4 = st.columns(4)
            stock = c1.slider("주식(%)", 0, 100, 40, step=5)
            bond = c2.slider("채권(%)", 0, 100, 35, step=5)
            cash = c3.slider("현금(%)", 0, 100, 15, step=5)
            alt = c4.slider("대체자산(%)", 0, 100, 10, step=5)

            total = stock + bond + cash + alt
            er = stock*0.07 + bond*0.03 + cash*0.02 + alt*0.05

            checks = {
                "합계 100%": total == 100,
                "주식 ≤ 50%": stock <= 50,
                "채권 ≥ 30%": bond >= 30,
                "현금 ≥ 10%": cash >= 10,
                "대체자산 ≤ 20%": alt <= 20,
                "기대수익률 ≥ 4.0%": er >= 4.0,
            }
            valid = all(checks.values())

            st.metric("합계", f"{total}%")
            st.metric("가정 기대수익률", f"{er:.2f}%")
            st.write(" · ".join([f"{'✅' if ok else '❌'} {label}" for label, ok in checks.items()]))

            if valid:
                st.success("모든 조건을 만족했습니다. 이 조합도 가능한 자산배분안입니다.")
            else:
                st.warning("조건을 보면서 비중을 다시 조정해보세요.")

            if st.button("📊 이 자산배분안 제출", type="primary", disabled=not valid):
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
    elif phase == "공적연금 핵심판단":
        st.subheader("5. 공적연금 핵심판단 · 지금 기억할 것은 숫자가 아니라 원리")
        st.caption("보험료율이나 수급액 같은 세부 숫자가 아니라, 대학생이 앞으로 기억할 핵심 원리를 확인합니다.")

        old = my_response(my_class, me, "pension_core")
        if old:
            p = old["payload"]
            st.success(f"제출 완료 · {p['score']} / 3")

            st.markdown("#### ① 가입기간")
            st.write(f"내 판단: {p['q1']} · 정답: **아니다**")
            st.caption("회사를 옮기거나 가입자 종류가 바뀌어도 인정되는 가입기간은 합산됩니다.")

            st.markdown("#### ② 제도의 성격")
            st.write(f"내 판단: {p['q2']} · 정답: **아니다**")
            st.caption("국민연금은 개인저축통장이 아니라 사회적 위험에 공동으로 대비하는 사회보험입니다.")

            st.markdown("#### ③ 은퇴설계에서의 역할")
            st.write(f"내 판단: {p['q3']} · 정답: **맞다**")
            st.caption("공적연금은 중요한 노후소득원이지만, 개인의 전체 은퇴설계를 대신하지는 않습니다.")
        else:
            with st.form("pension_core_form"):
                st.markdown("### ① 가입기간")
                st.write("“취업 후 회사를 옮기거나 가입자 종류가 바뀌면, 이전 국민연금 가입기간은 사라지고 다시 시작한다.”")
                q1 = st.radio("판단", ["맞다", "아니다"], index=None, horizontal=True, key="w4core1")

                st.write("---")
                st.markdown("### ② 제도의 성격")
                st.write("“국민연금은 내가 낸 돈을 내 개인계좌에 그대로 쌓아두었다가 돌려받는 개인저축 상품이다.”")
                q2 = st.radio("판단", ["맞다", "아니다"], index=None, horizontal=True, key="w4core2")

                st.write("---")
                st.markdown("### ③ 은퇴설계에서의 역할")
                st.write("“공적연금은 노후소득의 중요한 한 축이지만, 공적연금만 안다고 은퇴설계가 끝나는 것은 아니다.”")
                q3 = st.radio("판단", ["맞다", "아니다"], index=None, horizontal=True, key="w4core3")

                submitted = st.form_submit_button("🔒 세 문장 판단 완료", type="primary")
                if submitted:
                    if any(x is None for x in [q1, q2, q3]):
                        st.warning("세 문장에 모두 답해주세요.")
                    else:
                        c1 = q1 == "아니다"
                        c2 = q2 == "아니다"
                        c3 = q3 == "맞다"
                        save_response(my_class, me, "pension_core", {
                            "q1": q1, "q2": q2, "q3": q3,
                            "q1_correct": c1, "q2_correct": c2, "q3_correct": c3,
                            "score": int(c1) + int(c2) + int(c3),
                        })
                        st.rerun()

    elif phase == "결과":
        st.subheader("6. 나의 Retirement Planner Clinic 기록")
        stages = [
            ("사례정보", "case_info"),
            ("부족자금", "shortage_puzzle"),
            ("플랜구조", "plan_rescue"),
            ("자산배분", "allocation"),
            ("공적연금", "pension_core"),
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

    if phase == "사례 정보 찾기":
        df = all_responses(my_class, "case_info")
        st.subheader("사례 정보 찾기 결과")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for _, r in df.iterrows():
                p = r["payload"] or {}

                # 예전 테스트 데이터가 남아 있어도 화면이 깨지지 않도록 보정
                selected = set(p.get("selected", []))
                correct_set = {
                    "예상 은퇴기간(또는 기대수명)",
                    "예상 물가상승률",
                    "은퇴자산의 세후투자수익률",
                    "예상 공적연금액",
                }
                found_count = p.get("found_count", len(selected & correct_set))
                extra_count = p.get("extra_count", len(selected - correct_set))

                rows.append({
                    "이름": r["name"],
                    "핵심정보 발견": f"{found_count}/4",
                    "불필요정보 선택": extra_count,
                    "핵심정보 모두 발견": "O" if found_count == 4 else "X",
                    "불필요정보 없음": "O" if extra_count == 0 else "X",
                })

            result = pd.DataFrame(rows)
            st.dataframe(result, use_container_width=True, hide_index=True)

            avg_found = []
            avg_extra = []
            for _, r in df.iterrows():
                p = r["payload"] or {}
                selected = set(p.get("selected", []))
                correct_set = {
                    "예상 은퇴기간(또는 기대수명)",
                    "예상 물가상승률",
                    "은퇴자산의 세후투자수익률",
                    "예상 공적연금액",
                }
                avg_found.append(p.get("found_count", len(selected & correct_set)))
                avg_extra.append(p.get("extra_count", len(selected - correct_set)))

            c1, c2 = st.columns(2)
            c1.metric("평균 핵심정보 발견", f"{sum(avg_found)/len(avg_found):.2f} / 4")
            c2.metric("평균 불필요정보 선택", f"{sum(avg_extra)/len(avg_extra):.2f}개")

    elif phase == "부족자금 퍼즐":
        df = all_responses(my_class, "shortage_puzzle")
        st.subheader("부족자금 퍼즐 결과")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for _, r in df.iterrows():
                p = r["payload"] or {}
                rows.append({
                    "이름": r["name"],
                    "부족자금": "O" if p.get("q1_correct") else "X",
                    "다음 단계": "O" if p.get("q2_correct") else "X",
                    "총점": p.get("score", 0),
                })
            result = pd.DataFrame(rows).sort_values(["총점", "이름"], ascending=[False, True])
            st.dataframe(result, use_container_width=True, hide_index=True)
            st.bar_chart(result["총점"].value_counts().sort_index())

    elif phase == "플랜 구조대":
        df = all_responses(my_class, "plan_rescue")
        st.subheader("플랜 구조대 결과")

        st.markdown("#### A·B·C 수정안 비교")
        plan_options = {
            "A": ("은퇴시기를 2년 늦춘다", case_values(retire_years=22, retirement_years=23)),
            "B": ("목표 은퇴생활비를 월 350만원 → 330만원으로 조정한다", case_values(target_month=3_300_000)),
            "C": ("다른 조건은 그대로 두고 예상수익률만 연 4% → 5%로 높여 잡는다", case_values(pre_return=0.05)),
        }

        option_rows = []
        for key, (text, result) in plan_options.items():
            monthly_man = result["monthly_saving"] / 10_000
            option_rows.append({
                "수정안": key,
                "내용": text,
                "수정 후 필요 월저축액": f"{monthly_man:.1f}만원",
                "월 45만원 이내": "O" if monthly_man <= 45 else "X",
            })
        st.dataframe(pd.DataFrame(option_rows), use_container_width=True, hide_index=True)

        st.caption(
            "A와 B는 실제 설계조건을 바꾸는 방법이고, C는 실제 행동이나 목표는 그대로 둔 채 "
            "예상수익률 가정만 높이는 방법입니다."
        )

        st.markdown("#### 학생 선택 결과")
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
                    "수정 후 필요 월저축(만원)": p.get("monthly_saving_man"),
                })
            result = pd.DataFrame(rows)
            st.dataframe(result, use_container_width=True, hide_index=True)
            st.bar_chart(result["선택"].value_counts())

    elif phase == "자산배분 실험실":
        df = all_responses(my_class, "allocation")
        st.subheader("자산배분 실험실 결과")
        st.caption(
            "학생들은 같은 조건 안에서 주식·채권·현금·대체자산 비중을 조정하고, "
            "기대수익률을 최대한 높이는 조합을 찾습니다."
        )

        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for _, r in df.iterrows():
                p = r["payload"] or {}
                rows.append({
                    "이름": r["name"],
                    "주식(%)": p.get("stock"),
                    "채권(%)": p.get("bond"),
                    "현금(%)": p.get("cash"),
                    "대체(%)": p.get("alt"),
                    "기대수익률(%)": p.get("expected_return"),
                })
            result = pd.DataFrame(rows).sort_values(
                ["기대수익률(%)", "이름"], ascending=[False, True]
            )
            st.dataframe(result, use_container_width=True, hide_index=True)

            c1, c2 = st.columns(2)
            c1.metric("현재 최고 기대수익률", f"{result['기대수익률(%)'].max():.2f}%")
            c2.metric("제출 학생", f"{len(result)}명")

            avg = result[["주식(%)", "채권(%)", "현금(%)", "대체(%)"]].mean()
            st.markdown("#### 학급 평균 자산배분")
            st.bar_chart(avg)

    elif phase == "공적연금 핵심판단":
        df = all_responses(my_class, "pension_core")
        st.subheader("공적연금 핵심판단 결과")

        st.markdown("#### 교수용 정답·해설")
        st.markdown(
            "**① 가입기간 — 정답: 아니다**  \n"
            "회사를 옮기거나 가입자 종류가 바뀌더라도 인정되는 국민연금 가입기간은 합산됩니다."
        )
        st.markdown(
            "**② 제도의 성격 — 정답: 아니다**  \n"
            "국민연금은 내가 낸 돈을 개인계좌에 그대로 적립해 돌려받는 개인저축상품이 아니라, "
            "노령·장애·사망 등의 사회적 위험에 공동으로 대비하는 사회보험입니다."
        )
        st.markdown(
            "**③ 은퇴설계에서의 역할 — 정답: 맞다**  \n"
            "공적연금은 중요한 노후소득원이지만, 목표생활비·퇴직연금·개인연금·금융자산 등과 "
            "함께 전체 은퇴설계 속에서 고려해야 합니다."
        )

        st.markdown("#### 학생 응답 결과")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for _, r in df.iterrows():
                p = r["payload"] or {}
                rows.append({
                    "이름": r["name"],
                    "가입기간": "O" if p.get("q1_correct") else "X",
                    "사회보험": "O" if p.get("q2_correct") else "X",
                    "은퇴설계 역할": "O" if p.get("q3_correct") else "X",
                    "총점": p.get("score", 0),
                })
            result = pd.DataFrame(rows).sort_values(["총점", "이름"], ascending=[False, True])
            st.dataframe(result, use_container_width=True, hide_index=True)
            st.bar_chart(result["총점"].value_counts().sort_index())

    elif phase == "결과":
        stages = [
            ("사례정보", "case_info"),
            ("부족자금", "shortage_puzzle"),
            ("플랜구조", "plan_rescue"),
            ("자산배분", "allocation"),
            ("공적연금", "pension_core"),
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
