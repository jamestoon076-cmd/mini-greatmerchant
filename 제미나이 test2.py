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

# 모바일 최적화 CSS
st.markdown("""
<style>
    .stButton button { width: 100%; margin: 5px 0; padding: 15px; font-size: 18px; }
    .stTextInput input { font-size: 16px; padding: 10px; }
    div[data-testid="column"] { gap: 10px; }
    .price-up { color: #ff4b4b; font-weight: bold; }
    .price-down { color: #4b7bff; font-weight: bold; }
    .price-same { color: #808080; }
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
    .trade-complete {
        color: #00a65a; font-weight: bold; font-size: 16px;
        margin-top: 10px; padding: 10px; background-color: #f0fff0; border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. 구글 시트 연결 함수 ---
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

# --- 3. 데이터 로드 함수 ---
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
        villages, initial_stocks, seen = {}, {}, set()
        for row in vil_vals[1:]:
            v_name = row[0].strip()
            if not v_name or v_name in seen: continue
            seen.add(v_name)
            villages[v_name] = {'items': {}, 'x': int(row[1]) if len(row)>1 else 0, 'y': int(row[2]) if len(row)>2 else 0}
            initial_stocks[v_name] = {}
            if v_name != "용병 고용소":
                for i in range(3, len(headers)):
                    if headers[i] in items_info and len(row) > i and row[i].strip():
                        val = int(row[i])
                        villages[v_name]['items'][headers[i]] = val
                        initial_stocks[v_name][headers[i]] = val
        play_ws = doc.worksheet("Player_Data")
        slots = [{
            'slot': int(r['slot']), 'money': int(r.get('money', 0)), 'pos': str(r.get('pos', '한양')),
            'inv': json.loads(r.get('inventory', '{}')) if r.get('inventory') else {},
            'mercs': json.loads(r.get('mercs', '[]')) if r.get('mercs') else [],
            'week': int(r.get('week', 1)), 'month': int(r.get('month', 1)), 'year': int(r.get('year', 1592))
        } for r in play_ws.get_all_records() if str(r.get('slot', '')).strip()]
        return settings, items_info, merc_data, villages, initial_stocks, slots
    except Exception as e:
        st.error(f"❌ 데이터 로드 에러: {e}")
        return None, None, None, None, None, None

# --- 4. 세션 초기화 ---
def init_session_state():
    if 'game_started' not in st.session_state: st.session_state.game_started = False
    if 'trade_logs' not in st.session_state: st.session_state.trade_logs = {}
    if 'tab_key' not in st.session_state: st.session_state.tab_key = 0
    if 'is_trading' not in st.session_state: st.session_state.is_trading = False
    if 'last_qty' not in st.session_state: st.session_state.last_qty = {}
    if 'stats' not in st.session_state: st.session_state.stats = {'total_bought':0, 'total_sold':0, 'total_spent':0, 'total_earned':0, 'trade_count':0}

# --- 5. 시간 및 무게 시스템 ---
def update_game_time(player, settings, market_data, initial_stocks):
    if st.session_state.get('is_trading', False): return player, [] # 거래 중 시간 정지
    current_time = time.time()
    if 'last_time_update' not in st.session_state:
        st.session_state.last_time_update = current_time
        return player, []
    
    sec_per_month = int(settings.get('seconds_per_month', 180))
    sec_per_week = sec_per_month / 4
    elapsed = current_time - st.session_state.last_time_update
    weeks_passed = int(elapsed // sec_per_week)
    
    if weeks_passed > 0:
        for _ in range(weeks_passed):
            player['week'] += 1
            if player['week'] > 4:
                player['week'] = 1; player['month'] += 1
                for v_name, items in initial_stocks.items():
                    if v_name in market_data:
                        for i_name, stock in items.items():
                            if i_name in market_data[v_name]: market_data[v_name][i_name]['stock'] = stock
                if player['month'] > 12: player['month'] = 1; player['year'] += 1
        st.session_state.last_time_update += weeks_passed * sec_per_week
        st.session_state.event_display = {"message": f"🌟 {player['year']}년 {player['month']}월 {player['week']}주차 소식!", "time": time.time()}
    return player, []

def get_weight(player, items_info, merc_data):
    cw = sum(qty * items_info[item]['w'] for item, qty in player['inv'].items() if item in items_info)
    tw = 200 + sum(merc_data[m]['w_bonus'] for m in player['mercs'] if m in merc_data)
    return cw, tw

def update_prices(settings, items_info, market_data, initial_stocks=None):
    for v_name, v_data in market_data.items():
        if v_name == "용병 고용소": continue
        for i_name, i_info in v_data.items():
            if i_name in items_info:
                base, stock = items_info[i_name]['base'], i_info['stock']
                if stock < 100: f = 2.0
                elif stock < 500: f = 1.5
                elif stock < 1000: f = 1.2
                elif stock < 2000: f = 1.0
                elif stock < 5000: f = 0.8
                else: f = 0.6
                i_info['price'] = int(base * f)

# --- 6. 매매 핵심 로직 (무게 한도 무한 체결) ---
def process_buy(player, items_info, market_data, pos, item_name, qty, progress_placeholder, log_key):
    st.session_state.is_trading = True
    total_bought, total_spent = 0, 0
    st.session_state.trade_logs[log_key] = []
    item_w = items_info[item_name].get('w', 1)

    while total_bought < qty:
        update_prices(st.session_state.settings, items_info, market_data, st.session_state.initial_stocks)
        target = market_data[pos][item_name]
        cw, tw = get_weight(player, items_info, st.session_state.merc_data)
        
        can_pay = player['money'] // target['price'] if target['price'] > 0 else 0
        can_load = int((tw - cw) // item_w) if item_w > 0 else 999999
        
        batch = min(100, qty - total_bought, target['stock'], can_pay, can_load)
        if batch <= 0: break

        cost = batch * target['price']
        player['money'] -= cost
        total_spent += cost
        player['inv'][item_name] = player['inv'].get(item_name, 0) + batch
        target['stock'] -= batch
        total_bought += batch

        log_msg = f"➤ {total_bought}/{qty} 구매 중... (현재가: {target['price']}냥 | 남은무게: {tw-(cw+batch*item_w)}근)"
        st.session_state.trade_logs[log_key].append(log_msg)
        with progress_placeholder.container():
            for log in st.session_state.trade_logs[log_key][-5:]:
                st.markdown(f"<div class='trade-line'>{log}</div>", unsafe_allow_html=True)
        time.sleep(0.02)

    if total_bought > 0:
        st.session_state.last_trade_result = f"✅ {item_name} {total_bought}개 매수 완료! (평균가: {total_spent//total_bought}냥)"
    st.session_state.is_trading = False
    return total_bought, total_spent

def process_sell(player, items_info, market_data, pos, item_name, qty, progress_placeholder, log_key):
    st.session_state.is_trading = True
    total_sold, total_earned = 0, 0
    st.session_state.trade_logs[log_key] = []
    
    while total_sold < qty:
        update_prices(st.session_state.settings, items_info, market_data, st.session_state.initial_stocks)
        target = market_data[pos][item_name]
        my_stock = player['inv'].get(item_name, 0)
        
        batch = min(100, qty - total_sold, my_stock)
        if batch <= 0: break
            
        income = batch * target['price']
        player['money'] += income
        total_earned += income
        player['inv'][item_name] -= batch
        target['stock'] += batch
        total_sold += batch
        
        log_msg = f"➤ {total_sold}/{qty} 판매 중... (체결가: {target['price']}냥)"
        st.session_state.trade_logs[log_key].append(log_msg)
        with progress_placeholder.container():
            for log in st.session_state.trade_logs[log_key][-5:]:
                st.markdown(f"<div class='trade-line'>{log}</div>", unsafe_allow_html=True)
        time.sleep(0.02)

    if total_sold > 0:
        st.session_state.last_trade_result = f"✅ {item_name} {total_sold}개 판매 완료! (수익: {total_earned:,}냥)"
    st.session_state.is_trading = False
    return total_sold, total_earned

# --- 7. 메인 실행부 ---
init_session_state()
doc = connect_gsheet()

if doc:
    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        settings, items_info, merc_data, villages, initial_stocks, slots = load_game_data()
        if slots:
            slot_choice = st.selectbox("슬롯 번호", [1, 2, 3])
            if st.button("🎮 게임 시작", use_container_width=True):
                selected = next((s for s in slots if s['slot'] == slot_choice), None)
                if selected:
                    st.session_state.update({"player":selected, "settings":settings, "items_info":items_info, 
                                           "merc_data":merc_data, "villages":villages, "initial_stocks":initial_stocks,
                                           "last_time_update":time.time(), "game_started":True})
                    m_data = {v: {i: {'stock': s, 'price': items_info[i]['base']} for i, s in d['items'].items()} 
                             for v, d in villages.items() if v != "용병 고용소"}
                    st.session_state.market_data = m_data
                    st.rerun()
    else:
        player = st.session_state.player
        settings, items_info, merc_data, market_data, initial_stocks, villages = st.session_state.settings, st.session_state.items_info, st.session_state.merc_data, st.session_state.market_data, st.session_state.initial_stocks, st.session_state.villages
        
        player, _ = update_game_time(player, settings, market_data, initial_stocks)
        update_prices(settings, items_info, market_data, initial_stocks)
        cw, tw = get_weight(player, items_info, merc_data)

        st.title(f"🏯 {player['pos']}")
        if 'last_trade_result' in st.session_state: st.success(st.session_state.last_trade_result)
        
        t_col1, t_col2 = st.columns(2)
        t_col1.metric("💰 소지금", f"{player['money']:,}냥")
        t_col2.metric("⚖️ 무게", f"{cw}/{tw}근")

        @st.fragment(run_every="1s")
        def sync_time_ui():
            if st.session_state.get('is_trading', False): return
            st.session_state.player, _ = update_game_time(st.session_state.player, st.session_state.settings, st.session_state.market_data, st.session_state.initial_stocks)
            elapsed = time.time() - st.session_state.last_time_update
            rem = max(0, int((int(settings.get('seconds_per_month', 180))/4) - elapsed))
            c1, c2 = st.columns(2)
            month_names = ["1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"]
            c1.metric("📅 시간", f"{player['year']}년 {month_names[player['month']-1]} {player['week']}주차")
            c2.metric("⏰ 다음 주", f"{rem}초")
        sync_time_ui()

        # 📑 탭 구성 (TypeError 해결: key 부여)
        t_key = st.session_state.tab_key
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 저잣거리", "📦 인벤토리", "⚔️ 용병", "📊 통계", "⚙️ 이동"], key=f"tabs_{t_key}")

        with tab1: # 거래 탭
            if player['pos'] in market_data:
                for name, d in market_data[player['pos']].items():
                    with st.container():
                        st.markdown(f"**{name}**")
                        col1, col2, col3 = st.columns([2,1,1])
                        col1.write(f"💰 {d['price']:,}냥"); col2.write(f"📦 {d['stock']}개")
                        max_buy = min(player['money']//d['price'], (tw-cw)//items_info[name]['w'], d['stock'])
                        col3.write(f"⚡ {max_buy}개")
                        
                        col_a, col_b, col_c = st.columns([2,1,1])
                        qty_input = col_a.text_input("수량", value="1", key=f"q_{name}")
                        prog_ph = st.empty()
                        
                        if col_b.button("💰 매수", key=f"b_{name}"):
                            process_buy(player, items_info, market_data, player['pos'], name, int(qty_input), prog_ph, f"log_{name}")
                            st.rerun()
                        if col_c.button("📦 매도", key=f"s_{name}"):
                            process_sell(player, items_info, market_data, player['pos'], name, int(qty_input), prog_ph, f"log_{name}")
                            st.rerun()
                        st.divider()

        with tab5: # 이동 및 초기화
            curr_v = villages[player['pos']]
            move_options = {f"{t} (💰 {int(math.sqrt((curr_v['x']-villages[t]['x'])**2+(curr_v['y']-villages[t]['y'])**2)*settings.get('travel_cost', 15)):,}냥)": (t, int(math.sqrt((curr_v['x']-villages[t]['x'])**2+(curr_v['y']-villages[t]['y'])**2)*settings.get('travel_cost', 15))) for t in villages if t != player['pos']}
            selected = st.selectbox("목적지", list(move_options.keys()))
            if st.button("🚀 이동", use_container_width=True):
                dest, cost = move_options[selected]
                if player['money'] >= cost:
                    player['money'] -= cost; player['pos'] = dest
                    if 'last_trade_result' in st.session_state: del st.session_state['last_trade_result']
                    st.session_state.tab_key += 1 # 탭 초기화 핵심
                    st.success(f"✅ {dest} 이동 완료!"); st.rerun()
                else: st.error("❌ 잔액 부족")
