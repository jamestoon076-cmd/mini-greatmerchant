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

# 모바일 최적화 CSS (기존 유지)
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
</style>
""", unsafe_allow_html=True)

# --- 2. 구글 시트 연결 및 데이터 함수 (기존 유지) ---
@st.cache_resource
def connect_gsheet():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gspread"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        return gspread.authorize(creds).open("조선거상_DB")
    except: return None

@st.cache_data(ttl=10)
def load_game_data():
    doc = connect_gsheet()
    if not doc: return None, None, None, None, None, None
    try:
        # Setting_Data
        set_ws = doc.worksheet("Setting_Data")
        settings = {r['변수명']: float(r['값']) for r in set_ws.get_all_records()}
        # Item_Data
        item_ws = doc.worksheet("Item_Data")
        items_info = {str(r['item_name']).strip(): {'base': int(r['base_price']), 'w': int(r['weight'])} for r in item_ws.get_all_records() if r.get('item_name')}
        # Balance_Data (용병)
        bal_ws = doc.worksheet("Balance_Data")
        merc_data = {str(r['name']).strip(): {'price': int(r['price']), 'w_bonus': int(r.get('weight_bonus', 0))} for r in bal_ws.get_all_records() if r.get('name')}
        # Village_Data (마을/재고)
        vil_ws = doc.worksheet("Village_Data")
        vil_vals = vil_ws.get_all_values()
        headers = [h.strip() for h in vil_vals[0]]
        villages, initial_stocks = {}, {}
        for row in vil_vals[1:]:
            v_name = row[0].strip()
            if not v_name: continue
            villages[v_name] = {'items': {}, 'x': int(row[1]), 'y': int(row[2])}
            initial_stocks[v_name] = {}
            if v_name != "용병 고용소":
                for i in range(3, len(headers)):
                    if headers[i] in items_info and len(row) > i and row[i].strip():
                        val = int(row[i])
                        villages[v_name]['items'][headers[i]] = val
                        initial_stocks[v_name][headers[i]] = val
        # Player_Data
        play_ws = doc.worksheet("Player_Data")
        slots = [{
            'slot': int(r['slot']), 'money': int(r.get('money', 0)), 'pos': str(r.get('pos', '한양')),
            'inv': json.loads(r.get('inventory', '{}')) if r.get('inventory') else {},
            'mercs': json.loads(r.get('mercs', '[]')) if r.get('mercs') else [],
            'week': int(r.get('week', 1)), 'month': int(r.get('month', 1)), 'year': int(r.get('year', 1592)),
            'device_id': str(r.get('device_id', ''))
        } for r in play_ws.get_all_records()]
        return settings, items_info, merc_data, villages, initial_stocks, slots
    except: return None, None, None, None, None, None

def save_player_data(doc, player, stats, device_id):
    try:
        ws = doc.worksheet("Player_Data")
        data = ws.get_all_records()
        row_idx = -1
        for i, r in enumerate(data):
            if int(r['slot']) == player['slot']:
                row_idx = i + 2
                break
        if row_idx != -1:
            ws.update_cell(row_idx, 2, player['money'])
            ws.update_cell(row_idx, 3, player['pos'])
            ws.update_cell(row_idx, 4, json.dumps(player['inv'], ensure_ascii=False))
            ws.update_cell(row_idx, 5, json.dumps(player['mercs'], ensure_ascii=False))
            ws.update_cell(row_idx, 6, player['week'])
            ws.update_cell(row_idx, 7, player['month'])
            ws.update_cell(row_idx, 8, player['year'])
            ws.update_cell(row_idx, 9, device_id)
            return True
    except: return False

# --- 3. 유틸리티 함수 (무게, 시간, 가격) ---
def get_weight(player, items_info, merc_data):
    current_w = sum(qty * items_info[item]['w'] for item, qty in player['inv'].items() if item in items_info)
    total_w = 200 + sum(merc_data[m]['w_bonus'] for m in player['mercs'] if m in merc_data)
    return current_w, total_w

def get_time_display(player):
    months = ["1월","2월","3월","4월","5월","6월","7월","8월","9월","10월","11월","12월"]
    return f"{player['year']}년 {months[player['month']-1]} {player['week']}주차"

def update_prices(settings, items_info, market_data, initial_stocks):
    for v_name, items in market_data.items():
        if v_name == "용병 고용소": continue
        for i_name, i_data in items.items():
            base = items_info[i_name]['base']
            stock = i_data['stock']
            if stock < 100: factor = 2.0
            elif stock < 500: factor = 1.5
            elif stock < 1000: factor = 1.2
            elif stock < 2000: factor = 1.0
            elif stock < 5000: factor = 0.8
            else: factor = 0.6
            i_data['price'] = int(base * factor)

def update_game_time(player, settings, market_data, initial_stocks):
    if st.session_state.get('is_trading', False): return player, [] # 매매 중 시간 정지
    
    now = time.time()
    if 'last_time_update' not in st.session_state:
        st.session_state.last_time_update = now
        return player, []
    
    sec_per_month = int(settings.get('seconds_per_month', 180))
    sec_per_week = sec_per_month / 4
    elapsed = now - st.session_state.last_time_update
    weeks_passed = int(elapsed // sec_per_week)
    
    if weeks_passed > 0:
        for _ in range(weeks_passed):
            player['week'] += 1
            if player['week'] > 4:
                player['week'] = 1; player['month'] += 1
                # 매달 재고 초기화
                for v_name, stocks in initial_stocks.items():
                    if v_name in market_data:
                        for i_name, s_val in stocks.items():
                            market_data[v_name][i_name]['stock'] = s_val
                if player['month'] > 12:
                    player['month'] = 1; player['year'] += 1
        st.session_state.last_time_update += weeks_passed * sec_per_week
    return player, []

# --- 4. 매매 핵심 함수 (수정본: 무게 한도 끝까지 체결) ---
def process_buy(player, items_info, market_data, pos, item_name, qty, progress_placeholder, log_key):
    st.session_state.is_trading = True
    total_bought, total_spent = 0, 0
    batch_size = 100
    st.session_state.trade_logs[log_key] = []
    item_w = items_info[item_name].get('w', 1)

    while total_bought < qty:
        update_prices(st.session_state.settings, items_info, market_data, st.session_state.initial_stocks)
        target = market_data[pos][item_name]
        cw, tw = get_weight(player, items_info, st.session_state.merc_data)
        
        can_pay = player['money'] // target['price'] if target['price'] > 0 else 0
        can_load = int((tw - cw) // item_w) if item_w > 0 else 999999
        
        # 100개씩 끊되, 남은 주문량/재고/돈/무게 중 가장 작은 값만큼 매수
        batch = min(batch_size, qty - total_bought, target['stock'], can_pay, can_load)
        if batch <= 0: break

        cost = batch * target['price']
        player['money'] -= cost
        total_spent += cost
        player['inv'][item_name] = player['inv'].get(item_name, 0) + batch
        target['stock'] -= batch
        total_bought += batch

        log_msg = f"➤ {total_bought}/{qty} 구매 중... (현재가: {target['price']}냥)"
        st.session_state.trade_logs[log_key].append(log_msg)
        with progress_placeholder.container():
            for log in st.session_state.trade_logs[log_key][-5:]:
                st.markdown(f"<div class='trade-line'>{log}</div>", unsafe_allow_html=True)
        time.sleep(0.02)

    if total_bought > 0:
        st.session_state.last_trade_result = f"✅ {item_name} {total_bought}개 매수 완료! (평균가: {total_spent//total_bought if total_bought>0 else 0}냥)"
    st.session_state.is_trading = False
    return total_bought, total_spent

def process_sell(player, items_info, market_data, pos, item_name, qty, progress_placeholder, log_key):
    st.session_state.is_trading = True
    total_sold, total_earned = 0, 0
    batch_size = 100
    st.session_state.trade_logs[log_key] = []
    
    while total_sold < qty:
        update_prices(st.session_state.settings, items_info, market_data, st.session_state.initial_stocks)
        target = market_data[pos][item_name]
        my_stock = player['inv'].get(item_name, 0)
        
        batch = min(batch_size, qty - total_sold, my_stock)
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
        st.session_state.last_trade_result = f"✅ {item_name} {total_sold}개 매도 완료! (수익: {total_earned:,}냥)"
    st.session_state.is_trading = False
    return total_sold, total_earned

# --- 5. 초기화 및 메인 로직 ---
if 'game_started' not in st.session_state: st.session_state.game_started = False
if 'trade_logs' not in st.session_state: st.session_state.trade_logs = {}
if 'tab_key' not in st.session_state: st.session_state.tab_key = 0
if 'is_trading' not in st.session_state: st.session_state.is_trading = False
if 'device_id' not in st.session_state: st.session_state.device_id = str(uuid.uuid4())

doc = connect_gsheet()
if doc:
    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        settings, items_info, merc_data, villages, initial_stocks, slots = load_game_data()
        
        if slots:
            slot_no = st.selectbox("슬롯 선택", [1, 2, 3])
            if st.button("🎮 게임 시작", use_container_width=True):
                player = next((s for s in slots if s['slot'] == slot_no), None)
                if player:
                    st.session_state.player = player
                    st.session_state.settings = settings
                    st.session_state.items_info = items_info
                    st.session_state.merc_data = merc_data
                    st.session_state.villages = villages
                    st.session_state.initial_stocks = initial_stocks
                    st.session_state.last_time_update = time.time()
                    
                    # 마켓 데이터 초기화
                    m_data = {}
                    for v_name, v_info in villages.items():
                        if v_name == "용병 고용소": continue
                        m_data[v_name] = {i_name: {'stock': s_val, 'price': items_info[i_name]['base']} 
                                         for i_name, s_val in v_info['items'].items()}
                    st.session_state.market_data = m_data
                    st.session_state.game_started = True
                    st.rerun()
    else:
        # 게임 실행 중
        player = st.session_state.player
        settings = st.session_state.settings
        items_info = st.session_state.items_info
        merc_data = st.session_state.merc_data
        market_data = st.session_state.market_data
        initial_stocks = st.session_state.initial_stocks
        villages = st.session_state.villages

        # 시간 및 가격 업데이트
        player, _ = update_game_time(player, settings, market_data, initial_stocks)
        update_prices(settings, items_info, market_data, initial_stocks)
        cw, tw = get_weight(player, items_info, merc_data)

        # 상단 UI
        st.title(f"🏯 {player['pos']}")
        if 'last_trade_result' in st.session_state and st.session_state.last_trade_result:
            st.success(st.session_state.last_trade_result)
        
        m_col1, m_col2 = st.columns(2)
        m_col1.metric("💰 소지금", f"{player['money']:,}냥")
        m_col2.metric("⚖️ 무게", f"{cw}/{tw}근")

        # 시간 프래그먼트
        @st.fragment(run_every="1s")
        def sync_time_ui():
            if st.session_state.get('is_trading', False): return
            st.session_state.player, _ = update_game_time(st.session_state.player, st.session_state.settings, st.session_state.market_data, st.session_state.initial_stocks)
            elapsed = time.time() - st.session_state.last_time_update
            sec_per_week = settings.get('seconds_per_month', 180) / 4
            rem = max(0, int(sec_per_week - elapsed))
            c1, c2 = st.columns(2)
            c1.metric("📅 시간", get_time_display(st.session_state.player))
            c2.metric("⏰ 다음 주", f"{rem}초")
        sync_time_ui()

        # 📑 탭 구성 (수정본: Key를 통한 강제 초기화)
        t_key = st.session_state.tab_key
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 저잣거리", "🎒 주머니", "⚔️ 용병", "📊 통계", "⚙️ 이동"], key=f"tabs_{t_key}")

        with tab1: # 저잣거리
            if player['pos'] in market_data:
                for name, d in market_data[player['pos']].items():
                    with st.container():
                        st.markdown(f"### {name}")
                        col1, col2, col3 = st.columns([2,1,1])
                        col1.write(f"가격: **{d['price']:,}냥**")
                        col2.write(f"재고: **{d['stock']}**")
                        max_b = min(player['money']//d['price'] if d['price']>0 else 0, int((tw-cw)//items_info[name]['w']))
                        col3.write(f"가능: **{max_b}**")
                        
                        col_in, col_b, col_s = st.columns([2,1,1])
                        qty_val = col_in.text_input("수량", value="1", key=f"input_{name}")
                        prog_ph = st.empty()
                        
                        if col_b.button("💰 매수", key=f"btn_b_{name}"):
                            process_buy(player, items_info, market_data, player['pos'], name, int(qty_val), prog_ph, f"log_{name}")
                            st.rerun()
                        if col_s.button("📦 매도", key=f"btn_s_{name}"):
                            process_sell(player, items_info, market_data, player['pos'], name, int(qty_val), prog_ph, f"log_{name}")
                            st.rerun()
                        st.divider()
            else:
                st.info("이곳에는 저잣거리가 없습니다.")

        with tab2: # 주머니 (인벤토리)
            st.subheader("🎒 내 주머니")
            if player['inv']:
                for item, qty in list(player['inv'].items()):
                    if qty > 0:
                        st.write(f"{item}: {qty}개 ({items_info[item]['w'] * qty}근)")
            else:
                st.write("비어 있습니다.")

        with tab3: # 용병
            st.subheader("⚔️ 용병단")
            st.write(f"현재 용병: {', '.join(player['mercs']) if player['mercs'] else '없음'}")
            if player['pos'] == "용병 고용소":
                for m_name, m_info in merc_data.items():
                    if m_name not in player['mercs']:
                        if st.button(f"{m_name} 고용 ({m_info['price']:,}냥 | 무게+{m_info['w_bonus']}근)"):
                            if player['money'] >= m_info['price']:
                                player['money'] -= m_info['price']
                                player['mercs'].append(m_name)
                                st.success(f"{m_name}을(를) 고용했습니다!")
                                st.rerun()
                            else: st.error("돈이 부족합니다.")

        with tab4: # 통계 및 저장
            st.subheader("📊 상단 기록")
            if st.button("💾 게임 저장", use_container_width=True):
                if save_player_data(doc, player, None, st.session_state.device_id):
                    st.success("데이터가 안전하게 저장되었습니다!")
            
            if st.button("🚪 메인 화면으로", use_container_width=True):
                st.session_state.game_started = False
                st.rerun()

        with tab5: # 이동 (수정본: 이동 시 탭 초기화 로직)
            st.subheader("⚙️ 마을 이동")
            curr_v = villages[player['pos']]
            move_options = {}
            for v_name, v_info in villages.items():
                if v_name != player['pos']:
                    dist = math.sqrt((curr_v['x']-v_info['x'])**2 + (curr_v['y']-v_info['y'])**2)
                    cost = int(dist * settings.get('travel_cost', 15))
                    move_options[f"{v_name} (비용: {cost:,}냥)"] = (v_name, cost)
            
            selected = st.selectbox("목적지 선택", list(move_options.keys()))
            if st.button("🚀 이동하기", use_container_width=True):
                dest, cost = move_options[selected]
                if player['money'] >= cost:
                    # 1. 이전 도시 로그 삭제
                    if 'last_trade_result' in st.session_state:
                        del st.session_state['last_trade_result']
                    
                    # 2. 이동 처리
                    player['money'] -= cost
                    player['pos'] = dest
                    
                    # 3. ⭐ 탭 초기화 핵심: Key 변경
                    st.session_state.tab_key = st.session_state.get('tab_key', 0) + 1
                    
                    st.success(f"✅ {dest}(으)로 이동했습니다!")
                    st.rerun()
                else:
                    st.error("이동 비용이 부족합니다.")
