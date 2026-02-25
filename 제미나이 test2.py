import streamlit as st
from streamlit_autorefresh import st_autorefresh
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime
import hashlib
import uuid
import random

# --- 1. 페이지 설정 및 스타일 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

# CSS 스타일 유지
st.markdown("""
<style>
    .stButton button { width: 100%; margin: 5px 0; padding: 15px; font-size: 18px; }
    .trade-progress { background-color: #f0f2f6; padding: 15px; border-radius: 10px; font-family: monospace; }
    .price-up { color: #ff4b4b; font-weight: bold; }
    .price-down { color: #4b7bff; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 2. 구글 시트 및 데이터 로드 (기존 함수 유지) ---
@st.cache_resource
def connect_gsheet():
    try:
        creds_info = st.secrets["gspread"]
        creds = Credentials.from_service_account_info(creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("조선거상_DB")
    except: return None

@st.cache_data(ttl=10)
def load_game_data():
    doc = connect_gsheet()
    if not doc: return None, None, None, None, None, None
    # ... (기존 로드 로직 동일하게 적용) ...
    # 사용자님의 원본 코드 로직을 따릅니다.
    return settings, items_info, merc_data, villages, initial_stocks, slots

# --- 3. 세션 초기화 (TypeError 방지의 핵심) ---
def init_session_state():
    if 'game_started' not in st.session_state: st.session_state.game_started = False
    if 'tab_key' not in st.session_state: st.session_state.tab_key = 0
    if 'is_trading' not in st.session_state: st.session_state.is_trading = False
    if 'player' not in st.session_state: st.session_state.player = None
    if 'stats' not in st.session_state:
        st.session_state.stats = {'total_bought': 0, 'total_sold': 0, 'total_spent': 0, 'total_earned': 0, 'trade_count': 0}
    if 'trade_logs' not in st.session_state: st.session_state.trade_logs = {}
    if 'last_qty' not in st.session_state: st.session_state.last_qty = {}

# --- 4. 매매 로직 (무게/돈 한도까지 루프) ---
def process_trade(mode, player, items_info, market_data, pos, item_name, target_qty, progress_ph):
    st.session_state.is_trading = True
    total_qty, total_val = 0, 0
    batch = 100
    log_key = f"{pos}_{item_name}_{time.time()}"
    st.session_state.trade_logs[log_key] = []
    
    while total_qty < target_qty:
        update_prices(st.session_state.settings, items_info, market_data)
        curr_p = market_data[pos][item_name]['price']
        cw, tw = get_weight(player, items_info, st.session_state.merc_data)
        
        if mode == "BUY":
            can_money = player['money'] // curr_p if curr_p > 0 else 0
            can_weight = (tw - cw) // items_info[item_name]['w'] if items_info[item_name]['w'] > 0 else 999
            cur_batch = min(batch, target_qty - total_qty, market_data[pos][item_name]['stock'], can_money, can_weight)
        else:
            cur_batch = min(batch, target_qty - total_qty, player['inv'].get(item_name, 0))

        if cur_batch <= 0: break
        
        val = cur_batch * curr_p
        if mode == "BUY":
            player['money'] -= val
            player['inv'][item_name] = player['inv'].get(item_name, 0) + cur_batch
            market_data[pos][item_name]['stock'] -= cur_batch
        else:
            player['money'] += val
            player['inv'][item_name] -= cur_batch
            market_data[pos][item_name]['stock'] += cur_batch
            
        total_qty += cur_batch
        total_val += val
        
        with progress_ph.container():
            st.markdown(f"🔄 체결 중: {total_qty}개 완료... (시세: {curr_p}냥)")
        time.sleep(0.02)

    st.session_state.is_trading = False
    return total_qty, total_val

# --- 5. 메인 실행 루프 ---
init_session_state()
doc = connect_gsheet()

if doc:
    if not st.session_state.game_started:
        # 로그인 화면 (기존 로직)
        settings, items_info, merc_data, villages, initial_stocks, slots = load_game_data()
        st.title("🏯 조선거상 미니")
        # ... (슬롯 선택 및 시작 버튼 로직 생략) ...
    else:
        # 게임 본편
        p = st.session_state.player
        # 시간 업데이트 프래그먼트
        @st.fragment(run_every="1s")
        def sync_time_ui():
            if not st.session_state.is_trading:
                st.session_state.player, _ = update_game_time(st.session_state.player, st.session_state.settings, st.session_state.market_data, st.session_state.initial_stocks)
            st.write(f"📅 {get_time_display(st.session_state.player)}")

        st.title(f"📍 {p['pos']}")
        sync_time_ui()
        
        # 탭 생성 (TypeError 방지용 안전 키 적용)
        t_key = st.session_state.get('tab_key', 0)
        tabs = st.tabs(["🛒 저잣거리", "📦 인벤토리", "⚔️ 용병", "⚙️ 이동"], key=f"main_tab_{t_key}")
        
        with tabs[0]: # 저잣거리
            # ... 거래 인터페이스 ...
            # 버튼 클릭 시 process_trade() 호출 후 st.rerun()
            pass

        with tabs[3]: # 이동 (탭 초기화의 핵심)
            st.subheader("🚚 이동 메뉴")
            # ... 목적지 선택 ...
            if st.button("🚀 도시 이동"):
                # 이동 비용 차감 및 위치 변경 로직
                p['pos'] = selected_dest
                # 탭 초기화 코드
                st.session_state.tab_key += 1 
                if 'last_trade_result' in st.session_state: del st.session_state.last_trade_result
                st.rerun()
