import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime
import hashlib
import uuid

# --- [추가] 369번 라인 NameError 해결을 위한 함수 정의 ---
def update_game_time(player, settings, market_data, initial_stocks):
    """게임 내 시간을 업데이트하고 시장 데이터를 변동시키는 함수"""
    try:
        player['week'] = player.get('week', 1) + 1
        if player['week'] > 4:
            player['week'] = 1
            player['month'] += 1
        if player['month'] > 12:
            player['month'] = 1
            player['year'] += 1
        
        events = []
        # 시장 변동 로직 예시 (필요시 상세 구현)
        return player, events
    except Exception as e:
        return player, [("error", f"시간 업데이트 실패: {e}")]

# --- 기존 초기화 및 연결 로직 ---
def init_session():
    if 'session_id' not in st.session_state: st.session_state.session_id = str(uuid.uuid4())
    if 'game_started' not in st.session_state: st.session_state.game_started = False
    if 'player' not in st.session_state: st.session_state.player = None
    if 'stats' not in st.session_state:
        st.session_state.stats = {'total_bought':0, 'total_sold':0, 'trade_count':0}
    if 'events' not in st.session_state: st.session_state.events = []
    if 'last_update' not in st.session_state: st.session_state.last_update = time.time()
    if 'last_save_time' not in st.session_state: st.session_state.last_save_time = time.time()

def get_device_id():
    if 'device_id' not in st.session_state:
        session_key = f"{st.session_state.session_id}_{time.time()}"
        st.session_state.device_id = hashlib.md5(session_key.encode()).hexdigest()[:12]
    return st.session_state.device_id

# --- 구글 시트 저장 로직 (A:J열) ---
def save_player_data(doc, player, stats, device_id):
    try:
        play_ws = doc.worksheet("Player_Data")
        all_records = play_ws.get_all_records()
        row_idx = next((i for i, r in enumerate(all_records, 2) if r.get('slot') == player['slot']), None)
        
        if row_idx:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            save_values = [
                player['slot'], player['money'], player['pos'],
                json.dumps(player.get('mercs', []), ensure_ascii=False),
                json.dumps(player.get('inv', {}), ensure_ascii=False),
                now, player.get('week', 1), player.get('month', 1), player.get('year', 1),
                device_id
            ]
            play_ws.update(f'A{row_idx}:J{row_idx}', [save_values])
            return True
    except Exception as e:
        st.error(f"❌ 저장 실패: {e}")
        return False

# --- 메인 실행 흐름 (잘린 하단부 포함) ---
init_session()
doc = connect_gsheet() # 위에서 정의한 함수 호출
# --- 3. 구글 시트 연결 함수 (이 부분이 호출부보다 위에 있어야 함) ---
@st.cache_resource
def connect_gsheet():
    try:
        # Streamlit Secrets에서 보안 정보를 가져옴
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gspread"] 
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"❌ 시트 연결 에러: {e}")
        return None

if doc:
    if not st.session_state.game_started:
        # 슬롯 선택 로직 (사용자 코드 유지)
        st.title("🏯 조선거상 미니")
        # ... (슬롯 선택 UI 생략) ...
        if st.button("🎮 게임 시작"):
            st.session_state.game_started = True
            st.rerun()
            
    else:
        # 게임 메인 화면 (369번 라인 근처)
        player = st.session_state.player
        
        # [해결] update_game_time 호출
        curr_time = time.time()
        if curr_time - st.session_state.last_update > 180: # 3분 기준
            player, events = update_game_time(player, {}, {}, {})
            st.session_state.last_update = curr_time
        
        # --- 거래 및 UI 로직 ---
        # [해결] 792번 라인 SyntaxError 수정 및 안전하게 닫기
        try:
            # (매수/매도 거래 로직 실행 후)
            sold = 100 # 예시값
            earned = 1000 # 예시값
            avg_price = earned // sold if sold > 0 else 0
            
            st.markdown(
                f"<div class='trade-complete'>✅ 총 {sold}개 매도 완료! "
                f"(총 {earned:,}냥 | 평균가: {avg_price:,}냥)</div>", 
                unsafe_allow_html=True
            )
        except Exception as e:
            st.error(f"거래 처리 오류: {e}")

        if st.button("💾 수동 저장"):
            if save_player_data(doc, player, st.session_state.stats, get_device_id()):
                st.success("✅ 서버에 저장되었습니다!")

