import pandas as pd
import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title="Pension Architect · 5주차", page_icon="🏗️", layout="wide")

CLASSES = ["인하대", "숙대1", "숙대2"]
PHASES = [
    "대기", "학생입장", "DB·DC 구조 탐정", "DC 방치주의보",
    "TDF 착륙작전", "연금저축 vs IRP", "연금계좌 연결 퍼즐", "결과", "종료",
]

T_STATUS = "retire_w5_status"
T_STUDENTS = "retire_w5_students"
T_RESPONSES = "retire_w5_responses"

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
        .eq("class_name", class_name).eq("stage", stage).execute().data
    )
    return pd.DataFrame(rows)

def render_header(class_name, role):
    c1, c2 = st.columns([8, 2])
    with c1:
        st.title("🏗️ Pension Architect")
        st.caption(f"은퇴와 상속설계 · 5주차 · {class_name} · {role}")
    with c2:
        if st.button("로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()

DBDC_CARDS = [
    ("퇴직할 때 받을 급여 수준이 사전에 정해지는 구조", "DB"),
    ("적립금 운용 책임이 사용자(회사)에게 있음", "DB"),
    ("회사가 매년 일정 수준의 부담금을 근로자 계정에 납입", "DC"),
    ("근로자가 적립금 운용방법을 선택", "DC"),
    ("운용성과에 따라 최종 적립금이 달라질 수 있음", "DC"),
    ("운용성과에 대한 책임을 근로자가 부담", "DC"),
]

DC_WARNINGS = [
    {
        "title": "경고등 1 · 첫 적립",
        "question": "첫 직장에 취업했고 회사의 퇴직연금은 DC형입니다. 회사가 부담금을 넣었습니다. 가장 먼저 할 일은?",
        "options": [
            "퇴직할 때까지 그대로 둔다",
            "내 계좌의 운용상품과 자산배분을 확인한다",
            "회사가 알아서 운용한다고 생각하고 신경 쓰지 않는다",
        ],
        "answer": "내 계좌의 운용상품과 자산배분을 확인한다",
    },
    {
        "title": "경고등 2 · 운용지시 없음",
        "question": "DC 적립금의 운용지시가 장기간 없는 상황을 줄이기 위해 마련된 장치는?",
        "options": ["사전지정운용제도(디폴트옵션)", "퇴직금 중간정산", "국민연금 추후납부"],
        "answer": "사전지정운용제도(디폴트옵션)",
    },
    {
        "title": "경고등 3 · 장기 방치",
        "question": "DC형에 가입되어 있다는 사실만으로 장기 은퇴자금 관리가 끝났다고 볼 수 있을까?",
        "options": [
            "그렇다. 가입만 되어 있으면 충분하다",
            "아니다. 운용상품과 자산배분을 주기적으로 점검할 필요가 있다",
            "그렇다. 운용성과는 회사 책임이기 때문이다",
        ],
        "answer": "아니다. 운용상품과 자산배분을 주기적으로 점검할 필요가 있다",
    },
]

ACCOUNT_CASES = [
    {
        "title": "상황 1 · 운용 자유도",
        "text": "장기간 투자할 돈이고, ETF 등 위험자산 운용의 자유도가 중요합니다. 퇴직급여를 이전받는 목적은 아닙니다.",
        "options": ["연금저축펀드", "IRP", "둘 다 아님"],
        "answer": "연금저축펀드",
        "explain": "수업에서 다루는 단순화된 비교에서는 연금저축펀드가 위험자산 비중 제한이 없다는 점에서 이 상황에 상대적으로 더 부합합니다.",
    },
    {
        "title": "상황 2 · 이직과 퇴직급여",
        "text": "회사를 옮기게 되었고, 이전 직장의 퇴직급여를 노후자금으로 계속 이어서 관리하고 싶습니다.",
        "options": ["연금저축펀드", "IRP", "둘 다 아님"],
        "answer": "IRP",
        "explain": "IRP는 퇴직급여를 이전받아 계속 관리하는 통산 장치로 활용됩니다.",
    },
    {
        "title": "상황 3 · 곧 쓸 수도 있는 돈",
        "text": "1년 안에 병원비·이사비 등으로 쓸 수도 있는 비상자금 500만원이 생겼습니다. 세액공제를 위해 전부 연금계좌에 넣을까요?",
        "options": ["연금저축펀드", "IRP", "둘 다 아님"],
        "answer": "둘 다 아님",
        "explain": "연금계좌의 세제혜택만 보고 가까운 시일 안에 쓸 수 있는 비상자금까지 묶는 것은 적절하지 않습니다.",
    },
]

PATH_CASES = [
    {
        "title": "체크포인트 1 · 첫 직장",
        "text": "민지의 첫 직장 퇴직연금은 DC형입니다. 회사가 부담금을 납입했습니다. 민지가 할 행동은?",
        "options": [
            "회사가 알아서 운용할 것이므로 그대로 둔다",
            "운용상품과 자산배분을 직접 확인한다",
            "퇴직할 때 한꺼번에 운용한다",
        ],
        "answer": "운용상품과 자산배분을 직접 확인한다",
        "explain": "DC형은 근로자가 적립금 운용방법을 선택하고 운용결과에 책임을 집니다.",
    },
    {
        "title": "체크포인트 2 · 운용지시를 미루고 있음",
        "text": "민지는 바빠서 DC 운용지시를 계속 미루고 있습니다. 가장 먼저 확인할 것은?",
        "options": [
            "사전지정운용방법(디폴트옵션)이 어떻게 설정되어 있는지 확인한다",
            "국민연금 예상수령액만 확인한다",
            "퇴직급여를 지금 현금으로 인출한다",
        ],
        "answer": "사전지정운용방법(디폴트옵션)이 어떻게 설정되어 있는지 확인한다",
        "explain": "디폴트옵션은 장기간 운용지시가 없는 상황을 줄이기 위한 장치입니다.",
    },
    {
        "title": "체크포인트 3 · 이직",
        "text": "5년 뒤 이직합니다. 퇴직급여를 당장 소비하지 않고 노후자금으로 이어서 관리하고 싶습니다.",
        "options": [
            "IRP로 이전하여 이어서 관리한다",
            "생활비 통장에 받아 둔다",
            "연금저축펀드로만 이전해야 한다",
        ],
        "answer": "IRP로 이전하여 이어서 관리한다",
        "explain": "IRP는 이직·퇴직 시 퇴직급여를 이전받아 계속 관리하는 계좌로 활용됩니다.",
    },
    {
        "title": "체크포인트 4 · 개인 노후저축",
        "text": "퇴직급여 이전 목적은 아니고, 장기 ETF 투자에서 위험자산 운용의 자유도가 중요합니다. 무엇을 우선 비교해볼까요?",
        "options": [
            "연금저축펀드의 특성을 우선 비교한다",
            "IRP만 가능하므로 다른 계좌는 볼 필요가 없다",
            "비상자금 통장을 연금계좌로 바꾼다",
        ],
        "answer": "연금저축펀드의 특성을 우선 비교한다",
        "explain": "수업에서 다루는 단순화된 비교에서 연금저축펀드는 위험자산 비중 제한이 없다는 특징이 있습니다.",
    },
    {
        "title": "체크포인트 5 · 갑자기 필요한 돈",
        "text": "1년 안에 이사비로 사용할 가능성이 큰 500만원이 생겼습니다. 세액공제만 보고 전부 연금계좌에 넣을까요?",
        "options": [
            "전부 IRP에 넣는다",
            "전부 연금저축에 넣는다",
            "연금계좌와 분리해 필요한 유동성을 확보한다",
        ],
        "answer": "연금계좌와 분리해 필요한 유동성을 확보한다",
        "explain": "가까운 시일 안에 쓸 가능성이 큰 비상자금은 세제혜택만 보고 장기 연금계좌에 묶지 않는 판단이 중요합니다.",
    },
]

# 로그인
if "role" not in st.session_state:
    st.title("🏗️ Pension Architect")
    st.caption("5주차 · 첫 직장부터 은퇴까지 퇴직연금과 개인연금의 구조를 연결합니다.")
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

if role == "student":
    me = st.session_state.name
    if st.button("🔄 화면 새로고침", type="primary", use_container_width=True):
        st.rerun()
    st.caption(f"현재 단계: {phase}")

    if phase in ("대기", "학생입장"):
        st.info("접속되었습니다. 교수님이 다음 활동을 열 때까지 기다려주세요.")
        st.stop()

    if phase == "DB·DC 구조 탐정":
        st.subheader("1. DB·DC 구조 탐정 · 누가 무엇을 책임질까?")
        st.write("아래 6개 카드를 **DB형** 또는 **DC형**으로 분류하세요.")
        old = my_response(my_class, me, "dbdc_detective")
        if old:
            p = old["payload"]
            st.success(f"6개 카드 중 **{p['score']}개** 정확하게 분류했습니다.")
            rows = []
            for i, (text, correct) in enumerate(DBDC_CARDS):
                mine = p["answers"][i]
                rows.append({"카드": text, "내 분류": mine, "정답": correct, "결과": "O" if mine == correct else "X"})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.info("핵심: **DB는 받을 급여(Benefit)가 정해진 구조**, **DC는 회사가 낼 부담금(Contribution)이 정해지고 근로자가 운용하는 구조**입니다.")
        else:
            with st.form("dbdc_form"):
                answers = []
                for i, (text, _) in enumerate(DBDC_CARDS):
                    answers.append(st.radio(text, ["DB", "DC"], index=None, horizontal=True, key=f"dbdc_{i}"))
                submitted = st.form_submit_button("🔎 분류 제출", type="primary")
                if submitted:
                    if any(a is None for a in answers):
                        st.warning("6개 카드를 모두 분류해주세요.")
                    else:
                        correctness = [answers[i] == DBDC_CARDS[i][1] for i in range(len(DBDC_CARDS))]
                        save_response(my_class, me, "dbdc_detective", {"answers": answers, "correctness": correctness, "score": sum(correctness)})
                        st.rerun()

    elif phase == "DC 방치주의보":
        st.subheader("2. DC 방치주의보 · 3개의 경고등을 꺼라")
        st.write("DC형은 회사가 부담금을 넣어주는 것으로 끝나지 않습니다. 세 개의 상황에서 적절한 판단을 해보세요.")
        old = my_response(my_class, me, "dc_warning")
        if old:
            p = old["payload"]
            st.success(f"경고등 **{p['score']} / 3개**를 껐습니다.")
            for i, item in enumerate(DC_WARNINGS):
                mine = p["answers"][i]
                st.markdown(f"#### {item['title']}")
                st.write(item["question"])
                if mine == item["answer"]:
                    st.success(f"내 선택: {mine}")
                else:
                    st.error(f"내 선택: {mine}")
                st.caption(f"정답: {item['answer']}")
            st.info("DC형의 핵심은 **근로자가 운용방법을 선택하고 그 결과에 책임을 진다는 것**입니다. 디폴트옵션은 장기간 운용지시가 없는 상황을 줄이기 위한 장치입니다.")
        else:
            with st.form("dc_warning_form"):
                answers = []
                for i, item in enumerate(DC_WARNINGS):
                    st.markdown(f"### {item['title']}")
                    st.write(item["question"])
                    answers.append(st.radio("선택", item["options"], index=None, key=f"dc_warning_{i}"))
                    st.write("---")
                submitted = st.form_submit_button("🚨 경고등 끄기", type="primary")
                if submitted:
                    if any(a is None for a in answers):
                        st.warning("세 상황에 모두 답해주세요.")
                    else:
                        correctness = [answers[i] == DC_WARNINGS[i]["answer"] for i in range(len(DC_WARNINGS))]
                        save_response(my_class, me, "dc_warning", {"answers": answers, "correctness": correctness, "score": sum(correctness)})
                        st.rerun()

    elif phase == "TDF 착륙작전":
        st.subheader("3. TDF 착륙작전 · 내 글라이드패스가 은퇴자산에 미치는 영향")
        st.caption(
            "실제 TDF의 위험자산 비중과 글라이드패스는 상품마다 다릅니다. "
            "이 활동은 원리를 비교하기 위한 **수업용 가상 시뮬레이션**입니다."
        )

        st.info(
            "세 시점의 위험자산 비중을 직접 정해보세요. "
            "먼저 **예상 은퇴자산**을 확인한 뒤, 같은 선택이 은퇴 직전 **시장 충격**을 만났을 때 "
            "어떤 차이가 생기는지 확인합니다."
        )

        assumption_df = pd.DataFrame([
            {"수업용 가정": "은퇴 30년 전 시작자산", "값": "1억원"},
            {"수업용 가정": "위험자산 연 기대수익률", "값": "7%"},
            {"수업용 가정": "안정자산 연 기대수익률", "값": "3%"},
        ])
        st.dataframe(assumption_df, use_container_width=True, hide_index=True)

        old = my_response(my_class, me, "tdf_landing")

        if not old:
            with st.form("tdf_landing_form"):
                st.markdown("#### Round 1 · 은퇴 30년 전")
                r30 = st.slider("위험자산 비중(%)", 0, 100, 50, step=5, key="tdf_r30")

                st.markdown("#### Round 2 · 은퇴 10년 전")
                r10 = st.slider("위험자산 비중(%)", 0, 100, 50, step=5, key="tdf_r10")

                st.markdown("#### Round 3 · 은퇴 2년 전")
                r2 = st.slider("위험자산 비중(%)", 0, 100, 50, step=5, key="tdf_r2")

                submitted = st.form_submit_button("📈 예상 은퇴자산 확인", type="primary")
                if submitted:
                    def port_rate(w):
                        return (w / 100) * 0.07 + ((100 - w) / 100) * 0.03

                    start_asset = 100_000_000
                    rate30 = port_rate(r30)
                    rate10 = port_rate(r10)
                    rate2 = port_rate(r2)

                    asset_10 = start_asset * ((1 + rate30) ** 20)
                    asset_2 = asset_10 * ((1 + rate10) ** 8)
                    retirement_asset = asset_2 * ((1 + rate2) ** 2)

                    shock_return = (r2 / 100) * (-0.30) + ((100 - r2) / 100) * 0.02
                    after_shock_asset_2 = asset_2 * (1 + shock_return)
                    retirement_after_shock = after_shock_asset_2 * ((1 + rate2) ** 2)
                    shock_loss = retirement_asset - retirement_after_shock

                    save_response(my_class, me, "tdf_landing", {
                        "r30": r30,
                        "r10": r10,
                        "r2": r2,
                        "rate30": round(rate30 * 100, 4),
                        "rate10": round(rate10 * 100, 4),
                        "rate2": round(rate2 * 100, 4),
                        "asset_10": round(asset_10),
                        "asset_2": round(asset_2),
                        "retirement_asset": round(retirement_asset),
                        "glide_direction": r30 >= r10 >= r2,
                        "shock_return": round(shock_return * 100, 4),
                        "after_shock_asset_2": round(after_shock_asset_2),
                        "retirement_after_shock": round(retirement_after_shock),
                        "shock_loss": round(shock_loss),
                        "shock_revealed": False,
                    })
                    st.rerun()

        else:
            p = old["payload"]

            c1, c2, c3 = st.columns(3)
            c1.metric("은퇴 30년 전", f"위험자산 {p['r30']}%")
            c2.metric("은퇴 10년 전", f"위험자산 {p['r10']}%")
            c3.metric("은퇴 2년 전", f"위험자산 {p['r2']}%")

            st.markdown("#### 내 선택에 따른 예상 자산")
            result_df = pd.DataFrame([
                {"시점": "은퇴 10년 전", "예상자산": f"{p['asset_10']/100_000_000:.2f}억원"},
                {"시점": "은퇴 2년 전", "예상자산": f"{p['asset_2']/100_000_000:.2f}억원"},
                {"시점": "은퇴시점", "예상자산": f"{p['retirement_asset']/100_000_000:.2f}억원"},
            ])
            st.dataframe(result_df, use_container_width=True, hide_index=True)

            if p.get("glide_direction"):
                st.success("세 시점에서 위험자산 비중이 단계적으로 낮아지는 글라이드패스를 만들었습니다.")
            else:
                st.warning(
                    "은퇴가 가까워지는 과정에서 위험자산 비중이 다시 높아지는 구간이 있습니다. "
                    "TDF의 글라이드패스 원리와 비교해보세요."
                )

            chart_df = pd.DataFrame(
                {
                    "시점": ["① 30년 전", "② 10년 전", "③ 2년 전"],
                    "위험자산 비중(%)": [p["r30"], p["r10"], p["r2"]],
                }
            ).set_index("시점")
            st.line_chart(chart_df)

            if not p.get("shock_revealed", False):
                st.write("---")
                st.warning("⚡ 이제 은퇴 2년 전에 갑작스러운 시장 충격이 발생합니다.")
                st.caption("수업용 가상 충격: 위험자산 -30% · 안정자산 +2%")
                if st.button("⚡ 시장 충격 확인", type="primary"):
                    p["shock_revealed"] = True
                    save_response(my_class, me, "tdf_landing", p)
                    st.rerun()
            else:
                st.write("---")
                st.markdown("#### ⚡ 시장 충격 결과")
                c1, c2, c3 = st.columns(3)
                c1.metric("충격 시 포트폴리오 수익률", f"{p['shock_return']:.1f}%")
                c2.metric("충격 직후 자산", f"{p['after_shock_asset_2']/100_000_000:.2f}억원")
                c3.metric(
                    "은퇴시점 예상자산 감소",
                    f"{p['shock_loss']/10_000:.0f}만원",
                )
                st.write(
                    f"충격이 없었다면 은퇴시점 예상자산은 **{p['retirement_asset']/100_000_000:.2f}억원**, "
                    f"같은 자산배분에서 충격이 발생하면 **{p['retirement_after_shock']/100_000_000:.2f}억원**입니다."
                )
                st.info(
                    "은퇴가 가까운 시점의 위험자산 비중이 높을수록 같은 시장 충격이 "
                    "은퇴자산에 더 크게 전달될 수 있습니다."
                )

    elif phase == "연금저축 vs IRP":
        st.subheader("4. 연금저축 vs IRP · 세 상황에 더 잘 맞는 선택은?")
        st.caption("수업에서 다루는 핵심 차이를 이해하기 위한 단순화된 가상 상황입니다.")
        old = my_response(my_class, me, "account_choice")
        if old:
            p = old["payload"]
            st.success(f"세 상황 중 **{p['score']}개**를 핵심 특성에 맞게 판단했습니다.")
            for i, item in enumerate(ACCOUNT_CASES):
                st.markdown(f"#### {item['title']}")
                st.write(item["text"])
                st.write(f"내 선택: **{p['answers'][i]}**")
                st.caption(f"핵심 판단: {item['answer']} · {item['explain']}")
        else:
            with st.form("account_choice_form"):
                answers = []
                for i, item in enumerate(ACCOUNT_CASES):
                    st.markdown(f"### {item['title']}")
                    st.write(item["text"])
                    answers.append(st.radio("선택", item["options"], index=None, horizontal=True, key=f"account_case_{i}"))
                    st.write("---")
                submitted = st.form_submit_button("🧭 세 상황 판단", type="primary")
                if submitted:
                    if any(a is None for a in answers):
                        st.warning("세 상황에 모두 답해주세요.")
                    else:
                        correctness = [answers[i] == ACCOUNT_CASES[i]["answer"] for i in range(len(ACCOUNT_CASES))]
                        save_response(my_class, me, "account_choice", {"answers": answers, "correctness": correctness, "score": sum(correctness)})
                        st.rerun()

    elif phase == "연금계좌 연결 퍼즐":
        st.subheader("5. 연금계좌 연결 퍼즐 · 민지의 연금 경로를 복구하라")
        st.write(
            "단순히 사건의 순서를 맞추는 대신, 첫 직장부터 이직·개인저축까지 이어지는 "
            "**하나의 경로에서 다섯 번의 의사결정**을 내려보세요."
        )

        old = my_response(my_class, me, "flow_puzzle")
        if old:
            p = old["payload"]
            st.success(f"5개의 체크포인트 중 **{p['score']}개**를 적절하게 판단했습니다.")
            for i, item in enumerate(PATH_CASES):
                st.markdown(f"#### {item['title']}")
                st.write(item["text"])
                mine = p["answers"][i]
                if mine == item["answer"]:
                    st.success(f"내 선택: {mine}")
                else:
                    st.error(f"내 선택: {mine}")
                st.caption(f"핵심 판단: {item['answer']} · {item['explain']}")
            st.info(
                "핵심: 퇴직연금과 개인연금은 각각 따로 외우는 상품이 아니라, "
                "취업·운용·이직·추가저축·유동성 관리가 연결된 하나의 장기 의사결정 구조입니다."
            )
        else:
            with st.form("flow_puzzle_form"):
                answers = []
                for i, item in enumerate(PATH_CASES):
                    st.markdown(f"### {item['title']}")
                    st.write(item["text"])
                    answers.append(
                        st.radio(
                            "민지의 선택",
                            item["options"],
                            index=None,
                            key=f"path_case_{i}",
                        )
                    )
                    st.write("---")

                submitted = st.form_submit_button("🧩 연금 경로 완성", type="primary")
                if submitted:
                    if any(a is None for a in answers):
                        st.warning("다섯 체크포인트에 모두 답해주세요.")
                    else:
                        correctness = [
                            answers[i] == PATH_CASES[i]["answer"]
                            for i in range(len(PATH_CASES))
                        ]
                        save_response(my_class, me, "flow_puzzle", {
                            "answers": answers,
                            "correctness": correctness,
                            "score": sum(correctness),
                        })
                        st.rerun()

    elif phase == "결과":
        st.subheader("6. 나의 Pension Architect 기록")
        stages = [("DB·DC", "dbdc_detective"), ("DC관리", "dc_warning"), ("TDF", "tdf_landing"), ("계좌선택", "account_choice"), ("연결퍼즐", "flow_puzzle")]
        cols = st.columns(5)
        for col, (label, key) in zip(cols, stages):
            col.metric(label, "완료" if my_response(my_class, me, key) else "미완료")

    elif phase == "종료":
        st.success("5주차 Pension Architect가 종료되었습니다.")

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

    def professor_reveal(label: str):
        key = f"prof_reveal_{my_class}_{phase}_{label}"
        if not st.session_state.get(key, False):
            if st.button("🔐 정답·해설 보기", key=f"show_{key}"):
                st.session_state[key] = True
                st.rerun()
            return False
        else:
            if st.button("🙈 정답·해설 숨기기", key=f"hide_{key}"):
                st.session_state[key] = False
                st.rerun()
            return True

    if phase == "DB·DC 구조 탐정":
        df = all_responses(my_class, "dbdc_detective")
        st.subheader("DB·DC 구조 탐정 결과")

        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for i, (text, correct) in enumerate(DBDC_CARDS):
                total = correct_count = 0
                for _, r in df.iterrows():
                    answers = (r["payload"] or {}).get("answers", [])
                    if len(answers) > i:
                        total += 1
                        if answers[i] == correct:
                            correct_count += 1
                rows.append({
                    "카드": text,
                    "정답률(%)": round(correct_count / total * 100, 1) if total else 0,
                })
            st.markdown("#### 카드별 응답 결과")
            st.dataframe(pd.DataFrame(rows).sort_values("정답률(%)"), use_container_width=True, hide_index=True)

        if professor_reveal("dbdc"):
            st.markdown("#### 교수용 정답")
            st.dataframe(
                pd.DataFrame([{"카드": text, "정답": correct} for text, correct in DBDC_CARDS]),
                use_container_width=True,
                hide_index=True,
            )
            st.info(
                "핵심: DB는 받을 급여(Benefit)가 정해진 구조이고, "
                "DC는 회사가 낼 부담금(Contribution)이 정해지며 근로자가 운용하는 구조입니다."
            )

    elif phase == "DC 방치주의보":
        df = all_responses(my_class, "dc_warning")
        st.subheader("DC 방치주의보 결과")

        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for i, item in enumerate(DC_WARNINGS):
                total = correct_count = 0
                counts = {}
                for _, r in df.iterrows():
                    answers = (r["payload"] or {}).get("answers", [])
                    if len(answers) > i:
                        total += 1
                        ans = answers[i]
                        counts[ans] = counts.get(ans, 0) + 1
                        if ans == item["answer"]:
                            correct_count += 1
                rows.append({
                    "경고등": i + 1,
                    "정답률(%)": round(correct_count / total * 100, 1) if total else 0,
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        if professor_reveal("dc_warning"):
            st.markdown("#### 교수용 정답·핵심")
            for item in DC_WARNINGS:
                st.markdown(f"**{item['title']} — 정답:** {item['answer']}")
            st.info(
                "DC형은 근로자가 운용방법을 선택하고 그 결과에 책임을 집니다. "
                "디폴트옵션은 장기간 운용지시가 없는 상황을 줄이기 위한 장치입니다."
            )

    elif phase == "TDF 착륙작전":
        df = all_responses(my_class, "tdf_landing")
        st.subheader("TDF 착륙작전 결과")
        st.caption(
            "수업용 가정: 시작자산 1억원 · 위험자산 기대수익률 7% · 안정자산 기대수익률 3% · "
            "시장충격은 위험자산 -30%, 안정자산 +2%."
        )

        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for _, r in df.iterrows():
                p = r["payload"] or {}
                # 구버전 테스트 데이터가 남아 있어도 가능한 범위에서 계산
                r30 = p.get("r30", 0)
                r10 = p.get("r10", 0)
                r2 = p.get("r2", 0)

                def port_rate(w):
                    return (w / 100) * 0.07 + ((100 - w) / 100) * 0.03

                start_asset = 100_000_000
                asset_10 = p.get("asset_10", start_asset * ((1 + port_rate(r30)) ** 20))
                asset_2 = p.get("asset_2", asset_10 * ((1 + port_rate(r10)) ** 8))
                retirement_asset = p.get("retirement_asset", asset_2 * ((1 + port_rate(r2)) ** 2))
                shock_return = p.get("shock_return", ((r2 / 100) * (-0.30) + ((100-r2)/100) * 0.02) * 100)
                after_shock_asset_2 = p.get("after_shock_asset_2", asset_2 * (1 + shock_return/100))
                retirement_after_shock = p.get("retirement_after_shock", after_shock_asset_2 * ((1 + port_rate(r2)) ** 2))
                shock_loss = p.get("shock_loss", retirement_asset - retirement_after_shock)

                rows.append({
                    "이름": r["name"],
                    "30년 전 위험자산(%)": r30,
                    "10년 전 위험자산(%)": r10,
                    "2년 전 위험자산(%)": r2,
                    "예상 은퇴자산(억원)": round(retirement_asset / 100_000_000, 2),
                    "충격수익률(%)": round(shock_return, 1),
                    "충격 후 은퇴자산(억원)": round(retirement_after_shock / 100_000_000, 2),
                    "충격으로 감소(만원)": round(shock_loss / 10_000),
                })

            result = pd.DataFrame(rows)
            st.markdown("#### 학생들이 선택한 평균 위험자산 비중")
            avg_df = pd.DataFrame({
                "시점": ["① 30년 전", "② 10년 전", "③ 2년 전"],
                "평균 위험자산 비중(%)": [
                    result["30년 전 위험자산(%)"].mean(),
                    result["10년 전 위험자산(%)"].mean(),
                    result["2년 전 위험자산(%)"].mean(),
                ]
            }).set_index("시점")
            st.bar_chart(avg_df)

            avg_cols = st.columns(3)
            avg_cols[0].metric("30년 전 평균", f"{result['30년 전 위험자산(%)'].mean():.1f}%")
            avg_cols[1].metric("10년 전 평균", f"{result['10년 전 위험자산(%)'].mean():.1f}%")
            avg_cols[2].metric("2년 전 평균", f"{result['2년 전 위험자산(%)'].mean():.1f}%")

            st.markdown("#### 학생별 시장 충격 영향")
            shock_view = result.sort_values(
                ["충격수익률(%)", "2년 전 위험자산(%)"],
                ascending=[True, False],
            )
            st.dataframe(shock_view, use_container_width=True, hide_index=True)

            shock_chart = shock_view[["이름", "충격수익률(%)"]].set_index("이름")
            st.bar_chart(shock_chart)
            st.caption(
                "은퇴 2년 전 위험자산 비중이 높은 학생일수록 동일한 가상 시장충격에서 "
                "포트폴리오 수익률이 더 크게 악화되는 모습을 함께 비교할 수 있습니다."
            )

    elif phase == "연금저축 vs IRP":
        df = all_responses(my_class, "account_choice")
        st.subheader("연금저축 vs IRP 선택실험 결과")

        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            for i, item in enumerate(ACCOUNT_CASES):
                counts = {}
                for _, r in df.iterrows():
                    answers = (r["payload"] or {}).get("answers", [])
                    if len(answers) > i:
                        ans = answers[i]
                        counts[ans] = counts.get(ans, 0) + 1
                st.markdown(f"#### {item['title']} 선택 분포")
                st.bar_chart(pd.Series(counts, name="학생 수"))

        if professor_reveal("account_choice"):
            st.markdown("#### 교수용 정답·해설")
            for item in ACCOUNT_CASES:
                st.markdown(f"**{item['title']} — 핵심 판단: {item['answer']}**")
                st.caption(item["explain"])

    elif phase == "연금계좌 연결 퍼즐":
        df = all_responses(my_class, "flow_puzzle")
        st.subheader("연금계좌 연결 퍼즐 · 민지의 연금 경로 복구 결과")

        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for i, item in enumerate(PATH_CASES):
                total = correct_count = 0
                for _, r in df.iterrows():
                    answers = (r["payload"] or {}).get("answers", [])
                    if len(answers) > i:
                        total += 1
                        if answers[i] == item["answer"]:
                            correct_count += 1
                rows.append({
                    "체크포인트": i + 1,
                    "주제": item["title"].split("·", 1)[-1].strip(),
                    "정답률(%)": round(correct_count / total * 100, 1) if total else 0,
                })
            st.markdown("#### 체크포인트별 결과")
            st.dataframe(
                pd.DataFrame(rows).sort_values("정답률(%)"),
                use_container_width=True,
                hide_index=True,
            )

        if professor_reveal("flow_puzzle"):
            st.markdown("#### 교수용 정답·해설")
            for item in PATH_CASES:
                st.markdown(f"**{item['title']} — 핵심 판단:** {item['answer']}")
                st.caption(item["explain"])

    elif phase == "결과":
        stages = [
            ("DB·DC", "dbdc_detective"),
            ("DC관리", "dc_warning"),
            ("TDF", "tdf_landing"),
            ("계좌선택", "account_choice"),
            ("연결퍼즐", "flow_puzzle"),
        ]
        rows = [{"활동": label, "제출 인원": len(all_responses(my_class, key))} for label, key in stages]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with st.expander("⚠️ 데이터 관리"):
        if st.button("이 분반 5주차 응답 삭제"):
            supabase.table(T_RESPONSES).delete().eq("class_name", my_class).execute()
            st.rerun()

        if st.button("이 분반 5주차 전체 초기화"):
            supabase.table(T_RESPONSES).delete().eq("class_name", my_class).execute()
            supabase.table(T_STUDENTS).delete().eq("class_name", my_class).execute()
            set_phase(my_class, "대기")
            st.rerun()
