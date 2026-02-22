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
        creds_info = st.secrets["gspread"] # 스트림릿 Secrets에서 키 로드
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"❌ 연결 실패: {e}. Secrets 설정을 확인하세요!")
        return None

doc = connect_gsheet()

# --- [기능] 게임 상태 관리 (세션 스테이트) ---
# 처음 실행 시 게임 접속 상태를 'False'로 초기화하여 슬롯 선택창만 보이게 합니다.
if 'game_started' not in st.session_state:
    st.session_state.game_started = False
if 'player' not in st.session_state:
    st.session_state.player = None

# --- [화면 1] 세이브 슬롯 선택 (로그인 전) ---
if not st.session_state.game_started:
    st.title("🏯 조선거상 미니")
    st.subheader("💾 세이브 슬롯 선택")
    
    # 모바일에서 타이핑하기 편하도록 text_input 사용
    slot_input = st.text_input("슬롯 번호를 입력하세요 (1, 2, 3...)", value="1")
    
    # 엔터 대신 이 버튼을 누르면 다음 화면으로 넘어갑니다.
    if st.button("🎮 게임 시작/불러오기", use_container_width=True):
        # (실제로는 여기서 doc을 통해 시트 데이터를 읽어오는 로직이 들어갑니다)
        st.session_state.game_started = True
        st.session_state.player = {"slot": slot_input, "pos": "한양", "money": 10000} # 임시 데이터
        st.rerun() # 화면 새로고침하여 거래창으로 이동

# --- [화면 2] 물품 거래 및 이동 (로그인 후) ---
else:
    st.title("🏯 조선거상 미니")
    
    # 상단 상태바 (모바일 최적화 배치)
    p = st.session_state.player
    col1, col2 = st.columns(2)
    with col1:
        st.metric("현재 위치", p['pos'])
    with col2:
        st.metric("소지 금액", f"{p['money']:,}냥")
    
    st.divider()

    # 물품 거래 섹션 (대량 입력 가능)
    st.subheader("🛒 물품 거래")
    item = st.selectbox("물건 선택", ["쌀", "고기", "약초"]) # 예시
    
    # [핵심] 1000개든 뭐든 직접 타이핑하는 칸
    qty_str = st.text_input("수량 입력 (숫자만 타이핑)", value="1")
    
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("💰 매수하기", use_container_width=True):
            try:
                qty = int(qty_str)
                st.success(f"{item} {qty}개 매수 완료!")
            except:
                st.error("숫자를 입력하세요.")
                
    with btn_col2:
        if st.button("📦 매도하기", use_container_width=True):
            try:
                qty = int(qty_str)
                st.success(f"{item} {qty}개 매도 완료!")
            except:
                st.error("숫자를 입력하세요.")

    st.divider()
    
    # 로그아웃(슬롯 재선택) 버튼
    if st.button("↩️ 다른 슬롯 선택하기"):
        st.session_state.game_started = False
        st.rerun()
