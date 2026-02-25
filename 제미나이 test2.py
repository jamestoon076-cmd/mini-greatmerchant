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

# CSS 스타일 (거래 로그 및 가격 색상)
st.markdown("""
<style>
    .stButton button { width: 100%; margin: 5px 0; padding: 10px; font-size: 16px; }
    .price-up { color: #ff4b4b; font-weight: bold; }
    .price-down { color: #4b7bff; font-weight: bold; }
    .trade-progress { background-color: #f0f2f6; padding: 10px; border-radius: 10px; font-family: monospace; font-size: 13px; max-height: 150px; overflow-y: auto; }
</style>
""", unsafe_allow_html=True)

# --- 2. 데이터 연결 및 로드 (캐싱) ---
@st.cache_resource
def connect_gsheet():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gspread"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"❌ 시트 연결 에러: {e}")
        return None

@st.cache_data(ttl=60)
def load_game_data():
    doc = connect_gsheet()
    if not doc: return None
    
    # [설정/아이템/용병/마을/플레이어 데이터를 가져오는 기존 로직 동일]
    # (코드 간결화를 위해 세부 gspread 로직은 기존 내용 유지로 간주합니다)
    # ... (데이터 로드 로직 생략) ...
    return settings, items_info, merc_data, villages, initial_stocks, slots

# --- 3. 세션 초기화 ---
def init_session_state():
    if 'game_started' not in st.session_state: st.session_state.game_started = False
    if 'player' not in st.session_state: st.session_state.player = None
    if 'is_trading' not in st.session_state: st.session_state.is_trading = False
    if 'tab_key' not in st.session_state: st.session_state.tab_key = 0
    if 'trade_logs' not in st.session_state: st.session_state.trade_logs = {}
    if 'stats' not in st.session_state:
        st.session_state.stats = {'total_bought': 0, 'total_sold': 0, 'total_spent': 0, 'total_earned': 0, 'trade_count': 0}

# --- 4. 핵심 로직 함수 ---

def get_weight(player, items_info, merc_data):
    cw = sum(qty * items_info[item]['w'] for item, qty in player['inv'].items() if item in items_info)
    tw = 200 + sum(merc_data[m]['w_bonus'] for m in player['mercs'] if m in merc_data)
    return cw, tw

def update_prices(settings, items_info, market_data):
    for v_name, v_items in market_data.items():
        for i_name, i_info in v_items.items():
            if i_name in items_info:
                base = items_info[i_name]['base']
                stock = i_info['stock']
                # 재고 기반 가격 계수 (사용자 요청 로직)
                if stock < 100: f = 2.0
                elif stock < 500: f = 1.5
                elif stock < 1000: f = 1.2
                elif stock < 2000: f = 1.0
                elif stock < 5000: f = 0.8
                else: f = 0.6
                i_info['price'] = int(base * f)

def process_trade(mode, player, items_info, market_data, pos, item_name, target_qty, placeholder):
    """매수/매도 통합 처리 (무게/돈 한도까지 루프 체결)"""
    st.session_state.is_trading = True
    total_qty, total_val = 0, 0
    item_w = items_info[item_name]['w']
    batch = 100
    
    log_key = f"{mode}_{item_name}"
    st.session_state.trade_logs[log_key] = []

    while total_qty < target_qty:
        update_prices(st.session_state.settings, items_info, market_data)
        curr_p = market_data[pos][item_name]['price']
        cw, tw = get_weight(player, items_info, st.session_state.merc_data)
        
        if mode == "BUY":
            can_pay = player['money'] // curr_p if curr_p > 0 else 0
            can_load = (tw - cw) // item_w if item_w > 0 else 0
            current_batch = min(batch, target_qty - total_qty, market_data[pos][item_name]['stock'], can_pay, can_load)
        else: # SELL
            current_batch = min(batch, target_qty - total_qty, player['inv'].get(item_name, 0))

        if current_batch <= 0: break
        
        # 데이터 반영
        step_val = current_batch * curr_p
        if mode == "BUY":
            player['money'] -= step_val
            player['inv'][item_name] = player['inv'].get(item_name, 0) + current_batch
            market_data[pos][item_name]['stock'] -= current_batch
        else:
            player['money'] += step_val
            player['inv'][item_name] -= current_batch
            market_data[pos][item_name]['stock'] += current_batch
            
        total_qty += current_batch
        total_val += step_val
        
        # 실시간 로그 UI
        log_msg = f"➤ {total_qty}개 체결 중... (시세: {curr_p}냥)"
        st.session_state.trade_logs[log_key].append(log_msg)
        with placeholder.container():
            st.markdown(f"<div class='trade-progress'>{'<br>'.join(st.session_state.trade_logs[log_key][-3:])}</div>", unsafe_allow_html=True)
        time.sleep(0.05)

    st.session_state.is_trading = False
    return total_qty, total_val

# --- 5. UI 프래그먼트 (시간) ---
@st.fragment(run_every="1s")
def sync_time_ui():
    if st.session_state.get('is_trading', False):
        st.caption("🔄 거래 중 시간 정지")
        return

    # 시간 업데이트 로직 호출 (기존 update_game_time)
    # [시간/재고 초기화 로직 수행...]
    st.write(f"📅 {st.session_state.player['year']}년 {st.session_state.player['month']}월")

# --- 6. 메인 화면 ---
init_session_state()
# (로그인/슬롯 선택 로직 생략)

if st.session_state.game_started:
    p = st.session_state.player
    
    st.title(f"🏯 {p['pos']}")
    sync_time_ui()
    
    cw, tw = get_weight(p, st.session_state.items_info, st.session_state.merc_data)
    c1, c2 = st.columns(2)
    c1.metric("💰 소지금", f"{p['money']:,}냥")
    c2.metric("⚖️ 무게", f"{cw}/{tw}근")

    # --- 핵심 1: 탭 초기화 (key에 tab_key 사용) ---
    tabs = st.tabs(["🛒 저잣거리", "📦 인벤토리", "⚔️ 용병", "⚙️ 이동"], key=f"main_tabs_{st.session_state.tab_key}")

    with tabs[0]: # 저잣거리
        # [아이템 리스트 출력 및 매매 버튼]
        # if 매수 버튼 클릭:
        #    process_trade("BUY", ...) -> st.rerun()
        pass

    with tabs[3]: # 이동
        st.subheader("🚚 마을 이동")
        # 마을 선택 셀렉트박스 등...
        if st.button("🚀 이동 실행"):
            # 이동 로직 처리
            # p['pos'] = 새 마을
            # p['money'] -= 비용
            
            # --- 핵심 2: 이동 시 탭 초기화 로직 ---
            st.session_state.tab_key += 1 # 키를 변경하여 0번 탭(저잣거리)으로 강제 리셋
            if 'last_trade_result' in st.session_state: del st.session_state.last_trade_result
            st.success(f"{dest}로 이동 완료!")
            st.rerun()
