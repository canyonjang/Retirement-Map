import json
from collections import Counter

import pandas as pd
import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title="Retirement Map · 2주차", page_icon="🗺️", layout="wide")

CLASSES = ["인하대", "숙대1", "숙대2"]
PHASES = ["대기", "학생입장", "라이프맵", "100포인트", "연금공백", "결과", "종료"]

T_STATUS = "retire_w2_status"
T_STUDENTS = "retire_w2_students"
T_RESPONSES = "retire_w2_responses"

DOMAINS = ["재무", "건강", "활동·여가", "관계"]
ACTIVITIES = [
    "여행·취미", "운동·건강관리", "가족·친구 관계", "봉사·사회참여",
    "가교직업·소일거리", "정적인 취미", "의료·건강관리 강화", "돌봄·간병 준비",
    "상속·유언·웰다잉 준비"
]

INCOME_SOURCES = {
    "53~54세": [
        "가교직업·근로소득",
        "비상예비자금·금융자산 인출",
        "기타 소득원",
    ],
    "55~64세": [
        "가교직업·근로소득",
        "퇴직연금(연금수령 요건 충족 가정)",
        "개인연금(상품별 수급요건 충족 가정)",
        "비상예비자금·금융자산 인출",
        "기타 소득원",
    ],
    "65세 이후": [
        "국민연금 등 공적연금",
        "퇴직연금",
        "개인연금",
        "주택연금·농지연금(가입요건 충족 시)",
        "근로·사업소득",
        "금융자산 인출",
        "기타 소득원",
    ],
}


@st.cache_resource
def init_connection() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


supabase: Client = init_connection()
PROF_PASSWORD = st.secrets.get("PROF_PASSWORD", "")


def get_status(class_name: str) -> dict:
    rows = supabase.table(T_STATUS).select("*").eq("class_name", class_name).execute().data
    if not rows:
        supabase.table(T_STATUS).insert(
            {"class_name": class_name, "phase": "대기"}
        ).execute()
        return {"class_name": class_name, "phase": "대기"}
    return rows[0]


def set_phase(class_name: str, phase: str):
    supabase.table(T_STATUS).upsert(
        {"class_name": class_name, "phase": phase},
        on_conflict="class_name"
    ).execute()


def save_response(class_name: str, name: str, stage: str, payload: dict):
    supabase.table(T_RESPONSES).upsert(
        {
            "class_name": class_name,
            "name": name,
            "stage": stage,
            "payload": payload,
        },
        on_conflict="class_name,name,stage"
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


def add_student(class_name: str, name: str):
    supabase.table(T_STUDENTS).upsert(
        {"class_name": class_name, "name": name},
        on_conflict="class_name,name"
    ).execute()


def active_classes():
    rows = supabase.table(T_STATUS).select("*").execute().data
    return [r["class_name"] for r in rows if r.get("phase") not in ("대기", "종료")]


def render_header(class_name, role):
    c1, c2 = st.columns([8, 2])
    with c1:
        st.title("🗺️ Retirement Map")
        st.caption(f"은퇴와 상속설계 · 2주차 · {class_name} · {role}")
    with c2:
        if st.button("로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()


# ---------------- 로그인 ----------------
if "role" not in st.session_state:
    st.title("🗺️ Retirement Map")
    st.caption("2주차 · 은퇴생활을 '돈'이 아니라 '삶과 현금흐름의 구조'로 그려보는 앱")
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
            elif len(active) > 1:
                st.session_state["pending_name"] = name.strip()
                st.session_state["choose_class"] = True
                st.rerun()
            else:
                st.error("현재 열려 있는 강의실이 없습니다.")
                st.stop()

            add_student(cn, name.strip())
            st.session_state.update(role="student", name=name.strip(), class_name=cn)
            st.rerun()

        if st.session_state.get("choose_class"):
            cn = st.selectbox("열려 있는 분반을 선택하세요", active_classes())
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
                st.error("비밀번호가 틀렸거나 secrets에 PROF_PASSWORD가 설정되지 않았습니다.")
    st.stop()


my_class = st.session_state.class_name
role = st.session_state.role
status = get_status(my_class)
phase = status.get("phase", "대기")
render_header(my_class, "학생" if role == "student" else "교수")
st.write("---")


# ---------------- 학생 ----------------
if role == "student":
    me = st.session_state.name

    if st.button("🔄 화면 새로고침", type="primary", use_container_width=True):
        st.rerun()
    st.caption(f"현재 단계: {phase}")

    if phase in ("대기", "학생입장"):
        st.info("접속되었습니다. 교수님이 다음 단계를 열 때까지 기다려주세요.")
        st.stop()

    if phase == "라이프맵":
        st.subheader("1. 나의 은퇴 30년 라이프맵")
        st.write(
            "아래 세 시기는 **개념을 체험하기 위한 예시 구간**입니다. 실제 노화와 은퇴생활은 개인차가 큽니다. "
            "각 시기에 내가 중요하게 생각할 활동을 2~3개 골라보세요."
        )
        prev = my_response(my_class, me, "life_map")
        prev_payload = (prev or {}).get("payload") or {}
        selections = {}
        age_bands = ["65~74세", "75~84세", "85세 이후"]
        for band in age_bands:
            default = prev_payload.get(band, [])
            selections[band] = st.multiselect(
                f"{band}",
                ACTIVITIES,
                default=[x for x in default if x in ACTIVITIES],
                max_selections=3,
                key=f"life_{band}"
            )

        if st.button("라이프맵 저장", type="primary"):
            save_response(my_class, me, "life_map", selections)
            st.success("저장했습니다. 교수님 화면에서 반 전체 패턴을 함께 볼 수 있습니다.")

    elif phase == "100포인트":
        st.subheader("2. 은퇴준비 100포인트")
        st.write(
            "은퇴준비 자원 100을 **재무·건강·활동·관계**에 배분해보세요. "
            "정답은 없습니다. 세 시기에 내 우선순위가 어떻게 달라지는지를 보는 활동입니다."
        )
        prev = my_response(my_class, me, "points")
        old = (prev or {}).get("payload") or {}
        payload = {}
        valid = True

        for band in ["65~74세", "75~84세", "85세 이후"]:
            st.markdown(f"#### {band}")
            defaults = old.get(band, {"재무": 25, "건강": 25, "활동·여가": 25, "관계": 25})
            cols = st.columns(4)
            vals = {}
            for i, domain in enumerate(DOMAINS):
                vals[domain] = cols[i].number_input(
                    domain, min_value=0, max_value=100,
                    value=int(defaults.get(domain, 25)), step=5,
                    key=f"pt_{band}_{domain}"
                )
            total = sum(vals.values())
            payload[band] = vals
            if total != 100:
                valid = False
                st.warning(f"{band}: 현재 합계 {total}점입니다. 100점이 되도록 조정하세요.")
            else:
                st.success(f"{band}: 100점")

        if st.button("100포인트 저장", type="primary", disabled=not valid):
            save_response(my_class, me, "points", payload)
            st.success("저장했습니다.")

    elif phase == "연금공백":
        st.subheader("3. 53세 퇴직자의 '소득 타임라인' 메우기")
        st.write(
            "가정: 주된 일자리는 53세에 끝났고, 국민연금 노령연금은 65세부터 받을 수 있습니다. "
            "각 구간에서 **생활비를 충당할 소득원을 하나 이상** 선택하세요."
        )
        st.caption(
            "※ 퇴직연금·개인연금·주택연금·농지연금은 실제 가입 및 수급요건이 서로 다릅니다. "
            "여기서는 '소득원을 시간축에 연결하는 사고'만 연습합니다."
        )

        prev = my_response(my_class, me, "income_timeline")
        old = (prev or {}).get("payload") or {}
        picks = {}
        for band, options in INCOME_SOURCES.items():
            picks[band] = st.multiselect(
                band, options,
                default=[x for x in old.get(band, []) if x in options],
                key=f"income_{band}"
            )

        gaps = [band for band, vals in picks.items() if not vals]
        if gaps:
            st.error("소득원이 비어 있는 구간: " + ", ".join(gaps))
        else:
            st.success("세 구간 모두 최소 하나의 소득원이 연결되었습니다.")

        if st.button("소득 타임라인 저장", type="primary", disabled=bool(gaps)):
            save_response(my_class, me, "income_timeline", picks)
            st.success("저장했습니다.")

    elif phase == "결과":
        st.subheader("4. 나의 2주차 지도")
        life = my_response(my_class, me, "life_map")
        pts = my_response(my_class, me, "points")
        inc = my_response(my_class, me, "income_timeline")

        c1, c2, c3 = st.columns(3)
        c1.metric("라이프맵", "완료" if life else "미완료")
        c2.metric("100포인트", "완료" if pts else "미완료")
        c3.metric("소득 타임라인", "완료" if inc else "미완료")

        if inc:
            st.markdown("#### 내가 만든 소득 타임라인")
            for band, vals in inc["payload"].items():
                st.write(f"**{band}** → " + " · ".join(vals))

        st.info(
            "이번 주의 결론은 '얼마를 모을까?'가 아니라 "
            "**은퇴생활의 단계·비재무 영역·소득원의 시간 구조를 먼저 그려보는 것**입니다."
        )

    elif phase == "종료":
        st.success("2주차 Retirement Map 활동이 종료되었습니다.")


# ---------------- 교수 ----------------
else:
    ctl = st.columns([3, 3, 2])
    new_phase = ctl[0].selectbox("진행 단계", PHASES, index=PHASES.index(phase))
    if ctl[1].button("✅ 이 단계로 전환", type="primary", use_container_width=True):
        set_phase(my_class, new_phase)
        st.rerun()
    if ctl[2].button("🔄 새로고침", use_container_width=True):
        st.rerun()

    student_rows = supabase.table(T_STUDENTS).select("*").eq("class_name", my_class).execute().data
    st.metric("접속 학생", f"{len(student_rows)}명")
    st.write("---")

    if phase == "라이프맵":
        df = all_responses(my_class, "life_map")
        st.subheader("반 전체 라이프맵")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            for band in ["65~74세", "75~84세", "85세 이후"]:
                counter = Counter()
                for p in df["payload"]:
                    for x in (p or {}).get(band, []):
                        counter[x] += 1
                st.markdown(f"#### {band}")
                if counter:
                    out = pd.DataFrame(counter.most_common(), columns=["활동", "선택 인원"])
                    st.bar_chart(out.set_index("활동"))
                else:
                    st.write("응답 없음")

    elif phase == "100포인트":
        df = all_responses(my_class, "points")
        st.subheader("반 평균 100포인트")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            rows = []
            for _, r in df.iterrows():
                p = r["payload"] or {}
                for band, vals in p.items():
                    row = {"이름": r["name"], "시기": band}
                    row.update(vals)
                    rows.append(row)
            long_df = pd.DataFrame(rows)
            for band in ["65~74세", "75~84세", "85세 이후"]:
                sub = long_df[long_df["시기"] == band]
                if not sub.empty:
                    avg = sub[DOMAINS].mean().round(1)
                    st.markdown(f"#### {band}")
                    st.bar_chart(pd.DataFrame({"평균점수": avg}))

    elif phase == "연금공백":
        df = all_responses(my_class, "income_timeline")
        st.subheader("반 전체 소득 타임라인")
        if df.empty:
            st.info("아직 제출이 없습니다.")
        else:
            for band in ["53~54세", "55~64세", "65세 이후"]:
                counter = Counter()
                for p in df["payload"]:
                    for x in (p or {}).get(band, []):
                        counter[x] += 1
                st.markdown(f"#### {band}")
                if counter:
                    out = pd.DataFrame(counter.most_common(), columns=["소득원", "선택 인원"])
                    st.bar_chart(out.set_index("소득원"))

    elif phase == "결과":
        st.subheader("2주차 마무리")
        counts = {}
        for stage in ["life_map", "points", "income_timeline"]:
            counts[stage] = len(all_responses(my_class, stage))
        st.dataframe(
            pd.DataFrame(
                [
                    {"활동": "라이프맵", "제출": counts["life_map"]},
                    {"활동": "100포인트", "제출": counts["points"]},
                    {"활동": "소득 타임라인", "제출": counts["income_timeline"]},
                ]
            ),
            use_container_width=True,
            hide_index=True
        )
        st.info(
            "교수용 마무리 질문: '우리 반이 가장 중요하게 본 은퇴 영역은 나이에 따라 어떻게 바뀌었는가?' "
            "'53~65세 사이의 현금흐름을 어떤 소득원으로 메우려 했는가?'"
        )

    with st.expander("⚠️ 데이터 관리"):
        if st.button("이 분반 2주차 응답 삭제"):
            supabase.table(T_RESPONSES).delete().eq("class_name", my_class).execute()
            st.rerun()
        if st.button("이 분반 전체 초기화"):
            supabase.table(T_RESPONSES).delete().eq("class_name", my_class).execute()
            supabase.table(T_STUDENTS).delete().eq("class_name", my_class).execute()
            set_phase(my_class, "대기")
            st.rerun()
