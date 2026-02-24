import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime
import hashlib
import uuid
import random
from streamlit_autorefresh import st_autorefresh  # 라이브러리 추가 필요

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
    .trade-line {
        padding: 3px 0;
        border-bottom: 1px solid #e0e0e0;
    }
    .trade-complete {
        color: #00a65a;
        font-weight: bold;
        font-size: 16px;
        margin-top: 10px;
        padding: 10px;
        background-color: #f0fff0;
        border-radius: 5px;
    }
    .event-message {
        background-color: #e8f4fd;
        padding: 10px;
        border-radius: 5px;
        margin: 5px 0;
        text-align: center;
        font-weight: bold;
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
    if not doc:
        return None, None, None, None, None, None
    
    try:
        set_ws = doc.worksheet("Setting_Data")
        settings = {r['변수명']: float(r['값']) for r in set_ws.get_all_records()}
        
        item_ws = doc.worksheet("Item_Data")
        items_info = {}
        for r in item_ws.get_all_records():
            if r.get('item_name'):
                name = str(r['item_name']).strip()
                items_info[name] = {'base': int(r['base_price']), 'w': int(r['weight'])}
        
        bal_ws = doc.worksheet("Balance_Data")
        merc_data = {}
        for r in bal_ws.get_all_records():
            if r.get('name'):
                name = str(r['name']).strip()
                merc_data[name] = {'price': int(r['price']), 'w_bonus': int(r.get('weight_bonus', 0))}
        
        vil_ws = doc.worksheet("Village_Data")
        vil_vals = vil_ws.get_all_values()
        headers = [h.strip() for h in vil_vals[0]]
        
        villages = {}
        initial_stocks = {}
        seen_villages = set()
        
        for row in vil_vals[1:]:
            if not row or not row[0].strip(): continue
            v_name = row[0].strip()
            if v_name in seen_villages: continue
            seen_villages.add(v_name)
            
            x, y = (int(row[1]), int(row[2])) if len(row) > 2 and row[1] and row[2] else (0, 0)
            villages[v_name] = {'items': {}, 'x': x, 'y': y}
            initial_stocks[v_name] = {}
            
            if v_name != "용병 고용소":
                for i in range(3, len(headers)):
                    if headers[i] in items_info and len(row) > i and row[i].strip():
                        stock = int(row[i])
                        villages[v_name]['items'][headers[i]] = stock
                        initial_stocks[v_name][headers[i]] = stock
        
        play_ws = doc.worksheet("Player_Data")
        slots = []
        for r in play_ws.get_all_records():
            if str(r.get('slot', '')).strip():
                slots.append({
                    'slot': int(r['slot']), 'money': int(r.get('money', 0)), 'pos': str(r.get('pos', '한양')),
                    'inv': json.loads(r.get('inventory', '{}')) if r.get('inventory') else {},
                    'mercs': json.loads(r.get('mercs', '[]')) if r.get('mercs') else [],
                    'week': int(r.get('week', 1)), 'month': int(r.get('month', 1)), 'year': int(r.get('year', 1592)),
                    'last_save': r.get('last_save', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                })
        
        return settings, items_info, merc_data, villages, initial_stocks, slots
    except Exception as e:
        st.error(f"❌ 데이터 로드 에러: {e}")
        return None, None, None, None, None, None

# --- 4. 세션 초기화 함수 ---
def init_session_state():
    if 'game_started' not in st.session_state: st.session_state.game_started = False
    if 'player' not in st.session_state: st.session_state.player = None
    if 'market_data' not in st.session_state: st.session_state.market_data = None
    if 'settings' not in st.session_state: st.session_state.settings = None
    if 'items_info' not in st.session_state: st.session_state.items_info = None
    if 'villages' not in st.session_state: st.session_state.villages = None
    if 'merc_data' not in st.session_state: st.session_state.merc_data = None
    if 'initial_stocks' not in st.session_state: st.session_state.initial_stocks = None
    if 'stats' not in st.session_state:
        st.session_state.stats = {'total_bought': 0, 'total_sold': 0, 'total_spent': 0, 'total_earned': 0, 'trade_count': 0}
    if 'events' not in st.session_state: st.session_state.events = []
    if 'last_update' not in st.session_state: st.session_state.last_update = time.time()
    if 'last_time_update' not in st.session_state: st.session_state.last_time_update = time.time()
    if 'device_id' not in st.session_state:
        st.session_state.device_id = hashlib.md5(f"{uuid.uuid4()}_{time.time()}".encode()).hexdigest()[:12]
    if 'trade_logs' not in st.session_state: st.session_state.trade_logs = {}
    if 'last_qty' not in st.session_state: st.session_state.last_qty = {}

# --- 5. 시간 시스템 함수 (수정됨) ---
def update_game_time(player, settings, market_data, initial_stocks):
    current_time = time.time()
    
    if 'last_time_update' not in st.session_state:
        st.session_state.last_time_update = current_time
        return player, []
    
    elapsed = current_time - st.session_state.last_time_update
    seconds_per_month = int(settings.get('seconds_per_month', 180))
    seconds_per_week = seconds_per_month / 4  # 1주일 기준 시간
    
    weeks_passed = int(elapsed / seconds_per_week)
    events = []
    
    if weeks_passed > 0:
        old_month = player['month']
        old_year = player['year']
        
        for _ in range(weeks_passed):
            player['week'] += 1
            if player['week'] > 4:
                player['week'] = 1
                player['month'] += 1
                if player['month'] > 12:
                    player['month'] = 1
                    player['year'] += 1
        
        # 마지막 업데이트 시간 정밀 갱신
        st.session_state.last_time_update += weeks_passed * seconds_per_week
        st.session_state.last_update = current_time
        
        # 주간 알림 추가
        events.append(("week", f"🌟 {player['year']}년 {player['month']}월 {player['week']}주차가 되었습니다."))
        
        if old_month != player['month'] or old_year != player['year']:
            events.append(("month", f"🌙 {player['year']}년 {player['month']}월이 시작되었습니다!"))
            # 재고 초기화 로직
            for v_name in market_data:
                if v_name in initial_stocks:
                    for item_name in market_data[v_name]:
                        if item_name in initial_stocks[v_name]:
                            market_data[v_name][item_name]['stock'] = initial_stocks[v_name][item_name]
            events.append(("reset", "🔄 전 대륙 물품 재고 초기화 완료"))
            
        # 돌발 이벤트 (기존 로직 유지)
        inventoryResponsivePrice = settings.get('inventoryResponsivePrice', 5000)
        event_probability = inventoryResponsivePrice / 4000000 # 주 단위이므로 확률 조정
        if random.random() < event_probability:
            cities = list(market_data.keys())
            if cities:
                random_city = random.choice(cities)
                items_in_city = list(market_data[random_city].keys())
                if items_in_city:
                    vol_item = random.choice(items_in_city)
                    vol_direction = random.choice(["상승", "하락"])
                    vol_amount = random.randint(10, 30) + int(inventoryResponsivePrice / 1000)
                    if vol_direction == "상승":
                        market_data[random_city][vol_item]['price'] = int(market_data[random_city][vol_item]['price'] * (1 + vol_amount/100))
                        events.append(("volatility", f"📈 {random_city}의 {vol_item} 가격 {vol_amount}% 급등!"))
                    else:
                        market_data[random_city][vol_item]['price'] = int(market_data[random_city][vol_item]['price'] * (1 - vol_amount/100))
                        events.append(("volatility", f"📉 {random_city}의 {vol_item} 가격 {vol_amount}% 급락!"))
    
    return player, events

def get_time_display(player):
    return f"{player['year']}년 {player['month']}월 {player['week']}주차"

# --- 6. 게임 로직 함수들 (기존 유지) ---
def update_prices(settings, items_info, market_data, initial_stocks=None):
    for v_name, v_data in market_data.items():
        if v_name == "용병 고용소": continue
        for i_name, i_info in v_data.items():
            if i_name in items_info:
                base = items_info[i_name]['base']
                stock = i_info['stock']
                if stock < 100: price_factor = 2.0
                elif stock < 500: price_factor = 1.5
                elif stock < 1000: price_factor = 1.2
                elif stock < 2000: price_factor = 1.0
                elif stock < 5000: price_factor = 0.8
                else: price_factor = 0.6
                i_info['price'] = int(base * price_factor)

def get_weight(player, items_info, merc_data):
    cw = sum(qty * items_info[item]['w'] for item, qty in player['inv'].items() if item in items_info)
    tw = 200 + sum(merc_data[merc]['w_bonus'] for merc in player['mercs'] if merc in merc_data)
    return cw, tw

def calculate_max_purchase(player, items_info, market_data, pos, item_name, target_price):
    if item_name not in items_info: return 0
    cw, tw = get_weight(player, items_info, st.session_state.merc_data)
    max_by_money = player['money'] // target_price if target_price > 0 else 0
    max_by_weight = (tw - cw) // items_info[item_name]['w'] if items_info[item_name]['w'] > 0 else 999999
    return min(max_by_money, max_by_weight, market_data[pos][item_name]['stock'])

def process_buy(player, items_info, market_data, pos, item_name, qty, progress_placeholder, log_key):
    total_bought, total_spent, batch_prices = 0, 0, []
    if log_key not in st.session_state.trade_logs: st.session_state.trade_logs[log_key] = []
    while total_bought < qty:
        update_prices(st.session_state.settings, items_info, market_data, st.session_state.initial_stocks)
        target = market_data[pos][item_name]
        cw, tw = get_weight(player, items_info, st.session_state.merc_data)
        can_pay = player['money'] // target['price'] if target['price'] > 0 else 0
        can_load = (tw - cw) // items_info[item_name]['w'] if items_info[item_name]['w'] > 0 else 999999
        batch = min(100, qty - total_bought, target['stock'], can_pay, can_load)
        if batch <= 0: break
        for _ in range(batch):
            player['money'] -= target['price']
            total_spent += target['price']
            player['inv'][item_name] = player['inv'].get(item_name, 0) + 1
            target['stock'] -= 1
            total_bought += 1
            batch_prices.append(target['price'])
        log_msg = f"➤ {total_bought}/{qty} 구매 중... (체결가: {target['price']}냥)"
        st.session_state.trade_logs[log_key].append(log_msg)
        with progress_placeholder.container():
            for log in st.session_state.trade_logs[log_key][-5:]:
                st.markdown(f"<div class='trade-line'>{log}</div>", unsafe_allow_html=True)
        time.sleep(0.05)
    return total_bought, total_spent

def process_sell(player, items_info, market_data, pos, item_name, qty, progress_placeholder, log_key):
    total_sold, total_earned, batch_prices = 0, 0, []
    if log_key not in st.session_state.trade_logs: st.session_state.trade_logs[log_key] = []
    while total_sold < qty:
        update_prices(st.session_state.settings, items_info, market_data, st.session_state.initial_stocks)
        current_price = market_data[pos][item_name]['price']
        batch = min(100, qty - total_sold, player['inv'].get(item_name, 0))
        if batch <= 0: break
        for _ in range(batch):
            player['money'] += current_price
            player['inv'][item_name] -= 1
            market_data[pos][item_name]['stock'] += 1
            total_sold += 1
            total_earned += current_price
            batch_prices.append(current_price)
        log_msg = f"➤ {total_sold}/{qty} 판매 중... (체결가: {current_price}냥)"
        st.session_state.trade_logs[log_key].append(log_msg)
        with progress_placeholder.container():
            for log in st.session_state.trade_logs[log_key][-5:]:
                st.markdown(f"<div class='trade-line'>{log}</div>", unsafe_allow_html=True)
        time.sleep(0.05)
    return total_sold, total_earned

def save_player_data(doc, player, stats, device_id):
    try:
        play_ws = doc.worksheet("Player_Data")
        all_records = play_ws.get_all_records()
        row_idx = next((i for i, r in enumerate(all_records, start=2) if r.get('slot') == player['slot']), None)
        if row_idx:
            save_values = [player['slot'], player['money'], player['pos'], json.dumps(player['mercs'], ensure_ascii=False),
                           json.dumps(player['inv'], ensure_ascii=False), datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                           player['week'], player['month'], player['year'], device_id]
            play_ws.update(f'A{row_idx}:J{row_idx}', [save_values])
            return True
    except Exception as e:
        st.error(f"❌ 저장 실패: {e}")
        return False

# --- 7. 메인 실행 ---
doc = connect_gsheet()
init_session_state()

# ⭐ 1초마다 자동 새로고침 설정 (UI 유지하며 시간 업데이트)
st_autorefresh(interval=1000, key="gametimer")

if doc:
    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        settings, items_info, merc_data, villages, initial_stocks, slots = load_game_data()
        if slots:
            st.subheader("📋 세이브 슬롯 선택")
            slot_choice = st.selectbox("슬롯 번호", options=[1, 2, 3], index=0)
            if st.button("🎮 게임 시작", use_container_width=True):
                selected = next((s for s in slots if s['slot'] == slot_choice), None)
                if selected:
                    st.session_state.player, st.session_state.settings = selected, settings
                    st.session_state.items_info, st.session_state.merc_data = items_info, merc_data
                    st.session_state.villages, st.session_state.initial_stocks = villages, initial_stocks
                    st.session_state.last_time_update = time.time()
                    market_data = {v: {i: {'stock': s, 'price': items_info[i]['base']} for i, s in d['items'].items()} 
                                   for v, d in villages.items() if v != "용병 고용소"}
                    update_prices(settings, items_info, market_data, initial_stocks)
                    st.session_state.market_data = market_data
                    st.session_state.game_started = True
                    st.rerun()
    else:
        player = st.session_state.player
        settings = st.session_state.settings
        items_info = st.session_state.items_info
        merc_data = st.session_state.merc_data
        villages = st.session_state.villages
        market_data = st.session_state.market_data
        initial_stocks = st.session_state.initial_stocks
        
        # 시간 업데이트 및 주간 알림 처리
        player, new_events = update_game_time(player, settings, market_data, initial_stocks)
        if new_events:
            for etype, emsg in new_events:
                if etype == "week":
                    st.toast(emsg, icon="📅") # 1주마다 토스트 메시지 출력
                else:
                    st.session_state.events.append((etype, emsg))
        
        update_prices(settings, items_info, market_data, initial_stocks)
        cw, tw = get_weight(player, items_info, merc_data)
        
        if st.session_state.events:
            for _, message in st.session_state.events:
                st.markdown(f"<div class='event-message'>{message}</div>", unsafe_allow_html=True)
            st.session_state.events = []
        
        st.title(f"🏯 {player['pos']}")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💰 소지금", f"{player['money']:,}냥")
        col2.metric("⚖️ 무게", f"{cw}/{tw}근")
        col3.metric("📅 시간", get_time_display(player))
        
        # 남은 시간 계산 (1주 기준)
        sec_per_week = int(settings.get('seconds_per_month', 180)) / 4
        rem = max(0, int(sec_per_week - (time.time() - st.session_state.last_time_update)))
        col4.metric("⏰ 다음 주까지", f"{rem}초")
        
        # 탭 메뉴 구성 (기존 로직 동일)
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 저잣거리", "📦 인벤토리", "⚔️ 용병", "📊 통계", "⚙️ 이동"])
        
        with tab1:
            if player['pos'] == "용병 고용소":
                st.subheader("⚔️ 용병 고용")
                max_mercs = int(settings.get('max_mercenaries', 5))
                st.info(f"**현재 용병: {len(player['mercs'])}/{max_mercs}명**")
                for name, data in merc_data.items():
                    count = sum(1 for m in player['mercs'] if m == name)
                    if st.button(f"⚔️ {name} 고용 ({data['price']:,}냥)", disabled=(len(player['mercs']) >= max_mercs), key=f"m_{name}"):
                        if player['money'] >= data['price']:
                            player['money'] -= data['price']
                            player['mercs'].append(name)
                            st.rerun()
            elif player['pos'] in market_data:
                for item_name, d in market_data[player['pos']].items():
                    with st.container():
                        col_a, col_b, col_c = st.columns([2,1,1])
                        col_a.write(f"**{item_name}** ({d['price']:,}냥)")
                        col_b.write(f"📦 {d['stock']}개")
                        max_b = calculate_max_purchase(player, items_info, market_data, player['pos'], item_name, d['price'])
                        col_c.write(f"⚡ {max_b}개")
                        
                        qty_input = st.text_input("수량", value="1", key=f"q_{item_name}", label_visibility="collapsed")
                        p_ph = st.empty()
                        
                        btn_col1, btn_col2 = st.columns(2)
                        if btn_col1.button("💰 매수", key=f"b_{item_name}"):
                            try:
                                amt = min(int(qty_input), max_b)
                                if amt > 0: process_buy(player, items_info, market_data, player['pos'], item_name, amt, p_ph, f"log_{item_name}")
                                st.rerun()
                            except: pass
                        if btn_col2.button("📦 매도", key=f"s_{item_name}"):
                            try:
                                amt = min(int(qty_input), player['inv'].get(item_name, 0))
                                if amt > 0: process_sell(player, items_info, market_data, player['pos'], item_name, amt, p_ph, f"log_{item_name}")
                                st.rerun()
                            except: pass
                        st.divider()

        with tab2:
            st.subheader("📦 내 인벤토리")
            for item, qty in player['inv'].items():
                if qty > 0: st.write(f"• **{item}**: {qty}개 ({items_info[item]['w'] * qty}근)")
        
        with tab3:
            st.subheader("⚔️ 내 용병")
            for merc in set(player['mercs']):
                cnt = player['mercs'].count(merc)
                st.write(f"• **{merc}**: {cnt}명")

        with tab4:
            st.subheader("📊 거래 통계")
            st.write(f"💰 총 매입: {st.session_state.stats['total_spent']:,}냥 / 총 매출: {st.session_state.stats['total_earned']:,}냥")

        with tab5:
            st.subheader("⚙️ 게임 메뉴")
            towns = [t for t in villages.keys() if t != player['pos']]
            dest = st.selectbox("이동할 마을", towns)
            if st.button("🚀 이동", use_container_width=True):
                dist = math.sqrt((villages[player['pos']]['x'] - villages[dest]['x'])**2 + (villages[player['pos']]['y'] - villages[dest]['y'])**2)
                cost = int(dist * settings.get('travel_cost', 15))
                if player['money'] >= cost:
                    player['money'] -= cost
                    player['pos'] = dest
                    st.rerun()
            st.divider()
            if st.button("💾 저장", use_container_width=True):
                if save_player_data(doc, player, st.session_state.stats, st.session_state.device_id): st.success("✅ 저장 완료!")
            if st.button("🚪 메인으로", use_container_width=True):
                st.session_state.game_started = False
                st.rerun()
