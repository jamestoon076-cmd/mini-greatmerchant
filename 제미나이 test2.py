import streamlit as st
import time
import json
import gspread
from google.oauth2.service_account import Credentials

# --- [설정] 페이지 기본 세팅 ---
st.set_page_config(page_title="조선거상", layout="centered")

# --- [기능] 구글 시트 연결 ---
def connect_gsheet():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gspread"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"❌ 연결 실패: {e}")
        return None

doc = connect_gsheet()

# --- [기능] 슬롯 데이터 불러오기 ---
def get_slots():
    if not doc: return []
    sheet = doc.worksheet("플레이어")
    data = sheet.get_all_records()
    return data

# --- [기능] 게임 상태 관리 ---
if 'game_started' not in st.session_state:
    st.session_state.game_started = False
if 'player' not in st.session_state:
    st.session_state.player = None

# --- [화면 1] 세이브 슬롯 선택 (정보 표시) ---
if not st.session_state.game_started:
    st.title("🏯 조선거상 미니")
    st.subheader("💾 세이브 슬롯 선택")
    
    slots = get_slots()
    
    # [수정] 슬롯 정보를 먼저 리스트로 보여줍니다.
    if slots:
        for s in slots:
            st.write(f"**[{s['slot']}]** 위치: {s['pos']} | 잔액: {int(s.get('money', 0)):,}냥")
    else:
        st.warning("불러올 슬롯 데이터가 없습니다.")

    st.write("---")
    # 정보 확인 후 번호 입력
    slot_input = st.text_input("플레이할 슬롯 번호를 입력하세요", value="1")
    
    if st.button("🎮 게임 시작/불러오기", use_container_width=True):
        selected = next((s for s in slots if str(s['slot']) == slot_input), None)
        if selected:
            st.session_state.game_started = True
            st.session_state.player = selected
            st.rerun()
        else:
            st.error("해당 슬롯 번호를 찾을 수 없습니다.")

# --- [화면 2] 물품 거래 (슬롯 선택 후) ---
else:
    st.title("🏯 조선거상 미니")
    p = st.session_state.player
    
    # 상단 상태 정보
    col1, col2 = st.columns(2)
    with col1:
        st.metric("현재 위치", p['pos'])
    with col2:
        st.metric("소지 금액", f"{int(p['money']):,}냥")
    
    st.divider()

    # 물품 거래 (1000개 대량 입력 가능)
    st.subheader("🛒 물품 거래")
    item = st.selectbox("물건 선택", ["쌀", "고기", "약초"])
    qty_str = st.text_input("수량 입력 (타이핑 가능)", value="1")
    
    b_col1, b_col2 = st.columns(2)
    with b_col1:
        if st.button("💰 매수하기", use_container_width=True):
            st.success(f"{item} {qty_str}개 매수 완료!")
    with b_col2:
        if st.button("📦 매도하기", use_container_width=True):
            st.success(f"{item} {qty_str}개 매도 완료!")

    if st.button("↩️ 다른 슬롯 선택하기"):
        st.session_state.game_started = False
        st.rerun()
