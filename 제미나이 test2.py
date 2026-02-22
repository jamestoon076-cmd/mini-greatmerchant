import streamlit as st
import time
import json
import gspread
from google.oauth2.service_account import Credentials

# --- [설정] 페이지 기본 세팅 ---
st.set_page_config(page_title="조선거상", layout="centered")

# --- [기능] 구글 시트 연결 (Secrets 사용) ---
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

# --- [기능] 데이터가 있는 슬롯만 필터링하여 가져오기 ---
def get_slots():
    if not doc: return []
    try:
        # '플레이어' 탭이 없으면 첫 번째 탭을 가져옵니다
        sheet = doc.worksheet("플레이어")
    except:
        sheet = doc.get_worksheet(0)
    
    all_data = sheet.get_all_records()
    
    # [수정] 슬롯 번호가 실제 있는 행만 필터링 (무한 증식 방지)
    valid_slots = [s for s in all_data if str(s.get('slot', '')).strip() != ""]
    return valid_slots

# --- [기능] 게임 상태 관리 (세션 스테이트) ---
if 'game_started' not in st.session_state:
    st.session_state.game_started = False
if 'player' not in st.session_state:
    st.session_state.player = None

# --- [화면 1] 세이브 슬롯 선택 (로그인 전) ---
if not st.session_state.game_started:
    st.title("🏯 조선거상 미니")
    st.subheader("💾 세이브 슬롯 선택")
    
    with st.spinner('슬롯 정보를 불러오는 중...'):
        slots = get_slots()
    
    if slots:
        # 슬롯 정보를 박스 형태로 깔끔하게 표시
        for s in slots:
            st.info(f"📍 **슬롯 {s['slot']}** | 위치: {s.get('pos', '한양')} | 잔액: {int(s.get('money', 0)):,}냥")
    else:
        st.warning("불러올 수 있는 슬롯 데이터가 없습니다.")

    st.write("---")
    # 모바일에서 직접 숫자를 칠 수 있는 입력창
    slot_input = st.text_input("플레이할 슬롯 번호를 입력하세요", value="1")
    
    if st.button("🎮 게임 시작하기", use_container_width=True):
        # 입력한 번호와 일치하는 슬롯 찾기
        selected = next((s for s in slots if str(s.get('slot')) == slot_input), None)
        if selected:
            st.session_state.game_started = True
            st.session_state.player = selected
            st.rerun() # 화면을 즉시 거래창으로 전환
        else:
            st.error("슬롯 번호를 다시 확인해주세요.")

# --- [화면 2] 물품 거래 및 게임 메인 (로그인 후) ---
else:
    st.title("🏯 조선거상 미니")
    p = st.session_state.player
    
    # 상단 플레이어 상태 정보
    col1, col2 = st.columns(2)
    with col1:
        st.metric("현재 위치", p.get('pos', '한양'))
    with col2:
        st.metric("소지 금액", f"{int(p.get('money', 0)):,}냥")
    
    st.divider()

    # 대량 거래 UI (모바일 엔터키 대신 버튼 사용)
    st.subheader("🛒 물품 거래")
    # 아이템 리스트는 사용자님의 원본 ITEMS_INFO에 맞춰 수정하세요.
    item_choice = st.selectbox("아이템 선택", ["쌀", "고기", "약초", "인삼"])
    
    # [핵심] 1000개 등 대량 입력을 위한 직접 타이핑 칸
    qty_str = st.text_input("거래 수량 입력 (직접 타이핑)", value="1")
    
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("💰 매수하기", use_container_width=True):
            try:
                qty = int(qty_str)
                # 여기에 원본 buy(item_choice, qty) 함수를 연결하세요.
                st.success(f"성공적으로 {qty}개를 매수했습니다!")
            except:
                st.error("숫자를 정확히 입력하세요.")
                
    with btn_col2:
        if st.button("📦 매도하기", use_container_width=True):
            try:
                qty = int(qty_str)
                # 여기에 원본 sell(item_choice, qty) 함수를 연결하세요.
                st.success(f"성공적으로 {qty}개를 매도했습니다!")
            except:
                st.error("숫자를 정확히 입력하세요.")

    st.divider()
    # 로그아웃 기능
    if st.button("↩️ 다른 슬롯 선택 (처음으로)"):
        st.session_state.game_started = False
        st.rerun()
