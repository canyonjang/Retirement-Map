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

FLOW_ORDER = [
    "첫 직장에 취업한다",
    "회사의 퇴직연금(DB 또는 DC)이 시작된다",
    "DC형이라면 적립금 운용방법을 직접 선택·관리한다",
    "이직 또는 퇴직을 한다",
    "퇴직급여를 IRP로 이전하여 이어서 관리한다",
    "은퇴 후 퇴직연금·개인연금을 노후소득으로 활용한다",
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
        st.subheader("3. TDF 착륙작전 · 성장기회는 살리고, 은퇴 직전 충격은 줄여라")
        st.caption("아래 비율은 실제 특정 TDF가 아니라 수업용 가상 글라이드패스입니다.")
        st.info(
            "미션: 세 시점의 위험자산 비중을 정하세요. **적정 범위 안에서 시간이 갈수록 위험자산을 줄이고**, "
            "은퇴 2년 전 가상 시장충격의 손실을 **10% 이내**로 막으면서 "
            "**성장점수(세 시점 위험자산 비중의 합)를 최대한 높여보세요.**"
        )
        st.write("수업용 적정 범위: **30년 전 70~90% · 10년 전 40~60% · 2년 전 20~40%**")
        st.caption("가상 시장충격: 위험자산 -30%, 안정자산 +2%")

        old = my_response(my_class, me, "tdf_landing")
        if old:
            p = old["payload"]
            if p["landing_success"]:
                st.success(f"✅ 안전 착륙 성공 · 성장점수 **{p['growth_score']} / 185**")
            else:
                st.warning(f"착륙 조건을 모두 충족하지 못했습니다 · 성장점수 {p['growth_score']}")
            c1, c2, c3 = st.columns(3)
            c1.metric("은퇴 30년 전", f"위험자산 {p['r30']}%")
            c2.metric("은퇴 10년 전", f"위험자산 {p['r10']}%")
            c3.metric("은퇴 2년 전", f"위험자산 {p['r2']}%")
            st.metric("은퇴 2년 전 가상 충격 시 포트폴리오 수익률", f"{p['shock_return']:.1f}%")
            st.write(
                "착륙 조건:",
                f"{'✅' if p['range_ok'] else '❌'} 시점별 적정범위 · "
                f"{'✅' if p['descending_ok'] else '❌'} 위험자산 감소 · "
                f"{'✅' if p['shock_ok'] else '❌'} 충격 손실 10% 이내",
            )
            st.markdown("#### ✈️ 계획 변경 카드")
            st.write("예상보다 **5년 일찍 은퇴**하게 되었다면 글라이드패스를 어떻게 검토해야 할까요?")
            st.write(f"내 선택: **{p['surprise']}**")
            if p["surprise_correct"]:
                st.success("목표시점이 가까워졌으므로 위험자산을 더 줄이는 방향을 검토하는 판단이 적절합니다.")
            else:
                st.error("목표시점이 가까워졌다면 기존보다 더 보수적인 글라이드패스를 검토할 필요가 있습니다.")
            chart_df = pd.DataFrame({"은퇴까지 남은 기간": ["30년", "10년", "2년"], "위험자산 비중": [p["r30"], p["r10"], p["r2"]]}).set_index("은퇴까지 남은 기간")
            st.line_chart(chart_df)
        else:
            with st.form("tdf_landing_form"):
                c1, c2, c3 = st.columns(3)
                r30 = c1.slider("은퇴 30년 전 위험자산(%)", 0, 100, 80, step=5)
                r10 = c2.slider("은퇴 10년 전 위험자산(%)", 0, 100, 50, step=5)
                r2 = c3.slider("은퇴 2년 전 위험자산(%)", 0, 100, 30, step=5)
                shock_return = (r2 / 100) * (-30) + ((100 - r2) / 100) * 2
                growth_score = r30 + r10 + r2
                range_ok = (70 <= r30 <= 90) and (40 <= r10 <= 60) and (20 <= r2 <= 40)
                descending_ok = r30 > r10 > r2
                shock_ok = shock_return >= -10
                st.metric("현재 성장점수", f"{growth_score}")
                st.metric("은퇴 2년 전 충격 시 가상 수익률", f"{shock_return:.1f}%")
                surprise = st.radio(
                    "계획 변경: 예상보다 5년 일찍 은퇴하게 되었습니다. 무엇을 검토할까요?",
                    ["위험자산 비중을 더 늘린다", "현재 글라이드패스를 그대로 둔다", "위험자산 비중을 더 줄이는 방향을 검토한다"],
                    index=None,
                )
                submitted = st.form_submit_button("🛬 착륙 시도", type="primary")
                if submitted:
                    if surprise is None:
                        st.warning("계획 변경 카드에도 답해주세요.")
                    else:
                        surprise_correct = surprise == "위험자산 비중을 더 줄이는 방향을 검토한다"
                        landing_success = range_ok and descending_ok and shock_ok
                        save_response(my_class, me, "tdf_landing", {
                            "r30": r30, "r10": r10, "r2": r2, "growth_score": growth_score,
                            "shock_return": round(shock_return, 4), "range_ok": range_ok,
                            "descending_ok": descending_ok, "shock_ok": shock_ok,
                            "landing_success": landing_success, "surprise": surprise,
                            "surprise_correct": surprise_correct,
                        })
                        st.rerun()

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
                st.caption(f"수업용 판단: {item['answer']} · {item['explain']}")
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
        st.subheader("5. 연금계좌 연결 퍼즐 · 첫 직장에서 은퇴까지 이어 붙여라")
        st.caption("실제 개인연금 납입 시점은 다양할 수 있으며, 아래는 핵심 흐름을 이해하기 위한 단순화된 순서입니다.")
        old = my_response(my_class, me, "flow_puzzle")
        if old:
            p = old["payload"]
            st.success(f"6단계 중 **{p['score']}개 위치**를 정확하게 연결했습니다.")
            rows = []
            for i, correct in enumerate(FLOW_ORDER):
                mine = p["order"][i]
                rows.append({"단계": i + 1, "내 배열": mine, "정답": correct, "결과": "O" if mine == correct else "X"})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.info("핵심: 퇴직연금은 퇴직할 때 갑자기 생기는 돈이 아니라, 첫 직장부터 운용하고 이직 시 IRP 등으로 이어서 관리하는 장기 은퇴자산입니다.")
        else:
            with st.form("flow_puzzle_form"):
                st.write("아래 6개 사건을 시간 흐름에 맞게 배열하세요.")
                selected_order = []
                for i in range(6):
                    selected_order.append(st.selectbox(f"{i+1}단계", FLOW_ORDER, index=None, placeholder="이 단계에 들어갈 사건 선택", key=f"flow_{i}"))
                submitted = st.form_submit_button("🔗 연결 완료", type="primary")
                if submitted:
                    if any(x is None for x in selected_order):
                        st.warning("6단계를 모두 선택해주세요.")
                    elif len(set(selected_order)) != 6:
                        st.warning("같은 사건을 두 번 사용할 수 없습니다. 6개 사건을 각각 한 번씩 사용해주세요.")
                    else:
                        correctness = [selected_order[i] == FLOW_ORDER[i] for i in range(6)]
                        save_response(my_class, me, "flow_puzzle", {"order": selected_order, "correctness": correctness, "score": sum(correctness)})
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

    if phase == "DB·DC 구조 탐정":
        df = all_responses(my_class, "dbdc_detective")
        st.subheader("DB·DC 구조 탐정 결과")
        st.markdown("#### 교수용 정답")
        st.dataframe(pd.DataFrame([{"카드": text, "정답": correct} for text, correct in DBDC_CARDS]), use_container_width=True, hide_index=True)
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
                rows.append({"카드": text, "정답": correct, "정답률(%)": round(correct_count / total * 100, 1) if total else 0})
            st.markdown("#### 카드별 정답률")
            st.dataframe(pd.DataFrame(rows).sort_values("정답률(%)"), use_container_width=True, hide_index=True)

    elif phase == "DC 방치주의보":
        df = all_responses(my_class, "dc_warning")
        st.subheader("DC 방치주의보 결과")
        st.markdown("#### 교수용 정답·핵심")
        for item in DC_WARNINGS:
            st.markdown(f"**{item['title']} — 정답:** {item['answer']}")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for i, item in enumerate(DC_WARNINGS):
                total = correct_count = 0
                for _, r in df.iterrows():
                    answers = (r["payload"] or {}).get("answers", [])
                    if len(answers) > i:
                        total += 1
                        if answers[i] == item["answer"]:
                            correct_count += 1
                rows.append({"경고등": i + 1, "정답률(%)": round(correct_count / total * 100, 1) if total else 0})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    elif phase == "TDF 착륙작전":
        df = all_responses(my_class, "tdf_landing")
        st.subheader("TDF 착륙작전 결과")
        st.info("수업용 조건: 30년 전 70~90% · 10년 전 40~60% · 2년 전 20~40%, 시간이 갈수록 위험자산 감소, 은퇴 2년 전 가상 충격 손실 10% 이내.")
        st.caption("성장점수는 세 시점 위험자산 비중의 합입니다. 모든 착륙 조건을 지키면서 가능한 최대 성장점수는 185(90+60+35)입니다.")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for _, r in df.iterrows():
                p = r["payload"] or {}
                rows.append({
                    "이름": r["name"], "30년 전": p.get("r30"), "10년 전": p.get("r10"), "2년 전": p.get("r2"),
                    "충격수익률(%)": p.get("shock_return"), "안전착륙": "O" if p.get("landing_success") else "X",
                    "성장점수": p.get("growth_score"), "계획변경 판단": "O" if p.get("surprise_correct") else "X",
                })
            result = pd.DataFrame(rows).sort_values(["안전착륙", "성장점수", "이름"], ascending=[False, False, True])
            st.dataframe(result, use_container_width=True, hide_index=True)
            valid = result[result["안전착륙"] == "O"]
            c1, c2, c3 = st.columns(3)
            c1.metric("안전착륙 성공", f"{len(valid)} / {len(result)}명")
            c2.metric("성공자 최고 성장점수", f"{valid['성장점수'].max():.0f}" if not valid.empty else "-")
            c3.metric("계획변경 정답률", f"{(result['계획변경 판단'] == 'O').mean()*100:.1f}%")
            st.markdown("#### 학급 평균 글라이드패스")
            mean_df = pd.DataFrame({"위험자산 평균": [result["30년 전"].mean(), result["10년 전"].mean(), result["2년 전"].mean()]}, index=["30년 전", "10년 전", "2년 전"])
            st.line_chart(mean_df)

    elif phase == "연금저축 vs IRP":
        df = all_responses(my_class, "account_choice")
        st.subheader("연금저축 vs IRP 선택실험 결과")
        st.markdown("#### 교수용 정답·해설")
        for item in ACCOUNT_CASES:
            st.markdown(f"**{item['title']} — 수업용 판단: {item['answer']}**")
            st.caption(item["explain"])
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

    elif phase == "연금계좌 연결 퍼즐":
        df = all_responses(my_class, "flow_puzzle")
        st.subheader("연금계좌 연결 퍼즐 결과")
        st.markdown("#### 교수용 기준 순서")
        for i, item in enumerate(FLOW_ORDER, start=1):
            st.write(f"{i}. {item}")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for i, correct in enumerate(FLOW_ORDER):
                total = correct_count = 0
                for _, r in df.iterrows():
                    order = (r["payload"] or {}).get("order", [])
                    if len(order) > i:
                        total += 1
                        if order[i] == correct:
                            correct_count += 1
                rows.append({"단계": i + 1, "기준 사건": correct, "정답률(%)": round(correct_count / total * 100, 1) if total else 0})
            st.markdown("#### 가장 많이 헷갈린 연결")
            st.dataframe(pd.DataFrame(rows).sort_values("정답률(%)"), use_container_width=True, hide_index=True)

    elif phase == "결과":
        stages = [("DB·DC", "dbdc_detective"), ("DC관리", "dc_warning"), ("TDF", "tdf_landing"), ("계좌선택", "account_choice"), ("연결퍼즐", "flow_puzzle")]
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
