import html
from statistics import mean

import pandas as pd
from openai import OpenAI
import streamlit as st
from scipy.stats import ttest_rel, spearmanr
from supabase import Client, create_client

st.set_page_config(
    page_title="Future Self Lab · 10·11주차",
    page_icon="🪞",
    layout="wide"
)

# ─────────────────────────────────────────────────────────────
# 기본 설정
# ─────────────────────────────────────────────────────────────
CLASSES = ["인하대", "숙대1", "숙대2"]

PHASES = [
    "대기",
    "학생입장",
    "10주차 · 미래 자아 연속성",
    "10주차 · 불쾌한 액체 마시기",
    "10주차 · 지연보상과 할인율",
    "11주차 · 정신적 시간여행",
    "11주차 · Future You",
    "결과",
    "종료",
]

T_STATUS = "future_self_status"
T_STUDENTS = "future_self_students"
T_RESPONSES = "future_self_responses"


@st.cache_resource
def init_connection() -> Client:
    # Future You에는 개인적인 자유서술 응답이 있으므로
    # Secret key를 Streamlit Secrets에만 저장해 사용합니다.
    key = st.secrets.get("SUPABASE_SERVICE_KEY", "")

    if not key:
        raise RuntimeError(
            "Streamlit Secrets에 SUPABASE_SERVICE_KEY를 설정해주세요."
        )

    return create_client(
        st.secrets["SUPABASE_URL"],
        key
    )


supabase: Client = init_connection()

PROF_PASSWORD = st.secrets.get("PROF_PASSWORD", "")
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
OPENAI_MODEL = st.secrets.get(
    "OPENAI_MODEL",
    "gpt-6.1-sol"
)


# ─────────────────────────────────────────────────────────────
# Supabase helpers
# ─────────────────────────────────────────────────────────────
def get_status(class_name: str) -> dict:
    rows = (
        supabase
        .table(T_STATUS)
        .select("*")
        .eq("class_name", class_name)
        .execute()
        .data
    )

    if not rows:
        supabase.table(T_STATUS).insert(
            {
                "class_name": class_name,
                "phase": "대기"
            }
        ).execute()

        return {
            "class_name": class_name,
            "phase": "대기"
        }

    return rows[0]


def set_phase(class_name: str, phase: str):
    supabase.table(T_STATUS).upsert(
        {
            "class_name": class_name,
            "phase": phase
        },
        on_conflict="class_name"
    ).execute()


def add_student(class_name: str, name: str):
    supabase.table(T_STUDENTS).upsert(
        {
            "class_name": class_name,
            "name": name
        },
        on_conflict="class_name,name"
    ).execute()


def get_student(class_name: str, name: str):
    rows = (
        supabase
        .table(T_STUDENTS)
        .select("*")
        .eq("class_name", class_name)
        .eq("name", name)
        .execute()
        .data
    )

    return rows[0] if rows else None


def active_classes():
    rows = (
        supabase
        .table(T_STATUS)
        .select("*")
        .execute()
        .data
    )

    return [
        r["class_name"]
        for r in rows
        if r.get("phase") not in ("대기", "종료")
    ]


def save_response(
    class_name: str,
    name: str,
    stage: str,
    payload: dict
):
    supabase.table(T_RESPONSES).upsert(
        {
            "class_name": class_name,
            "name": name,
            "stage": stage,
            "payload": payload
        },
        on_conflict="class_name,name,stage"
    ).execute()


def my_response(
    class_name: str,
    name: str,
    stage: str
):
    rows = (
        supabase
        .table(T_RESPONSES)
        .select("*")
        .eq("class_name", class_name)
        .eq("name", name)
        .eq("stage", stage)
        .execute()
        .data
    )

    return rows[0] if rows else None


def all_responses(
    class_name: str,
    stage: str
) -> pd.DataFrame:
    rows = (
        supabase
        .table(T_RESPONSES)
        .select("*")
        .eq("class_name", class_name)
        .eq("stage", stage)
        .execute()
        .data
    )

    return pd.DataFrame(rows)

def fsc_discount_analysis(class_name: str):
    """
    미래 자아 연속성(FSC)과 지연보상 결과를
    같은 학생 이름을 기준으로 연결합니다.
    """

    fsc_df = all_responses(class_name, "fsc")
    discount_df = all_responses(class_name, "discount")

    if fsc_df.empty or discount_df.empty:
        return pd.DataFrame()

    # ── FSC ──────────────────────────────
    fsc_rows = []

    for _, row in fsc_df.iterrows():
        payload = row.get("payload") or {}
        option = payload.get("option")

        if option is not None:
            fsc_rows.append({
                "name": row["name"],
                "fsc": float(option)
            })

    # ── 지연보상 / 할인율 ─────────────────
    discount_rows = []

    for _, row in discount_df.iterrows():
        payload = row.get("payload") or {}

        delayed_count = payload.get("delayed_count")
        delayed_rate = payload.get("delayed_rate")
        k_mid = payload.get("k_mid")

        if delayed_rate is not None:
            discount_rows.append({
                "name": row["name"],
                "delayed_count": delayed_count,
                "delayed_rate": float(delayed_rate),
                "k_mid": float(k_mid) if k_mid is not None else None
            })

    if not fsc_rows or not discount_rows:
        return pd.DataFrame()

    fsc_result = pd.DataFrame(fsc_rows)
    discount_result = pd.DataFrame(discount_rows)

    merged = pd.merge(
        fsc_result,
        discount_result,
        on="name",
        how="inner"
    )

    return merged


def safe_spearman(df, x_col, y_col):
    """
    Spearman 상관계수를 안전하게 계산합니다.
    응답이 너무 적거나 모든 값이 같으면 계산하지 않습니다.
    """

    if df.empty:
        return None, None

    temp = df[[x_col, y_col]].copy()
    temp[x_col] = pd.to_numeric(temp[x_col], errors="coerce")
    temp[y_col] = pd.to_numeric(temp[y_col], errors="coerce")
    temp = temp.dropna()

    if len(temp) < 3:
        return None, None

    if temp[x_col].nunique() < 2 or temp[y_col].nunique() < 2:
        return None, None

    rho, p = spearmanr(temp[x_col], temp[y_col])

    return float(rho), float(p)

def all_students(
    class_name: str
) -> pd.DataFrame:
    rows = (
        supabase
        .table(T_STUDENTS)
        .select("*")
        .eq("class_name", class_name)
        .execute()
        .data
    )

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────
# 10주차 ① 미래 자아 연속성
# 원본 Google Form의 7개 겹침 그림을 단순 SVG로 재현
# ─────────────────────────────────────────────────────────────
def fsc_cards_html():
    # 1: 거의 분리 → 7: 거의 완전 중첩
    dxs = [72, 60, 49, 38, 27, 16, 5]

    cards = []

    for i, dx in enumerate(dxs, 1):
        x1 = 52
        x2 = x1 + dx

        # 옵션 1에만 현재 자아 / 미래 자아 표시
        labels = ""

        if i == 1:
            labels = (
                f'<text x="{x1}" y="37" text-anchor="middle" font-size="9">'
                f'현재 자아</text>'
                f'<text x="{x2}" y="37" text-anchor="middle" font-size="9">'
                f'미래 자아</text>'
            )

        svg = (
            f'<div style="min-width:145px;border:1px solid #ddd;'
            f'border-radius:10px;padding:8px;text-align:center;">'
            f'<div style="font-weight:700;margin-bottom:4px;">옵션 {i}</div>'
            f'<svg width="140" height="82" viewBox="0 0 160 82" '
            f'aria-label="옵션 {i}">'
            f'<circle cx="{x1}" cy="40" r="30" fill="white" '
            f'stroke="#222" stroke-width="2"/>'
            f'<circle cx="{x2}" cy="40" r="30" fill="white" '
            f'fill-opacity="0.55" stroke="#222" stroke-width="2"/>'
            f'{labels}'
            f'</svg>'
            f'</div>'
        )

        cards.append(svg)

    return (
        '<div style="display:flex;gap:8px;flex-wrap:wrap;">'
        + "".join(cards)
        + "</div>"
    )


# ─────────────────────────────────────────────────────────────
# 10주차 ② 불쾌한 액체 마시기
# 원본 분석 엑셀의 1~5점 매핑 그대로 사용
# ─────────────────────────────────────────────────────────────
LIQUID_OPTIONS = [
    "1 티스푼(약 5ml)",
    "1 테이블스푼(약 15ml)",
    "1/4 컵(약 60ml)",
    "1/2 컵(약 120ml)",
    "1 컵(약 240ml)",
]

LIQUID_SCORE = {
    label: i + 1
    for i, label in enumerate(LIQUID_OPTIONS)
}


# ─────────────────────────────────────────────────────────────
# 10주차 ③ 지연보상/할인율
# 원본 분석 엑셀 params 시트와 계산식을 그대로 구현
#
# k = (V-SV)/(SV*D)
# ─────────────────────────────────────────────────────────────
DELAY_QUESTIONS = [

    {
        "immediate":
            "오늘 3,000원 받아서 편의점에서 간식 사먹기",

        "delayed":
            "120일 후 3,300원 받아서 편의점 간식 사먹기",

        "k":
            0.0008333333333333334,
    },

    {
        "immediate":
            "오늘 5,000원 받아서 동네 카페 가기",

        "delayed":
            "30일 후 7,000원 받아서 동네 카페 가기",

        "k":
            0.013333333333333334,
    },

    {
        "immediate":
            "오늘 10,000원 받아서 중식당에서 점심 식사",

        "delayed":
            "45일 후 14,000원 받아서 중식당에서 점심 식사",

        "k":
            0.008888888888888889,
    },

    {
        "immediate":
            "오늘 8,000원 받아서 택시 타기",

        "delayed":
            "7일 후 20,000원 받아서 택시 타기",

        "k":
            0.21428571428571427,
    },

    {
        "immediate":
            "오늘 15,000원 받아서 친구 선물 사기",

        "delayed":
            "14일 후 30,000원 받아서 친구 선물 사기",

        "k":
            0.07142857142857142,
    },

    {
        "immediate":
            "오늘 20,000원 할인 쿠폰 받아 사용하기",

        "delayed":
            "150일 후 22,000원 할인 쿠폰 받아 사용하기",

        "k":
            0.0006666666666666666,
    },

    {
        "immediate":
            "오늘 25,000원 받아서 저녁 데이트 외식하기",

        "delayed":
            "60일 후 40,000원 받아서 저녁 데이트 외식하기",

        "k":
            0.01,
    },

    {
        "immediate":
            "오늘 30,000원 받아서 온라인 쇼핑하기",

        "delayed":
            "5일 후 50,000원 받아서 온라인 쇼핑하기",

        "k":
            0.13333333333333333,
    },

    {
        "immediate":
            "오늘 35,000원 받아서 뮤지컬 티켓 예매",

        "delayed":
            "21일 후 70,000원 받아서 뮤지컬 티켓 예매",

        "k":
            0.047619047619047616,
    },

    {
        "immediate":
            "오늘 50,000원 받아서 숙박 예매하기",

        "delayed":
            "3일 후 85,000원 받아서 숙박 예매하기",

        "k":
            0.23333333333333334,
    },
]


def calc_discount(answers):

    delayed_count = 0

    immediate_ks = []
    delayed_ks = []

    for ans, q in zip(
        answers,
        DELAY_QUESTIONS
    ):

        if ans == q["delayed"]:

            delayed_count += 1
            delayed_ks.append(
                q["k"]
            )

        else:

            immediate_ks.append(
                q["k"]
            )

    # 작년 분석 엑셀의
    # MAX(즉시 선택 k*)
    # MIN(지연 선택 k*)
    # 중간값 계산을 그대로 재현

    k_min = (
        max(immediate_ks)
        if immediate_ks
        else 0.0
    )

    k_max = (
        min(delayed_ks)
        if delayed_ks
        else 0.0
    )

    k_mid = (
        k_min + k_max
    ) / 2

    return {
        "delayed_count":
            delayed_count,

        "delayed_rate":
            delayed_count / 10,

        "k_min":
            k_min,

        "k_max":
            k_max,

        "k_mid":
            k_mid,
    }


# ─────────────────────────────────────────────────────────────
# 11주차 ④ 정신적 시간여행 A/B
#
# A:
# 0 = 미래→현재
# 10 = 현재→미래
#
# B:
# 0 = 현재→미래
# 10 = 미래→현재
#
# 작년 분석 엑셀처럼
# B 응답은 10-원응답으로 변환하여 합산
# ─────────────────────────────────────────────────────────────
def time_group(
    class_name: str,
    name: str
):

    student = get_student(
        class_name,
        name
    )

    if not student:

        add_student(
            class_name,
            name
        )

        student = get_student(
            class_name,
            name
        )

    # 입장 순서에 따라 자동 교차 배정
    # 두 집단 크기를 거의 같게 유지

    return (
        "A"
        if int(student["id"]) % 2 == 1
        else "B"
    )


def aligned_time_score(
    group: str,
    raw: int
):

    return (
        raw
        if group == "A"
        else 10 - raw
    )


# ─────────────────────────────────────────────────────────────
# 11주차 ⑤ Future You
#
# 작년 Apps Script의 생성 프롬프트와
# 학생용 chatStarter를 그대로 구현
#
# 생성 엔진만
# OpenAI Responses API로 교체
# ─────────────────────────────────────────────────────────────
@st.cache_resource
def init_openai_client() -> OpenAI:

    if not OPENAI_API_KEY:

        raise RuntimeError(
            "Streamlit Secrets에 "
            "OPENAI_API_KEY를 설정해주세요."
        )

    return OpenAI(
        api_key=OPENAI_API_KEY
    )


def call_openai(
    prompt: str
) -> str:

    client = init_openai_client()

    try:

        response = client.responses.create(
            model=OPENAI_MODEL,
            reasoning={
                "effort": "low"
            },
            input=prompt.strip(),
        )

    except Exception as exc:

        raise RuntimeError(
            f"OpenAI API 오류: {exc}"
        ) from exc

    out = (
        response.output_text
        or ""
    ).strip()

    if not out:

        raise RuntimeError(
            "OpenAI가 빈 응답을 반환했습니다."
        )

    return out


def future_memory_prompt(
    nickname,
    values_imp,
    goal,
    worry,
    direction
):

    return f'''
당신은 지금부터 "60세가 된 미래의 {nickname}"입니다.

[현재 나 정보]

- 가치: {values_imp}
- 목표: {goal}
- 걱정: {worry}
- 삶의 방향: {direction}

위 정보를 바탕으로
'미래 기억(future memory)'을
회고적 어조로 작성하세요.

반드시 아래 문장으로 시작하세요:

"안녕, 나는 60세의 너야. 내가 어떤 사람이 되어 있는지부터 이야기할게."
'''


def chat_starter(
    future_memory: str
):

    return f'''
지금부터 너는
60세가 된 '미래의 나'로만 말해줘.

아래의 '미래 기억'은
네(미래의 나)의 과거가 된 셈이야.

규칙:

- 회고적 어조 사용:
  "내가 네 나이였을 때..."를 자주 사용

- 따뜻하지만 현실적인 조언

- 정답이 아니라 방향 제시


등장 인사(반드시):

"안녕, 나는 60세의 너야. 내가 어떤 사람이 되어 있는지부터 이야기할게."


[미래 기억]

{future_memory}


이제부터 내가 질문하면,
위의 맥락을 유지해서 답해줘.
'''


# ─────────────────────────────────────────────────────────────
# 공통 UI
# ─────────────────────────────────────────────────────────────
def render_header(
    class_name,
    role
):

    c1, c2 = st.columns(
        [8, 2]
    )

    with c1:

        st.title(
            "🪞 Future Self Lab"
        )

        st.caption(
            f"은퇴와 상속설계 · "
            f"10·11주차 · "
            f"{class_name} · "
            f"{role}"
        )

    with c2:

        if st.button(
            "로그아웃",
            use_container_width=True
        ):

            st.session_state.clear()
            st.rerun()


def reveal_control(
    label: str,
    phase: str,
    class_name: str
):

    key = (
        f"reveal_"
        f"{class_name}_"
        f"{phase}_"
        f"{label}"
    )

    if not st.session_state.get(
        key,
        False
    ):

        if st.button(
            "📊 집단 결과 공개",
            key=f"show_{key}",
            type="primary"
        ):

            st.session_state[key] = True
            st.rerun()

        return False

    if st.button(
        "🙈 집단 결과 숨기기",
        key=f"hide_{key}"
    ):

        st.session_state[key] = False
        st.rerun()

    return True


# ─────────────────────────────────────────────────────────────
# 로그인
# ─────────────────────────────────────────────────────────────
if "role" not in st.session_state:

    st.title(
        "🪞 Future Self Lab"
    )

    st.caption(
        "10·11주차 · "
        "미래의 나를 측정하고, "
        "선택하고, 만나봅니다."
    )

    role_choice = st.radio(
        "접속 유형",
        [
            "학생",
            "교수"
        ],
        horizontal=True
    )

    # ─────────────────────────────
    # 학생 로그인
    # ─────────────────────────────
    if role_choice == "학생":

        name = st.text_input(
            "이름",
            placeholder=
            "출석 확인을 위해 실명을 입력하세요"
        )

        st.caption(
            "실명은 수업 운영과 제출 여부 확인에 사용합니다. "
            "강의실 집단 결과 화면에는 표시하지 않습니다."
        )

        if st.button(
            "입장하기",
            type="primary"
        ):

            nm = name.strip()

            if not nm:

                st.error(
                    "이름을 입력해주세요."
                )

                st.stop()

            active = active_classes()

            if len(active) == 1:

                cn = active[0]

                add_student(
                    cn,
                    nm
                )

                st.session_state.update(
                    role="student",
                    name=nm,
                    class_name=cn
                )

                st.rerun()

            elif len(active) == 0:

                st.error(
                    "현재 열려 있는 강의실이 없습니다."
                )

            else:

                st.session_state[
                    "pending_name"
                ] = nm

                st.session_state[
                    "choose_class"
                ] = True

                st.rerun()

        if st.session_state.get(
            "choose_class"
        ):

            active = active_classes()

            if not active:

                st.error(
                    "현재 열려 있는 강의실이 없습니다."
                )

                st.stop()

            cn = st.selectbox(
                "열려 있는 분반",
                active
            )

            if st.button(
                "이 분반으로 입장"
            ):

                nm = (
                    st.session_state
                    .get(
                        "pending_name",
                        ""
                    )
                    .strip()
                )

                add_student(
                    cn,
                    nm
                )

                st.session_state.update(
                    role="student",
                    name=nm,
                    class_name=cn
                )

                st.session_state.pop(
                    "choose_class",
                    None
                )

                st.session_state.pop(
                    "pending_name",
                    None
                )

                st.rerun()

    # ─────────────────────────────
    # 교수 로그인
    # ─────────────────────────────
    else:

        cn = st.selectbox(
            "분반",
            CLASSES
        )

        pw = st.text_input(
            "교수 비밀번호",
            type="password"
        )

        if st.button(
            "교수 통제소 입장",
            type="primary"
        ):

            if (
                PROF_PASSWORD
                and pw == PROF_PASSWORD
            ):

                st.session_state.update(
                    role="professor",
                    class_name=cn
                )

                st.rerun()

            else:

                st.error(
                    "비밀번호가 틀렸거나 "
                    "Secrets에 PROF_PASSWORD가 "
                    "설정되지 않았습니다."
                )

    st.stop()


# ─────────────────────────────────────────────────────────────
# 로그인 이후 공통
# ─────────────────────────────────────────────────────────────
my_class = (
    st.session_state.class_name
)

role = (
    st.session_state.role
)

phase = (
    get_status(my_class)
    .get(
        "phase",
        "대기"
    )
)

render_header(
    my_class,
    "학생"
    if role == "student"
    else "교수"
)

st.write("---")


# ─────────────────────────────────────────────────────────────
# 학생 화면
# ─────────────────────────────────────────────────────────────
if role == "student":

    me = (
        st.session_state.name
    )

    if st.button(
        "🔄 화면 새로고침",
        use_container_width=True
    ):

        st.rerun()

    st.caption(
        f"현재 단계: {phase}"
    )

    # ─────────────────────────────
    # 대기 / 입장
    # ─────────────────────────────
    if phase in (
        "대기",
        "학생입장"
    ):

        st.info(
            "접속되었습니다. "
            "교수님이 다음 활동을 열 때까지 "
            "기다려주세요."
        )

        st.stop()

    # ─────────────────────────────
    # 10주차 ① FSC
    # ─────────────────────────────
    if phase == "10주차 · 미래 자아 연속성":

        st.subheader(
            "10주차 ① 미래 자아 연속성 측정"
        )

        st.markdown(
    "왼쪽 원은 **현재 자아(Current Self)**, 오른쪽 원은 **10년 후 미래 자아(Future Self)** 입니다. "
    "두 원이 많이 겹칠수록 현재의 나와 미래의 나가 더 비슷하다고 느낀다는 의미입니다."
        )
        st.markdown(
            fsc_cards_html(),
            unsafe_allow_html=True
        )

        old = my_response(
            my_class,
            me,
            "fsc"
        )

        if old:

            score = int(
                (
                    old["payload"]
                    or {}
                ).get(
                    "option",
                    0
                )
            )

            st.success(
                f"제출했습니다. "
                f"내가 고른 그림은 "
                f"**옵션 {score}**입니다."
            )

        else:

            with st.form(
                "fsc_form"
            ):

                option = st.radio(
                    "여러 그림 중 현재의 나와 10년 후 미래의 내가 얼마나 비슷하다고 느껴지는지를 가장 잘 나타내는 그림을 선택하세요.",
                    list(
                        range(
                            1,
                            8
                        )
                    ),
                    horizontal=True,
                    index=None
                )

                if st.form_submit_button(
                    "제출",
                    type="primary"
                ):

                    if option is None:

                        st.warning(
                            "옵션을 선택해주세요."
                        )

                    else:

                        save_response(
                            my_class,
                            me,
                            "fsc",
                            {
                                "option":
                                    int(option)
                            }
                        )

                        st.rerun()

    # ─────────────────────────────
    # 10주차 ② 불쾌한 액체
    # ─────────────────────────────
    elif phase == "10주차 · 불쾌한 액체 마시기":

        st.subheader(
            "10주차 ② 불쾌한 액체 마시기"
        )

        st.caption(
            "실제로 불쾌한 액체를 마시는 실험이 아닙니다. "
            "각 상황에서 자신이 감당할 수 있다고 생각하는 양을 선택합니다."
        )

        old = my_response(
            my_class,
            me,
            "unpleasant_liquid"
        )

        if old:

            p = old["payload"]

            st.success(
                "제출했습니다."
            )

            st.write(
                f"**지금의 나:** "
                f"{p['now']}"
            )

            st.write(
                f"**한 달 뒤의 나:** "
                f"{p['future']}"
            )

            st.write(
                f"**친구:** "
                f"{p['friend']}"
            )

        else:

            with st.form(
                "liquid_form"
            ):

                now = st.radio(
                    "지금 당신은 얼마나 많은 양의 "
                    "불쾌한 액체(물 + 식초 + 간장 혼합)를 "
                    "직접 마실 수 있을 것 같나요?",
                    LIQUID_OPTIONS,
                    index=None,
                )

                future = st.radio(
                    "한 달 뒤 당신은 얼마나 많은 양의 "
                    "불쾌한 액체(물 + 식초 + 간장 혼합)를 "
                    "직접 마실 수 있을 것 같나요?",
                    LIQUID_OPTIONS,
                    index=None,
                )

                friend = st.radio(
                    "당신의 친구(자주 연락하는 친구)는 "
                    "얼마나 많은 양의 불쾌한 액체"
                    "(물 + 식초 + 간장 혼합)를 "
                    "직접 마실 수 있을 것 같나요?",
                    LIQUID_OPTIONS,
                    index=None,
                )

                if st.form_submit_button(
                    "제출",
                    type="primary"
                ):

                    if not all(
                        [
                            now,
                            future,
                            friend
                        ]
                    ):

                        st.warning(
                            "세 문항에 모두 응답해주세요."
                        )

                    else:

                        save_response(
                            my_class,
                            me,
                            "unpleasant_liquid",
                            {
                                "now":
                                    now,

                                "future":
                                    future,

                                "friend":
                                    friend,

                                "now_score":
                                    LIQUID_SCORE[now],

                                "future_score":
                                    LIQUID_SCORE[future],

                                "friend_score":
                                    LIQUID_SCORE[friend],
                            }
                        )

                        st.rerun()

    # ─────────────────────────────
    # 10주차 ③ 지연보상
    # ─────────────────────────────
    elif phase == "10주차 · 지연보상과 할인율":

        st.subheader(
            "10주차 ③ 지연보상과 할인율"
        )

        st.write(
            "각 상황에서 "
            "**지금 받는 선택**과 "
            "**조금 기다렸다가 더 받는 선택** 중 "
            "더 끌리는 쪽을 고르세요."
        )

        old = my_response(
            my_class,
            me,
            "discount"
        )

        if old:

            p = old["payload"]

            c1, c2, c3 = st.columns(
                3
            )

            c1.metric(
                "지연보상 선택",
                f"{p['delayed_count']} / 10"
            )

            c2.metric(
                "지연보상 선택률",
                f"{p['delayed_rate'] * 100:.0f}%"
            )

            c3.metric(
                "대표 할인율 k",
                f"{p['k_mid']:.4f}"
            )

            st.caption(
                "작년 분석 방식과 동일하게 "
                f"k_min={p['k_min']:.4f}, "
                f"k_max={p['k_max']:.4f}의 "
                "중간값을 대표값으로 사용했습니다."
            )

        else:

            with st.form(
                "discount_form"
            ):

                answers = []

                for i, q in enumerate(
                    DELAY_QUESTIONS,
                    1
                ):

                    answers.append(

                        st.radio(
                            f"{i}. 어느 쪽이 더 끌리시나요?",
                            [
                                q["immediate"],
                                q["delayed"]
                            ],
                            index=None,
                            key=f"delay_q_{i}",
                        )

                    )

                if st.form_submit_button(
                    "나의 할인율 확인",
                    type="primary"
                ):

                    if any(
                        a is None
                        for a in answers
                    ):

                        st.warning(
                            "10문항에 모두 응답해주세요."
                        )

                    else:

                        calc = calc_discount(
                            answers
                        )

                        save_response(
                            my_class,
                            me,
                            "discount",
                            {
                                "answers":
                                    answers,

                                **calc
                            }
                        )

                        st.rerun()


                # ─────────────────────────────
                # FSC 점수별 평균 지연보상 선택률
                # ─────────────────────────────
                st.markdown("#### FSC 점수별 평균 지연보상 선택률")

                graph_df = (
                    cross_df
                    .groupby("fsc", as_index=False)["delayed_rate"]
                    .mean()
                    .sort_values("fsc")
                )

                graph_df["지연보상 선택률(%)"] = (
                    graph_df["delayed_rate"] * 100
                )

                graph_df["FSC"] = graph_df["fsc"].astype(int)

                st.line_chart(
                    graph_df.set_index("FSC")[
                        ["지연보상 선택률(%)"]
                    ]
                )

                # ─────────────────────────────
                # 교수용 해석
                # ─────────────────────────────
                st.markdown("#### 이번 분반 결과")

                if rho_rate is None:
                    st.info(
                        "응답의 변이가 충분하지 않아 "
                        "FSC와 지연보상 선택률의 관계를 계산할 수 없습니다."
                    )

                elif p_rate < 0.05 and rho_rate > 0:
                    st.success(
                        "이번 분반에서는 현재 자아와 미래 자아 간의 "
                        "유사성을 높게 느낄수록 미래 보상을 더 많이 선택하고, "
                        "지연보상 선택률이 높은 경향이 나타났습니다."
                    )

                elif p_rate < 0.05 and rho_rate < 0:
                    st.warning(
                        "이번 분반에서는 예상과 반대로 미래 자아 연속성이 "
                        "높을수록 지연보상 선택률이 낮은 관계가 나타났습니다."
                    )

                elif rho_rate > 0:
                    st.info(
                        "이번 분반에서는 미래 자아 연속성이 높을수록 "
                        "지연보상 선택률도 높아지는 방향은 나타났지만, "
                        "통계적으로 뚜렷한 관계라고 보기는 어렵습니다."
                    )

                elif rho_rate < 0:
                    st.info(
                        "이번 분반에서는 미래 자아 연속성이 높을수록 "
                        "지연보상 선택률이 낮아지는 방향이 나타났지만, "
                        "통계적으로 뚜렷한 관계라고 보기는 어렵습니다."
                    )

                else:
                    st.info(
                        "이번 분반에서는 미래 자아 연속성과 "
                        "지연보상 선택률 사이에 뚜렷한 관계가 나타나지 않았습니다."
                    )

                # 할인율 k 해석
                if rho_k is not None:
                    st.caption(
                        f"참고: FSC와 할인율 k의 Spearman 상관계수는 "
                        f"ρ = {rho_k:.3f} (p = {p_k:.3f})입니다. "
                        "k가 낮을수록 미래 보상을 덜 할인한다는 의미입니다."
                    )
    
    # ─────────────────────────────
    # 11주차 ④ 정신적 시간여행
    # ─────────────────────────────
    elif phase == "11주차 · 정신적 시간여행":

        st.subheader(
            "11주차 ④ 정신적 시간여행"
        )

        group = time_group(
            my_class,
            me
        )

        old = my_response(
            my_class,
            me,
            "time_travel"
        )

        if group == "A":

            st.write(
                "시간에 대해 생각할 때는 "
                "두 가지 방식이 있습니다."
            )

            st.write(
                "첫 번째는 "
                "**현재에서 시작하여 미래로** "
                "마음속 여행을 하는 것입니다."
            )

            st.write(
                "두 번째는 "
                "**미래에서 시작하여 현재로** "
                "마음속 여행을 하는 것입니다."
            )

            left = (
                "미래에서 시작하여 현재로"
            )

            right = (
                "현재에서 시작하여 미래로"
            )

        else:

            st.write(
                "시간에 대해 생각할 때는 "
                "두 가지 방식이 있습니다."
            )

            st.write(
                "첫 번째는 "
                "**미래에서 시작하여 현재로** "
                "마음속 여행을 하는 것입니다."
            )

            st.write(
                "두 번째는 "
                "**현재에서 시작하여 미래로** "
                "마음속 여행을 하는 것입니다."
            )

            left = (
                "현재에서 시작하여 미래로"
            )

            right = (
                "미래에서 시작하여 현재로"
            )

        if old:

            raw = int(
                (
                    old["payload"]
                    or {}
                ).get(
                    "raw_score",
                    5
                )
            )

            st.success(
                f"제출했습니다. "
                f"내가 선택한 위치는 "
                f"**{raw}**입니다."
            )

        else:

            with st.form(
                "time_travel_form"
            ):

                st.markdown(
                    f"**0 = {left}** "
                    "　←──────→　 "
                    f"**10 = {right}**"
                )

                raw = st.slider(
                    "당신은 시간에 대해 "
                    "어떤 방식으로 주로 생각하십니까?",
                    0,
                    10,
                    5,
                    1
                )

                if st.form_submit_button(
                    "제출",
                    type="primary"
                ):

                    save_response(
                        my_class,
                        me,
                        "time_travel",
                        {
                            "group":
                                group,

                            "raw_score":
                                int(raw),

                            "aligned_score":
                                int(
                                    aligned_time_score(
                                        group,
                                        raw
                                    )
                                ),
                        }
                    )

                    st.rerun()

    # ─────────────────────────────
    # 11주차 ⑤ Future You
    # ─────────────────────────────
    elif phase == "11주차 · Future You":

        st.subheader(
            "11주차 ⑤ Future You · 60세의 나 만나기"
        )

        st.info(
            "실명은 Future You 생성 요청에 보내지 않습니다. "
            "AI에는 아래에 직접 입력한 "
            "**별명/호칭, 가치, 목표, 걱정, 미래상**만 전달됩니다. "
            "너무 개인적이거나 민감한 내용은 적지 않아도 됩니다."
        )

        old = my_response(
            my_class,
            me,
            "future_you"
        )

        if (
            old
            and (
                old["payload"]
                or {}
            ).get(
                "future_memory"
            )
        ):

            p = old["payload"]

            st.success(
                "미래의 내가 도착했습니다."
            )

            st.markdown(
                "### 미래 기억"
            )

            st.write(
                p["future_memory"]
            )

            st.markdown(
                "### 대화 시작 문장"
            )

            st.caption(
                "아래 코드 블록의 복사 아이콘을 누른 뒤, "
                "평소 사용하는 ChatGPT/Gemini에 붙여넣고 "
                "질문을 시작하세요."
            )

            st.code(
                p["chat_starter"],
                language=None
            )

        else:

            with st.form(
                "future_you_form"
            ):

                nickname = st.text_input(
                    "자신을 알아볼 수 있는 "
                    "단어나 별명/호칭"
                )

                values_imp = st.text_area(
                    "지금 자신이 중요하게 생각하는 "
                    "가치 3가지",
                    placeholder=
                    "예: 건강, 사랑, 성실"
                )

                goal = st.text_area(
                    "지금 자신이 이루고 싶은 목표",
                    placeholder=
                    "예: 취업, 창업, 연애"
                )

                worry = st.text_area(
                    "최근 6개월 동안 가장 자주 했던 "
                    "걱정 또는 고민",
                    placeholder=
                    "예: 졸업 후 진로, 돈 문제"
                )

                direction = st.text_area(
                    "자신이 원하는 삶의 방향 / "
                    "미래 자신의 이미지",
                    placeholder=
                    "예: 단란한 가정의 부모, "
                    "사회적으로 성공적인 지위"
                )

                generate = (
                    st.form_submit_button(
                        "✨ 미래의 나 만나기",
                        type="primary"
                    )
                )

            if generate:

                if not all(
                    x.strip()
                    for x in [
                        nickname,
                        values_imp,
                        goal,
                        worry,
                        direction
                    ]
                ):

                    st.warning(
                        "다섯 항목을 모두 입력해주세요."
                    )

                else:

                    try:

                        with st.spinner(
                            "60세의 미래 기억을 "
                            "만들고 있습니다..."
                        ):

                            fm = call_openai(
                                future_memory_prompt(
                                    nickname.strip(),
                                    values_imp.strip(),
                                    goal.strip(),
                                    worry.strip(),
                                    direction.strip()
                                )
                            )

                            starter = chat_starter(
                                fm
                            )

                            save_response(
                                my_class,
                                me,
                                "future_you",
                                {
                                    "nickname":
                                        nickname.strip(),

                                    "values":
                                        values_imp.strip(),

                                    "goal":
                                        goal.strip(),

                                    "worry":
                                        worry.strip(),

                                    "direction":
                                        direction.strip(),

                                    "future_memory":
                                        fm,

                                    "chat_starter":
                                        starter,

                                    "model":
                                        OPENAI_MODEL,
                                }
                            )

                        st.rerun()

                    except Exception as exc:

                        st.error(
                            "미래 기억 생성에 실패했습니다. "
                            "다시 시도해주세요.\n\n"
                            f"{exc}"
                        )

    # ─────────────────────────────
    # 학생 결과
    # ─────────────────────────────
    elif phase == "결과":

        st.subheader(
            "10·11주차 활동 완료"
        )

        stages = [
            (
                "미래 자아 연속성",
                "fsc"
            ),
            (
                "불쾌한 액체",
                "unpleasant_liquid"
            ),
            (
                "지연보상·할인율",
                "discount"
            ),
            (
                "정신적 시간여행",
                "time_travel"
            ),
            (
                "Future You",
                "future_you"
            ),
        ]

        mine = []

        for label, key in stages:

            mine.append(
                {
                    "활동":
                        label,

                    "상태":
                        "완료"
                        if my_response(
                            my_class,
                            me,
                            key
                        )
                        else "미제출"
                }
            )

        st.dataframe(
            pd.DataFrame(mine),
            use_container_width=True,
            hide_index=True
        )

    elif phase == "종료":

        st.info(
            "이번 활동이 종료되었습니다."
        )


# ─────────────────────────────────────────────────────────────
# 교수 화면
# ─────────────────────────────────────────────────────────────
else:

    st.subheader(
        "교수 통제소"
    )

    c1, c2, c3 = st.columns(
        [4, 2, 2]
    )

    new_phase = c1.selectbox(
        "진행 단계",
        PHASES,
        index=PHASES.index(
            phase
        )
    )

    if c2.button(
        "✅ 단계 적용",
        type="primary",
        use_container_width=True
    ):

        set_phase(
            my_class,
            new_phase
        )

        st.rerun()

    if c3.button(
        "🔄 새로고침",
        use_container_width=True
    ):

        st.rerun()

    students = all_students(
        my_class
    )

    st.metric(
        "접속 학생",
        f"{len(students)}명"
    )

    st.write("---")

    # ─────────────────────────────
    # 교수 FSC
    # ─────────────────────────────
    if phase == "10주차 · 미래 자아 연속성":

        df = all_responses(
            my_class,
            "fsc"
        )

        st.subheader(
            "미래 자아 연속성 측정"
        )

        st.metric(
            "제출",
            f"{len(df)}명"
        )

        if (
            not df.empty
            and reveal_control(
                "fsc",
                phase,
                my_class
            )
        ):

            vals = [
                int(
                    (
                        p
                        or {}
                    ).get(
                        "option",
                        0
                    )
                )
                for p in df["payload"]
            ]

            counts = (
                pd.Series(vals)
                .value_counts()
                .reindex(
                    range(1, 8),
                    fill_value=0
                )
            )

            result = pd.DataFrame(
                {
                    "옵션":
                        [
                            f"옵션 {i}"
                            for i in range(
                                1,
                                8
                            )
                        ],

                    "학생 수":
                        counts.values
                }
            )

            st.bar_chart(
                result.set_index(
                    "옵션"
                )
            )

            st.metric(
                "학급 평균",
                f"{mean(vals):.2f}"
            )

            st.caption(
                "값이 클수록 현재 자아와 "
                "10년 후 미래 자아를 "
                "더 비슷하게 느낀다는 응답입니다."
            )

    # ─────────────────────────────
    # 교수 불쾌한 액체
    # ─────────────────────────────
    elif phase == "10주차 · 불쾌한 액체 마시기":

        df = all_responses(
            my_class,
            "unpleasant_liquid"
        )

        st.subheader(
            "불쾌한 액체 마시기"
        )

        st.metric(
            "제출",
            f"{len(df)}명"
        )

        if (
            not df.empty
            and reveal_control(
                "liquid",
                phase,
                my_class
            )
        ):

            now_scores = []
            fut_scores = []
            friend_scores = []

            for p in df["payload"]:

                p = p or {}

                now_scores.append(
                    float(
                        p["now_score"]
                    )
                )

                fut_scores.append(
                    float(
                        p["future_score"]
                    )
                )

                friend_scores.append(
                    float(
                        p["friend_score"]
                    )
                )

            avg_df = pd.DataFrame(
                {
                    "대상":
                        [
                            "지금의 나",
                            "한 달 뒤의 나",
                            "친구"
                        ],

                    "평균 점수":
                        [
                            mean(now_scores),
                            mean(fut_scores),
                            mean(friend_scores)
                        ],
                }
            )

            st.bar_chart(
                avg_df.set_index(
                    "대상"
                )
            )

            st.dataframe(
                avg_df.round(3),
                use_container_width=True,
                hide_index=True
            )

            if len(df) >= 2:

                p_now_future = (
                    ttest_rel(
                        now_scores,
                        fut_scores,
                        nan_policy="omit"
                    ).pvalue
                )

                p_now_friend = (
                    ttest_rel(
                        now_scores,
                        friend_scores,
                        nan_policy="omit"
                    ).pvalue
                )

                p_future_friend = (
                    ttest_rel(
                        fut_scores,
                        friend_scores,
                        nan_policy="omit"
                    ).pvalue
                )

                test_df = pd.DataFrame(
                    [
                        {
                            "비교":
                                "현재 자기 vs 미래 자기",

                            "대응표본 t검정 p값":
                                p_now_future
                        },

                        {
                            "비교":
                                "현재 자기 vs 친구",

                            "대응표본 t검정 p값":
                                p_now_friend
                        },

                        {
                            "비교":
                                "미래 자기 vs 친구",

                            "대응표본 t검정 p값":
                                p_future_friend
                        },
                    ]
                )

                st.markdown(
                    "#### 작년 분석 엑셀과 같은 대응표본 비교"
                )

                st.dataframe(
                    test_df.style.format(
                        {
                            "대응표본 t검정 p값":
                                "{:.4f}"
                        }
                    ),
                    use_container_width=True,
                    hide_index=True
                )

            st.caption(
                "점수 환산: "
                "1티스푼=1, "
                "1테이블스푼=2, "
                "1/4컵=3, "
                "1/2컵=4, "
                "1컵=5."
            )

    # ─────────────────────────────
    # 교수 지연보상
    # ─────────────────────────────
    elif phase == "10주차 · 지연보상과 할인율":

        df = all_responses(
            my_class,
            "discount"
        )

        st.subheader(
            "지연보상과 할인율"
        )

        st.metric(
            "제출",
            f"{len(df)}명"
        )

        if (
            not df.empty
            and reveal_control(
                "discount",
                phase,
                my_class
            )
        ):

            rows = []

            for p in df["payload"]:

                p = p or {}

                rows.append(
                    {
                        "지연보상 선택 개수":
                            p["delayed_count"],

                        "지연보상 선택률":
                            p["delayed_rate"],

                        "k_mid":
                            p["k_mid"],
                    }
                )

            res = pd.DataFrame(
                rows
            )

            c1, c2, c3 = st.columns(
                3
            )

            c1.metric(
                "평균 지연보상 선택",
                f"{res['지연보상 선택 개수'].mean():.2f} / 10"
            )

            c2.metric(
                "평균 지연보상 선택률",
                f"{res['지연보상 선택률'].mean() * 100:.1f}%"
            )

            c3.metric(
                "평균 대표 할인율 k",
                f"{res['k_mid'].mean():.4f}"
            )

            hist = (
                res[
                    "지연보상 선택 개수"
                ]
                .value_counts()
                .reindex(
                    range(0, 11),
                    fill_value=0
                )
            )

            st.markdown(
                "#### 지연보상 선택 개수 분포"
            )

            st.bar_chart(
                pd.DataFrame(
                    {
                        "학생 수":
                            hist.values
                    },
                    index=[
                        str(i)
                        for i in range(11)
                    ]
                )
            )
        st.write("---")
        st.subheader("FSC × 지연보상 교차분석")

        st.caption(
        "미래 자아 연속성과 지연보상 선택을 모두 완료한 학생만 분석합니다."
    )

        cross_key = f"show_fsc_discount_{my_class}"

        if st.button(
        "📊 교차분석 보기"
        if not st.session_state.get(cross_key, False)
        else "🙈 교차분석 숨기기",
        key=f"btn_{cross_key}"
    ):
        st.session_state[cross_key] = not st.session_state.get(
            cross_key, False
        )
        st.rerun()

        if st.session_state.get(cross_key, False):

        cross_df = fsc_discount_analysis(my_class)

        if cross_df.empty:
            st.warning(
                "미래 자아 연속성과 지연보상을 모두 완료한 학생이 아직 없습니다."
            )

        elif len(cross_df) < 3:
            st.warning(
                f"두 활동을 모두 완료한 학생은 {len(cross_df)}명입니다. "
                "상관분석을 하기에는 응답 수가 부족합니다."
            )

        else:
            rho_rate, p_rate = safe_spearman(
                cross_df,
                "fsc",
                "delayed_rate"
            )

            rho_k, p_k = safe_spearman(
                cross_df,
                "fsc",
                "k_mid"
            )

            c1, c2, c3 = st.columns(3)

            with c1:
                st.metric(
                    "분석 인원",
                    f"{len(cross_df)}명"
                )

            with c2:
                if rho_rate is not None:
                    st.metric(
                        "FSC ↔ 지연보상 선택률",
                        f"ρ = {rho_rate:.3f}"
                    )
                else:
                    st.metric(
                        "FSC ↔ 지연보상 선택률",
                        "계산 불가"
                    )

            with c3:
                if rho_k is not None:
                    st.metric(
                        "FSC ↔ 할인율 k",
                        f"ρ = {rho_k:.3f}"
                    )
                else:
                    st.metric(
                        "FSC ↔ 할인율 k",
                        "계산 불가"
                    )

            st.markdown("#### FSC 점수별 평균 지연보상 선택률")

            graph_df = (
                cross_df
                .groupby("fsc", as_index=False)["delayed_rate"]
                .mean()
                .sort_values("fsc")
            )

            graph_df["지연보상 선택률(%)"] = (
                graph_df["delayed_rate"] * 100
            )

            graph_df["FSC"] = graph_df["fsc"].astype(int)

            st.line_chart(
                graph_df.set_index("FSC")[
                    ["지연보상 선택률(%)"]
                ]
            )

            st.markdown("#### 이번 분반 결과")

            if rho_rate is None:
                st.info(
                    "응답의 변이가 충분하지 않아 "
                    "FSC와 지연보상 선택률의 관계를 계산할 수 없습니다."
                )

            elif p_rate < 0.05 and rho_rate > 0:
                st.success(
                    "이번 분반에서는 현재 자아와 미래 자아 간의 "
                    "유사성을 높게 느낄수록 미래 보상을 더 많이 선택하고, "
                    "지연보상 선택률이 높은 경향이 나타났습니다."
                )

            elif p_rate < 0.05 and rho_rate < 0:
                st.warning(
                    "이번 분반에서는 예상과 반대로 미래 자아 연속성이 "
                    "높을수록 지연보상 선택률이 낮은 관계가 나타났습니다."
                )

            elif rho_rate > 0:
                st.info(
                    "이번 분반에서는 미래 자아 연속성이 높을수록 "
                    "지연보상 선택률도 높아지는 방향은 나타났지만, "
                    "통계적으로 뚜렷한 관계라고 보기는 어렵습니다."
                )

            elif rho_rate < 0:
                st.info(
                    "이번 분반에서는 미래 자아 연속성이 높을수록 "
                    "지연보상 선택률이 낮아지는 방향이 나타났지만, "
                    "통계적으로 뚜렷한 관계라고 보기는 어렵습니다."
                )

            else:
                st.info(
                    "이번 분반에서는 미래 자아 연속성과 "
                    "지연보상 선택률 사이에 뚜렷한 관계가 나타나지 않았습니다."
                )

            if rho_k is not None:
                st.caption(
                    f"참고: FSC와 할인율 k의 Spearman 상관계수는 "
                    f"ρ = {rho_k:.3f} (p = {p_k:.3f})입니다. "
                    "k가 낮을수록 미래 보상을 덜 할인한다는 의미입니다."
                )                
              

    
    # ─────────────────────────────
    # 교수 정신적 시간여행
    # ─────────────────────────────
    elif phase == "11주차 · 정신적 시간여행":

        df = all_responses(
            my_class,
            "time_travel"
        )

        st.subheader(
            "정신적 시간여행 A/B"
        )

        st.metric(
            "제출",
            f"{len(df)}명"
        )

        if not df.empty:

            groups = [
                str(
                    (
                        p
                        or {}
                    ).get(
                        "group",
                        ""
                    )
                )
                for p in df["payload"]
            ]

            gc = (
                pd.Series(groups)
                .value_counts()
            )

            st.caption(
                f"자동 배정: "
                f"A조 {int(gc.get('A', 0))}명 · "
                f"B조 {int(gc.get('B', 0))}명"
            )

        if (
            not df.empty
            and reveal_control(
                "time_travel",
                phase,
                my_class
            )
        ):

            aligned = [
                int(
                    (
                        p
                        or {}
                    ).get(
                        "aligned_score",
                        5
                    )
                )
                for p in df["payload"]
            ]

            n = len(
                aligned
            )

            forward = sum(
                x >= 6
                for x in aligned
            )

            reverse = sum(
                x <= 4
                for x in aligned
            )

            neutral = sum(
                x == 5
                for x in aligned
            )

            forward_only = sum(
                x == 10
                for x in aligned
            )

            summary = pd.DataFrame(
                [
                    {
                        "구분":
                            "순방향(현재→미래)",

                        "학생 수":
                            forward,

                        "비율":
                            forward / n
                    },

                    {
                        "구분":
                            "역방향(미래→현재)",

                        "학생 수":
                            reverse,

                        "비율":
                            reverse / n
                    },

                    {
                        "구분":
                            "둘 다 아님(5)",

                        "학생 수":
                            neutral,

                        "비율":
                            neutral / n
                    },

                    {
                        "구분":
                            "순방향만(10)",

                        "학생 수":
                            forward_only,

                        "비율":
                            forward_only / n
                    },
                ]
            )

            st.dataframe(
                summary.style.format(
                    {
                        "비율":
                            "{:.1%}"
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

            st.bar_chart(
                summary
                .iloc[:3]
                .set_index(
                    "구분"
                )[
                    "학생 수"
                ]
            )

            st.markdown(
                "#### 작년 분석 파일에 적어둔 파일럿 연구 비교값"
            )

            pilot = pd.DataFrame(
                [
                    {
                        "구분":
                            "순방향(현재→미래)",

                        "파일럿 연구":
                            "83%"
                    },

                    {
                        "구분":
                            "역방향(미래→현재)",

                        "파일럿 연구":
                            "15%"
                    },

                    {
                        "구분":
                            "둘 다 아님",

                        "파일럿 연구":
                            "2%"
                    },

                    {
                        "구분":
                            "순방향만",

                        "파일럿 연구":
                            "27%"
                    },
                ]
            )

            st.dataframe(
                pilot,
                use_container_width=True,
                hide_index=True
            )

            st.caption(
                "A조와 B조는 질문의 좌우 순서가 반대입니다. "
                "B조는 작년 분석과 동일하게 "
                "10-원응답으로 변환한 뒤 합산했습니다."
            )

    # ─────────────────────────────
    # 교수 Future You
    # ─────────────────────────────
    elif phase == "11주차 · Future You":

        df = all_responses(
            my_class,
            "future_you"
        )

        st.subheader(
            "Future You 생성 현황"
        )

        st.metric(
            "미래 기억 생성 완료",
            f"{len(df)}명"
        )

        st.info(
            "학생의 가치·목표·걱정·미래상 원문과 "
            "생성된 미래 기억은 "
            "강의실 화면에 표시하지 않습니다."
        )

        if not df.empty:

            with st.expander(
                "교수 확인용 제출자 명단 보기"
            ):

                status = pd.DataFrame(
                    {
                        "이름":
                            df["name"].tolist(),

                        "생성 상태":
                            [
                                "완료"
                            ] * len(df)
                    }
                )

                st.dataframe(
                    status,
                    use_container_width=True,
                    hide_index=True
                )

    # ─────────────────────────────
    # 교수 전체 결과
    # ─────────────────────────────
    elif phase == "결과":

        stages = [
            (
                "10주차 · 미래 자아 연속성",
                "fsc"
            ),

            (
                "10주차 · 불쾌한 액체",
                "unpleasant_liquid"
            ),

            (
                "10주차 · 지연보상과 할인율",
                "discount"
            ),

            (
                "11주차 · 정신적 시간여행",
                "time_travel"
            ),

            (
                "11주차 · Future You",
                "future_you"
            ),
        ]

        rows = [
            {
                "활동":
                    label,

                "제출 인원":
                    len(
                        all_responses(
                            my_class,
                            key
                        )
                    )
            }
            for label, key in stages
        ]

        st.dataframe(
            pd.DataFrame(
                rows
            ),
            use_container_width=True,
            hide_index=True
        )

    # ─────────────────────────────
    # 데이터 관리
    # ─────────────────────────────
    with st.expander(
        "⚠️ 데이터 관리"
    ):

        stage_map = {
            "미래 자아 연속성":
                "fsc",

            "불쾌한 액체":
                "unpleasant_liquid",

            "지연보상과 할인율":
                "discount",

            "정신적 시간여행":
                "time_travel",

            "Future You":
                "future_you",
        }

        target_label = st.selectbox(
            "삭제할 활동",
            list(
                stage_map.keys()
            )
        )

        if st.button(
            "선택 활동 응답 삭제"
        ):

            (
                supabase
                .table(T_RESPONSES)
                .delete()
                .eq(
                    "class_name",
                    my_class
                )
                .eq(
                    "stage",
                    stage_map[
                        target_label
                    ]
                )
                .execute()
            )

            st.rerun()

        if st.button(
            "이 분반 10·11주차 응답 전체 삭제"
        ):

            (
                supabase
                .table(T_RESPONSES)
                .delete()
                .eq(
                    "class_name",
                    my_class
                )
                .execute()
            )

            st.rerun()

        if st.button(
            "이 분반 전체 초기화"
        ):

            (
                supabase
                .table(T_RESPONSES)
                .delete()
                .eq(
                    "class_name",
                    my_class
                )
                .execute()
            )

            (
                supabase
                .table(T_STUDENTS)
                .delete()
                .eq(
                    "class_name",
                    my_class
                )
                .execute()
            )

            set_phase(
                my_class,
                "대기"
            )

            st.rerun()
