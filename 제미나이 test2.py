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

# --- 1. 페이지 설정 및 스타일 (UI 개선 참고) ---
st.set_page_config(
    page_title="조선거상 미니",
    page_icon="🏯",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 모바일 최적화 및 UI 개선 CSS
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
    .slot-container { background-color: #ffffff; padding: 20px; border-radius: 15px; border: 1px solid #e1e4e8; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .trade-container { background-color: #f8f9fa; padding: 15px; border-radius: 10px; margin-top: 10px; border: 1px solid #dee2e6; }
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
        # 설정 데이터 로드
        set_ws = doc.worksheet("Setting_Data")
        settings = {r['변수명']: float(r['값']) for r in set_ws.get_all_records()}
        
        # 아이템 정보 로드
        item_ws = doc.worksheet("Item_Data")
        items_info = {}
        for r in item_ws.get_all_records():
            if r.get('item_name'):
                name = str(r['item_name']).strip()
                items_info[name] = {
                    'base': int(r['base_price']),
                    'w': int(r['weight'])
                }
        
        # 용병 정보 로드
        bal_ws = doc.worksheet("Balance_Data")
        merc_data = {}
        for r in bal_ws.get_all_records():
            if r.get('name'):
                name = str(r['name']).strip()
                merc_data[name] = {
                    'price': int(r['price']),
                    'w_bonus': int(r.get('weight_bonus', 0))
                }
        
        # 마을 데이터 로드
        vil_ws = doc.worksheet("Korea_Village_Data")
        vil_vals = vil_ws.get_all_values()
        headers = [h.strip() for h in vil_vals[0]]
        
        villages = {}
        initial_stocks = {}
        seen_villages = set()
        
        for row in vil_vals[1:]:
            if not row or not row[0].strip():
                continue
            v_name = row[0].strip()
            
            if v_name in seen_villages:
                continue
            seen_villages.add(v_name)
            
            try:
                x = int(row[1]) if len(row) > 1 and row[1] else 0
                y = int(row[2]) if len(row) > 2 and row[2] else 0
            except:
                x, y = 0, 0
            
            villages[v_name] = {'items': {}, 'x': x, 'y': y}
            initial_stocks[v_name] = {}
            
            if v_name != "용병 고용소":
                for i in range(3, len(headers)):
                    if headers[i] in items_info:
                        if len(row) > i and row[i].strip():
                            try:
                                stock = int(row[i])
                                villages[v_name]['items'][headers[i]] = stock
                                initial_stocks[v_name][headers[i]] = stock
                            except:
                                pass
        
        # 플레이어 데이터 로드
        play_ws = doc.worksheet("Player_Data")
        slots = []
        for r in play_ws.get_all_records():
            if str(r.get('slot', '')).strip():
                slots.append({
                    'slot': int(r['slot']),
                    'money': int(r.get('money', 0)),
                    'pos': str(r.get('pos', '한양')),
                    'inv': json.loads(r.get('inventory', '{}')) if r.get('inventory') else {},
                    'mercs': json.loads(r.get('mercs', '[]')) if r.get('mercs') else [],
                    'week': int(r.get('week', 1)),
                    'month': int(r.get('month', 1)),
                    'year': int(r.get('year', 1592)),
                    'last_save': r.get('last_save', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                })
        
        return settings, items_info, merc_data, villages, initial_stocks, slots
    
    except Exception as e:
        st.error(f"❌ 데이터 로드 에러: {e}")
        return None, None, None, None, None, None

# --- 4. 세션 초기화 함수 ---
def init_session_state():
    if 'game_started' not in st.session_state:
        st.session_state.game_started = False
    if 'player' not in st.session_state:
        st.session_state.player = None
    if 'market_data' not in st.session_state:
        st.session_state.market_data = None
    if 'settings' not in st.session_state:
        st.session_state.settings = None
    if 'items_info' not in st.session_state:
        st.session_state.items_info = None
    if 'villages' not in st.session_state:
        st.session_state.villages = None
    if 'merc_data' not in st.session_state:
        st.session_state.merc_data = None
    if 'initial_stocks' not in st.session_state:
        st.session_state.initial_stocks = None
    if 'stats' not in st.session_state:
        st.session_state.stats = {
            'total_bought': 0,
            'total_sold': 0,
            'total_spent': 0,
            'total_earned': 0,
            'trade_count': 0
        }
    if 'events' not in st.session_state:
        st.session_state.events = []
    if 'last_update' not in st.session_state:
        st.session_state.last_update = time.time()
    if 'last_time_update' not in st.session_state:
        st.session_state.last_time_update = time.time()
    if 'device_id' not in st.session_state:
        session_key = f"{str(uuid.uuid4())}_{time.time()}"
        st.session_state.device_id = hashlib.md5(session_key.encode()).hexdigest()[:12]
    if 'last_save_time' not in st.session_state:
        st.session_state.last_save_time = time.time()
    if 'trade_logs' not in st.session_state:
        st.session_state.trade_logs = {}
    if 'last_qty' not in st.session_state:
        st.session_state.last_qty = {}

# --- 5. 시간 시스템 함수 (기준 코드 유지, UI 참고) ---
def update_game_time(player, settings, market_data, initial_stocks):
    current_time = time.time()
    
    if 'last_time_update' not in st.session_state:
        st.session_state.last_time_update = current_time
        return player, []
    
    elapsed = current_time - st.session_state.last_time_update
    seconds_per_month = int(settings.get('seconds_per_month', 180))  # 스프레드시트 연동
    months_passed = int(elapsed / seconds_per_month)
    
    events = []
    
    if months_passed > 0:
        old_month = player['month']
        old_year = player['year']
        
        for _ in range(months_passed):
            player['week'] += 1
            if player['week'] > 4:
                player['week'] = 1
                player['month'] += 1
                if player['month'] > 12:
                    player['month'] = 1
                    player['year'] += 1
        
        st.session_state.last_time_update = current_time
        st.session_state.last_update = current_time
        
        if old_month != player['month'] or old_year != player['year']:
            events.append(("month", f"🌙 {player['year']}년 {player['month']}월이 시작되었습니다!"))
            
            reset_count = 0
            for v_name in market_data:
                if v_name in initial_stocks:
                    for item_name in market_data[v_name]:
                        if item_name in initial_stocks[v_name]:
                            old_stock = market_data[v_name][item_name]['stock']
                            market_data[v_name][item_name]['stock'] = initial_stocks[v_name][item_name]
                            if old_stock != initial_stocks[v_name][item_name]:
                                reset_count += 1
            if reset_count > 0:
                events.append(("reset", f"🔄 {reset_count}개 품목 재고 초기화"))
        
        events.append(("week", f"🌟 {player['year']}년 {player['month']}월 {player['week']}주차"))
        
        # 계절 효과 등 (기준 코드 유지)
        season_effects = {
            (3,4,5): ("🌸 봄: 인삼/가죽 수요 증가!", ['인삼', '소가죽', '염색가죽'], 1.2),
            (6,7,8): ("☀️ 여름: 비단 수요 증가!", ['비단'], 1.3),
            (9,10,11): ("🍂 가을: 쌀 수요 증가!", ['쌀'], 1.3),
            (12,1,2): ("❄️ 겨울: 가죽갑옷 수요 급증!", ['가죽갑옷'], 1.5)
        }
        
        for months, (msg, items, factor) in season_effects.items():
            if player['month'] in months:
                events.append(("season", msg))
                break
        
        if random.random() < 0.3:
            cities = list(market_data.keys())
            if cities:
                random_city = random.choice(cities)
                items_in_city = list(market_data[random_city].keys())
                if items_in_city:
                    vol_item = random.choice(items_in_city)
                    vol_direction = random.choice(["상승", "하락"])
                    vol_amount = random.randint(10, 30)
                    
                    if vol_direction == "상승":
                        market_data[random_city][vol_item]['price'] = int(market_data[random_city][vol_item]['price'] * (1 + vol_amount/100))
                        events.append(("volatility", f"📈 {random_city}의 {vol_item} 가격 {vol_amount}% 급등!"))
                    else:
                        market_data[random_city][vol_item]['price'] = int(market_data[random_city][vol_item]['price'] * (1 - vol_amount/100))
                        events.append(("volatility", f"📉 {random_city}의 {vol_item} 가격 {vol_amount}% 급락!"))
    
    return player, events

def get_time_display(player):
    month_names = ["1월", "2월", "3월", "4월", "5월", "6월", 
                   "7월", "8월", "9월", "10월", "11월", "12월"]
    return f"{player['year']}년 {month_names[player['month']-1]} {player['week']}주차"

# --- 6. 게임 로직 함수들 (가격 변동: 재고 기반만) ---
def update_prices(settings, items_info, market_data, initial_stocks=None):
    if initial_stocks is None:
        initial_stocks = st.session_state.get('initial_stocks', {})
    
    min_price_rate = settings.get('min_price_rate', 0.4)
    max_price_rate = settings.get('max_price_rate', 3.0)
    
    for v_name, v_data in market_data.items():
        if v_name == "용병 고용소":
            continue
            
        for i_name, i_info in v_data.items():
            if i_name in items_info:
                base = items_info[i_name]['base']
                stock = i_info['stock']
                initial_stock = initial_stocks.get(v_name, {}).get(i_name, 100)
                
                if initial_stock <= 0:
                    initial_stock = 100
                
                if stock <= 0:
                    i_info['price'] = int(base * max_price_rate)
                else:
                    stock_ratio = stock / initial_stock
                    
                    # 재고 기반 가격 변동 (기준 코드처럼 단순화)
                    if stock_ratio < 0.5:  # 재고 50% 미만
                        price_factor = 2.5
                    elif stock_ratio < 1.0:  # 재고 100% 미만
                        price_factor = 1.8
                    else:
                        price_factor = 1.0
                    
                    i_info['price'] = int(base * price_factor)
                    
                    min_price = int(base * min_price_rate)
                    if i_info['price'] < min_price:
                        i_info['price'] = min_price
                    if i_info['price'] > base * max_price_rate:
                        i_info['price'] = int(base * max_price_rate)

def get_weight(player, items_info, merc_data):
    cw = 0
    for item, qty in player['inv'].items():
        if item in items_info:
            cw += qty * items_info[item]['w']
    
    tw = 200
    for merc in player['mercs']:
        if merc in merc_data:
            tw += merc_data[merc]['w_bonus']
    
    return cw, tw

def calculate_max_purchase(player, items_info, market_data, pos, item_name, target_price):
    if item_name not in items_info:
        return 0
    
    cw, tw = get_weight(player, items_info, st.session_state.merc_data)
    item_weight = items_info[item_name]['w']
    
    max_by_money = player['money'] // target_price if target_price > 0 else 0
    max_by_weight = (tw - cw) // item_weight if item_weight > 0 else 999999
    max_by_stock = market_data[pos][item_name]['stock']
    
    return min(max_by_money, max_by_weight, max_by_stock)

def process_buy(player, items_info, market_data, pos, item_name, qty, progress_placeholder, log_key):
    total_bought = 0
    total_spent = 0
    batch_prices = []
    
    if log_key not in st.session_state.trade_logs:
        st.session_state.trade_logs[log_key] = []
    
    while total_bought < qty:
        update_prices(st.session_state.settings, items_info, market_data, st.session_state.initial_stocks)
        target = market_data[pos][item_name]
        cw, tw = get_weight(player, items_info, st.session_state.merc_data)
        
        can_pay = player['money'] // target['price'] if target['price'] > 0 else 0
        can_load = (tw - cw) // items_info[item_name]['w'] if items_info[item_name]['w'] > 0 else 999999
        
        batch = min(100, qty - total_bought, target['stock'], can_pay, can_load)
        
        if batch <= 0:
            break
        
        for _ in range(batch):
            player['money'] -= target['price']
            total_spent += target['price']
            player['inv'][item_name] = player['inv'].get(item_name, 0) + 1
            target['stock'] -= 1
            total_bought += 1
            batch_prices.append(target['price'])
        
        avg_price = sum(batch_prices) // len(batch_prices) if batch_prices else 0
        log_msg = f"➤ {total_bought}/{qty} 구매 중... (체결가: {target['price']}냥 | 평균가: {avg_price}냥)"
        st.session_state.trade_logs[log_key].append(log_msg)
        
        with progress_placeholder.container():
            for log in st.session_state.trade_logs[log_key][-10:]:
                st.markdown(f"<div class='trade-line'>{log}</div>", unsafe_allow_html=True)
        
        time.sleep(0.05)
    
    return total_bought, total_spent

def process_sell(player, items_info, market_data, pos, item_name, qty, progress_placeholder, log_key):
    total_sold = 0
    total_earned = 0
    batch_prices = []
    
    if log_key not in st.session_state.trade_logs:
        st.session_state.trade_logs[log_key] = []
    
    while total_sold < qty:
        update_prices(st.session_state.settings, items_info, market_data, st.session_state.initial_stocks)
        current_price = market_data[pos][item_name]['price']
        
        batch = min(100, qty - total_sold, player['inv'].get(item_name, 0))
        
        if batch <= 0:
            break
        
        for _ in range(batch):
            player['money'] += current_price
            player['inv'][item_name] -= 1
            market_data[pos][item_name]['stock'] += 1
            total_sold += 1
            total_earned += current_price
            batch_prices.append(current_price)
        
        avg_price = sum(batch_prices) // len(batch_prices) if batch_prices else 0
        log_msg = f"➤ {total_sold}/{qty} 판매 중... (체결가: {current_price}냥 | 평균가: {avg_price}냥)"
        st.session_state.trade_logs[log_key].append(log_msg)
        
        with progress_placeholder.container():
            for log in st.session_state.trade_logs[log_key][-10:]:
                st.markdown(f"<div class='trade-line'>{log}</div>", unsafe_allow_html=True)
        
        time.sleep(0.05)
    
    return total_sold, total_earned

def save_player_data(doc, player, stats, device_id):
    try:
        play_ws = doc.worksheet("Player_Data")
        all_records = play_ws.get_all_records()
        
        row_idx = None
        for i, record in enumerate(all_records, start=2):
            if record.get('slot') == player['slot']:
                row_idx = i
                break
        
        if row_idx:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            save_values = [
                player['slot'],
                player['money'],
                player['pos'],
                json.dumps(player['mercs'], ensure_ascii=False),
                json.dumps(player['inv'], ensure_ascii=False),
                now,
                player['year'],
                player['month'],
                player['week']
            ]
            play_ws.update(f"A{row_idx}:I{row_idx}", [save_values])
            return True
        else:
            return False
    except Exception as e:
        st.error(f"❌ 저장 에러: {e}")
        return False

# --- 7. 메인 로직 ---
init_session_state()

doc = connect_gsheet()
settings, items_info, merc_data, villages, initial_stocks, slots = load_game_data()

if not settings:
    st.stop()

st.session_state.settings = settings
st.session_state.items_info = items_info
st.session_state.merc_data = merc_data
st.session_state.villages = villages
st.session_state.initial_stocks = initial_stocks

# 시장 데이터 초기화 (마을별 아이템 가격/재고)
if st.session_state.market_data is None:
    market_data = {}
    for v_name, v_info in villages.items():
        market_data[v_name] = {}
        for item_name, stock in v_info['items'].items():
            market_data[v_name][item_name] = {'stock': stock, 'price': items_info[item_name]['base']}
    st.session_state.market_data = market_data

if not st.session_state.game_started:
    st.title("🏯 조선거상 미니")
    for slot in slots:
        with st.container():
            st.markdown(f"""<div class="slot-container"><b>💾 슬롯 {slot['slot']}</b><br>
            📍 현재 위치: {slot['pos']} | 💰 소지금: {slot['money']:,}냥<br>
            🕒 마지막 저장: {slot['last_save']}</div>""", unsafe_allow_html=True)
            if st.button(f"슬롯 {slot['slot']} 접속", key=f"slot_{slot['slot']}"):
                st.session_state.player = slot
                st.session_state.game_started = True
                st.rerun()
else:
    player = st.session_state.player
    market_data = st.session_state.market_data
    
    player, new_events = update_game_time(player, settings, market_data, initial_stocks)
    st.session_state.events.extend(new_events)
    
    st.header(f"📍 {player['pos']}")
    
    money_placeholder = st.empty()
    money_placeholder.metric("💰 소지금", f"{player['money']:,}냥")
    
    cw, tw = get_weight(player, items_info, merc_data)
    weight_placeholder = st.empty()
    weight_placeholder.metric("⚖️ 무게", f"{cw}/{tw}근")
    
    time_placeholder = st.empty()
    time_placeholder.info(f"⏰ {get_time_display(player)}")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 거래", "📦 인벤", "⚔️ 용병", "🚀 이벤트", "⚙️ 메뉴"])
    
    with tab1:
        if player['pos'] == "용병 고용소":
            st.subheader("⚔️ 용병 고용소")
            max_mercs = int(settings.get('max_mercenaries', 5))
            for name, data in merc_data.items():
                count = player['mercs'].count(name)
                if st.button(f"⚔️ {name} 고용 ({data['price']:,}냥 | 무게 +{data['w_bonus']}근)", key=f"merc_{name}"):
                    if len(player['mercs']) >= max_mercs:
                        st.error(f"❌ 최대 {max_mercs}명 초과")
                    elif player['money'] >= data['price']:
                        player['money'] -= data['price']
                        player['mercs'].append(name)
                        st.success(f"✅ {name} 고용 완료!")
                        st.rerun()
                    else:
                        st.error("❌ 잔액 부족")
        else:
            st.subheader(f"🛒 {player['pos']} 시세")
            items = list(market_data[player['pos']].keys())
            for item_name in items:
                d = market_data[player['pos']][item_name]
                base_price = items_info[item_name]['base']
                
                if d['price'] > base_price * 1.2:
                    price_class = "price-up"
                elif d['price'] < base_price * 0.8:
                    price_class = "price-down"
                else:
                    price_class = "price-same"
                
                with st.container(border=True):
                    st.markdown(f"**{item_name}** <span class='{price_class}'>{d['price']:,}냥</span>", unsafe_allow_html=True)
                    col1, col2 = st.columns(2)
                    col1.write(f"📦 {d['stock']}개")
                    max_buy = calculate_max_purchase(player, items_info, market_data, player['pos'], item_name, d['price'])
                    col2.write(f"⚡ {max_buy}개")
                    
                    qty = st.number_input("수량", min_value=1, value=1, key=f"qty_{item_name}")
                    b_col, s_col = st.columns(2)
                    if b_col.button("💰 매수"):
                        process_buy(player, items_info, market_data, player['pos'], item_name, qty, st.empty(), f"buy_{item_name}_{time.time()}")
                        st.rerun()
                    if s_col.button("📦 매도"):
                        process_sell(player, items_info, market_data, player['pos'], item_name, qty, st.empty(), f"sell_{item_name}_{time.time()}")
                        st.rerun()

    with tab2:
        st.subheader("📦 인벤토리")
        if player['inv']:
            for item, qty in player['inv'].items():
                if qty > 0:
                    st.write(f"• {item}: {qty}개")
        else:
            st.write("비어있음")

    with tab3:
        st.subheader("⚔️ 용병")
        if player['mercs']:
            for merc in set(player['mercs']):
                count = player['mercs'].count(merc)
                st.write(f"• {merc}: {count}명")
        else:
            st.write("없음")

    with tab4:
        st.subheader("🚀 이벤트")
        for _, msg in st.session_state.events[-10:]:
            st.markdown(f"<div class='event-message'>{msg}</div>", unsafe_allow_html=True)

    with tab5:
        st.subheader("⚙️ 메뉴")
        towns = list(villages.keys())
        selected = st.selectbox("이동", towns)
        if st.button("🚀 이동"):
            player['pos'] = selected
            st.rerun()
        
        if st.button("💾 저장"):
            save_player_data(doc, player, st.session_state.stats, st.session_state.device_id)
            st.success("저장 완료!")

