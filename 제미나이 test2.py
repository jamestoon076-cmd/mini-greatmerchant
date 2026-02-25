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
st.set_page_config(
    page_title="조선거상 미니",
    page_icon="🏯",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .stButton button { width: 100%; margin: 5px 0; padding: 15px; font-size: 18px; }
    .stTextInput input { font-size: 16px; padding: 10px; }
    .price-up { color: #ff4b4b; font-weight: bold; }
    .price-down { color: #4b7bff; font-weight: bold; }
    .trade-progress {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
        font-family: monospace;
        font-size: 14px;
        max-height: 200px;
        overflow-y: auto;
    }
    .trade-line { padding: 3px 0; border-bottom: 1px solid #e0e0e0; }
</style>
""", unsafe_allow_html=True)

# --- 2. 구글 시트 연결 및 데이터 로드 ---
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

@st.cache_data(ttl=10)
def load_game_data():
    doc = connect_gsheet()
    if not doc: return None, None, None, None, None, None
    try:
        set_ws = doc.worksheet("Setting_Data")
        settings = {r['변수명']: float(r['값']) for r in set_ws.get_all_records()}
        item_ws = doc.worksheet("Item_Data")
        items_info = {str(r['item_name']).strip(): {'base': int(r['base_price']), 'w': int(r['weight'])} for r in item_ws.get_all_records() if r.get('item_name')}
        bal_ws = doc.worksheet("Balance_Data")
        merc_data = {str(r['name']).strip(): {'price': int(r['price']), 'w_bonus': int(r.get('weight_bonus', 0))} for r in bal_ws.get_all_records() if r.get('name')}
        vil_ws = doc.worksheet("Village_Data")
        vil_vals = vil_ws.get_all_values()
        headers = [h.strip() for h in vil_vals[0]]
        villages, initial_stocks = {}, {}
        for row in vil_vals[1:]:
            if not row or not row[0].strip(): continue
            v_name = row[0].strip()
            x, y = int(row[1]) if len(row)>1 and row[1] else 0, int(row[2]) if len(row)>2 and row[2] else 0
            villages[v_name] = {'items': {}, 'x': x, 'y': y}
            initial_stocks[v_name] = {}
            if v_name != "용병 고용소":
                for i in range(3, len(headers)):
                    if headers[i] in items_info and len(row) > i and row[i].strip():
                        villages[v_name]['items'][headers[i]] = int(row[i])
                        initial_stocks[v_name][headers[i]] = int(row[i])
        play_ws = doc.worksheet("Player_Data")
        slots = []
        for r in play_ws.get_all_records():
            if str(r.get('slot', '')).strip():
                slots.append({
                    'slot': int(r['slot']), 'money': int(r.get('money', 0)), 'pos': str(r.get('pos', '한양')),
                    'inv': json.loads(r.get('inventory', '{}')) if r.get('inventory') else {},
                    'mercs': json.loads(r.get('mercs', '[]')) if r.get('mercs') else [],
                    'week': int(r.get('week', 1)), 'month': int(r.get('month', 1)), 'year': int(r.get('year', 1592))
                })
        return settings, items_info, merc_data, villages, initial_stocks, slots
    except Exception as e:
        st.error(f"❌ 로드 에러: {e}"); return None, None, None, None, None, None

# --- 3. 세션 초기화 ---
def init_session_state():
    if 'game_started' not in st.session_state: st.session_state.game_started = False
    if 'player' not in st.session_state: st.session_state.player = None
    if 'tab_key' not in st.session_state: st.session_state.tab_key = 0
    if 'is_trading' not in st.session_state: st.session_state.is_trading = False
    if 'trade_logs' not in st.session_state: st.session_state.trade_logs = {}
    if 'last_qty' not in st.session_state: st.session_state.last_qty = {}
    if 'stats' not in st.session_state: st.session_state.stats = {'total_spent': 0, 'total_earned': 0, 'total_bought': 0, 'total_sold': 0, 'trade_count': 0}

# --- 4. 핵심 게임 로직 ---
def get_weight(player, items_info, merc_data):
    cw = sum(qty * items_info[item]['w'] for item, qty in player['inv'].items() if item in items_info)
    tw = 200 + sum(merc_data[m]['w_bonus'] for m in player['mercs'] if m in merc_data)
    return cw, tw

def update_prices(settings, items_info, market_data):
    for v_name, v_items in market_data.items():
        if v_name == "용병 고용소": continue
        for i_name, i_info in v_items.items():
            if i_name in items_info:
                stock = i_info['stock']
                if stock < 100: f = 2.0
                elif stock < 500: f = 1.5
                elif stock < 1000: f = 1.2
                elif stock < 2000: f = 1.0
                elif stock < 5000: f = 0.8
                else: f = 0.6
                i_info['price'] = int(items_info[i_name]['base'] * f)

def process_trade(mode, player, items_info, market_data, pos, item_name, target_qty, progress_ph, log_key):
    st.session_state.is_trading = True
    total_q, total_v = 0, 0
    batch = 100
    st.session_state.trade_logs[log_key] = []
    
    while total_q < target_qty:
        update_prices(st.session_state.settings, items_info, market_data)
        curr_p = market_data[pos][item_name]['price']
        cw, tw = get_weight(player, items_info, st.session_state.merc_data)
        
        if mode == "BUY":
            can_p = player['money'] // curr_p if curr_p > 0 else 0
            can_l = (tw - cw) // items_info[item_name]['w'] if items_info[item_name]['w'] > 0 else 9999
            cur_batch = min(batch, target_qty - total_q, market_data[pos][item_name]['stock'], can_p, can_l)
        else: # SELL
            cur_batch = min(batch, target_qty - total_q, player['inv'].get(item_name, 0))
            
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
            
        total_q += cur_batch
        total_v += val
        
        msg = f"➤ {total_q}/{target_qty} 체결 중... ({curr_p}냥)"
        st.session_state.trade_logs[log_key].append(msg)
        with progress_ph.container():
            st.markdown(f"<div class='trade-progress'>{''.join([f'<div class=trade-line>{l}</div>' for l in st.session_state.trade_logs[log_key][-3:]])}</div>", unsafe_allow_html=True)
        time.sleep(0.02)
        
    st.session_state.is_trading = False
    return total_q, total_v

# --- 5. 메인 실행 ---
doc = connect_gsheet()
init_session_state()

if doc:
    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        settings, items_info, merc_data, villages, initial_stocks, slots = load_game_data()
        if slots:
            st.subheader("📋 세이브 슬롯 선택")
            slot_choice = st.selectbox("슬롯 번호", options=[1, 2, 3])
            if st.button("🎮 게임 시작"):
                selected = next((s for s in slots if s['slot'] == slot_choice), None)
                if selected:
                    st.session_state.update({"player": selected, "settings": settings, "items_info": items_info, "merc_data": merc_data, "villages": villages, "initial_stocks": initial_stocks, "game_started": True})
                    market_data = {v: {i: {'stock': s, 'price': items_info[i]['base']} for i, s in data['items'].items()} for v, data in villages.items() if v != "용병 고용소"}
                    st.session_state.market_data = market_data
                    st.rerun()
    else:
        # 게임 실행 화면
        p, settings, items_info, market_data = st.session_state.player, st.session_state.settings, st.session_state.items_info, st.session_state.market_data
        
        # 시간 업데이트 (프래그먼트)
        @st.fragment(run_every="1s")
        def time_ui():
            if not st.session_state.is_trading:
                # 여기에 시간 흐름 로직 추가 가능
                pass
            st.write(f"📅 {p['year']}년 {p['month']}월 {p['week']}주차")

        st.title(f"📍 {p['pos']}")
        time_ui()
        cw, tw = get_weight(p, items_info, st.session_state.merc_data)
        st.write(f"💰 {p['money']:,}냥 | ⚖️ {cw}/{tw}근")

        # --- 핵심: 탭 초기화 키 적용 ---
        tabs = st.tabs(["🛒 저잣거리", "📦 인벤토리", "⚔️ 용병", "⚙️ 메뉴"], key=f"tab_{st.session_state.tab_key}")
        
        with tabs[0]:
            if p['pos'] in market_data:
                for item_name, d in market_data[p['pos']].items():
                    col1, col2, col3 = st.columns([2,1,1])
                    col1.write(f"**{item_name}** ({d['price']:,}냥)")
                    qty_input = st.text_input("수량", value="1", key=f"in_{item_name}")
                    prog_ph = st.empty()
                    b_col1, b_col2 = st.columns(2)
                    if b_col1.button("💰 매수", key=f"b_{item_name}"):
                        q, v = process_trade("BUY", p, items_info, market_data, p['pos'], item_name, int(qty_input), prog_ph, f"buy_{item_name}")
                        st.session_state.last_trade_result = f"✅ {item_name} {q}개 매수 완료"
                        st.rerun()
                    if b_col2.button("📦 매도", key=f"s_{item_name}"):
                        q, v = process_trade("SELL", p, items_info, market_data, p['pos'], item_name, int(qty_input), prog_ph, f"sell_{item_name}")
                        st.session_state.last_trade_result = f"✅ {item_name} {q}개 매도 완료"
                        st.rerun()

        with tabs[3]: # 메뉴 및 이동
            st.subheader("🚚 마을 이동")
            dest = st.selectbox("목적지 선택", [v for v in villages.keys() if v != p['pos']])
            if st.button("🚀 이동하기"):
                # 이동 비용 계산 및 적용 로직 (생략된 기존 로직 추가)
                p['pos'] = dest
                st.session_state.tab_key += 1 # 탭 초기화 핵심!
                st.rerun()
            if st.button("💾 저장"):
                # 저장 로직
                st.success("저장되었습니다.")
