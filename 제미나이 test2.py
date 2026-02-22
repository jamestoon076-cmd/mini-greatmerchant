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

# --- [기능] 슬롯 데이터 불러오기 (안전 모드) ---
def get_slots():
    if not doc: return []
    try:
        # 1순위: '플레이어' 탭 시도
        sheet = doc.worksheet("플레이어")
    except:
        # 2순위: 안되면 그냥 첫 번째 탭 가져오기
        sheet = doc.get_worksheet(0)
    
    return sheet.get_all_records()

# --- [기능] 게임 상태 관리 ---
if 'game_started' not in st.session_state:
    st.session_state.game_started = False
if 'player' not in st.session_state:
    st.session_state.player = None

# --- [화면 1] 세이브 슬롯 선택 (정보 표시) ---
if not st.session_state.game_started:
    st.title("🏯 조선거상 미니")
    st.subheader("💾 세이브 슬롯 선택")
    
    with st.spinner('데이터 불러오는 중...'):
        slots = get_slots()
    
    if slots:
        # [이미지 참고] 슬롯 정보를 모바일에서 보기 편하게 리스트업
        for s in slots:
            slot_id = s.get('slot', '?')
            pos = s.get('pos', '알수없음')
            money = s.get('money', 0)
            st.info(f"📍 **슬롯 {slot_id}** | 현재위치: {pos} | 잔액: {int(money):,}냥")
    else:
        st.warning("데이터가 비어있거나 탭을 찾을 수 없습니다.")

    st.write("---")
    # [핵심] 키보드 타이핑 가능하도록 텍스트 입력창 유지
    slot_input = st.text_input("플레이할 슬롯 번호를 직접 입력하세요", value="1")
    
    if st.button("🎮 게임 시작하기", use_container_width=True):
        selected = next((s for s in slots if str(s.get('slot')) == slot_input), None)
        if selected:
            st.session_state.game_started = True
            st.session_state.player = selected
            st.rerun()
        else:
            st.error("슬롯 번호를 다시 확인해주세요.")

# --- [화면 2] 물품 거래 (로그인 성공 시) ---
else:
    st.title("🏯 조선거상 미니")
    p = st.session_state.player
    
    # 상단 요약 정보
    c1, c2 = st.columns(2)
    c1.metric("위치", p.get('pos', '한양'))
    c2.metric("잔액", f"{int(p.get('money', 0)):,}냥")
    
    st.divider()

    # 대량 거래 UI (모바일 엔터키 대신 버튼 사용)
    st.subheader("🛒 물품 거래")
    item_list = ["쌀", "고기", "약초"] # 실제 ITEMS_INFO가 있다면 그걸로 대체하세요.
    item = st.selectbox("아이템", item_list)
    qty_input = st.text_input("수량 입력 (1000개 등 직접 입력)", value="1")
    
    b1, b2 = st.columns(2)
    with b1:
        if st.button("💰 매수", use_container_width=True):
            st.success(f"{item} {qty_input}개 매수 요청 완료!")
    with b2:
        if st.button("📦 매도", use_container_width=True):
            st.success(f"{item} {qty_input}개 매도 요청 완료!")

    if st.button("↩️ 슬롯 다시 고르기"):
        st.session_state.game_started = False
        st.rerun()
