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
        return None, None, None, None, None, None, None
    
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
        vil_ws = doc.worksheet("Village_Data")
        vil_vals = vil_ws.get_all_values()
        headers = [h.strip() for h in vil_vals[0]]
        
        villages = {}
        initial_stocks = {}
        seen_villages = set()  # 중복 체크를 위한 세트
        
        for row in vil_vals[1:]:
            if not row or not row[0].strip():
                continue
            v_name = row[0].strip()
            
            # 이미 처리한 마을이면 스킵
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
        
        # 도시별 설정 데이터 로드
        city_settings = {}
        try:
            city_ws = doc.worksheet("City_Setting_Data")
            for r in city_ws.get_all_records():
                city_name = str(r['village_name']).strip()
                city_settings[city_name] = {
                    'ratio_extreme_high': float(r.get('ratio_extreme_high', 2.0)),
                    'ratio_high': float(r.get('ratio_high', 1.5)),
                    'ratio_above_normal': float(r.get('ratio_above_normal', 1.0)),
                    'ratio_normal': float(r.get('ratio_normal', 0.7)),
                    'ratio_low': float(r.get('ratio_low', 0.4)),
                    'factor_extreme_high': float(r.get('factor_extreme_high', 0.5)),
                    'factor_high': float(r.get('factor_high', 0.7)),
                    'factor_above_normal': float(r.get('factor_above_normal', 0.85)),
                    'factor_normal': float(r.get('factor_normal', 1.0)),
                    'factor_low': float(r.get('factor_low', 1.3)),
                    'factor_extreme_low': float(r.get('factor_extreme_low', 2.0)),
                    'region_discount': float(r.get('region_discount', 1.0)),
                    'city_premium': float(r.get('city_premium', 1.0)),
                }
        except Exception as e:
            st.warning("City_Setting_Data 시트를 찾을 수 없습니다. 기본값을 사용합니다.")
            city_settings = {}
        
        return settings, items_info, merc_data, villages, initial_stocks, slots, city_settings
    
    except Exception as e:
        st.error(f"❌ 데이터 로드 에러: {e}")
        return None, None, None, None, None, None, None

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

# --- 5. 시간 시스템 함수 ---
def update_game_time(player, settings, market_data, initial_stocks):
    current_time = time.time()
    
    if 'last_time_update' not in st.session_state:
        st.session_state.last_time_update = current_time
        return player, []
    
    elapsed = current_time - st.session_state.last_time_update
    # ✅ 스프레드시트에서 seconds_per_month 값 가져오기
    seconds_per_month = int(settings.get('seconds_per_month', 180))  # 기본값 180
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
        
        # ... 나머지 코드 ...
    
        return player, events
        
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

# --- 6. 게임 로직 함수들 ---
def update_prices(settings, items_info, market_data, initial_stocks=None, city_settings=None):
    if initial_stocks is None:
        initial_stocks = st.session_state.get('initial_stocks', {})
    if city_settings is None:
        city_settings = st.session_state.get('city_settings', {})
    
    # 기본 설정값
    default_ratio_extreme_high = settings.get('price_ratio_extreme_high', 2.0)
    default_ratio_high = settings.get('price_ratio_high', 1.5)
    default_ratio_above_normal = settings.get('price_ratio_above_normal', 1.0)
    default_ratio_normal = settings.get('price_ratio_normal', 0.7)
    default_ratio_low = settings.get('price_ratio_low', 0.4)
    
    default_factor_extreme_high = settings.get('price_factor_extreme_high', 0.5)
    default_factor_high = settings.get('price_factor_high', 0.7)
    default_factor_above_normal = settings.get('price_factor_above_normal', 0.85)
    default_factor_normal = settings.get('price_factor_normal', 1.0)
    default_factor_low = settings.get('price_factor_low', 1.3)
    default_factor_extreme_low = settings.get('price_factor_extreme_low', 2.0)
    
    min_price_rate = settings.get('min_price_rate', 0.4)
    max_price_rate = settings.get('max_price_rate', 3.0)
    
    for v_name, v_data in market_data.items():
        # 도시별 설정 가져오기
        city_set = city_settings.get(v_name, {})
        
        ratio_extreme_high = city_set.get('ratio_extreme_high', default_ratio_extreme_high)
        ratio_high = city_set.get('ratio_high', default_ratio_high)
        ratio_above_normal = city_set.get('ratio_above_normal', default_ratio_above_normal)
        ratio_normal = city_set.get('ratio_normal', default_ratio_normal)
        ratio_low = city_set.get('ratio_low', default_ratio_low)
        
        factor_extreme_high = city_set.get('factor_extreme_high', default_factor_extreme_high)
        factor_high = city_set.get('factor_high', default_factor_high)
        factor_above_normal = city_set.get('factor_above_normal', default_factor_above_normal)
        factor_normal = city_set.get('factor_normal', default_factor_normal)
        factor_low = city_set.get('factor_low', default_factor_low)
        factor_extreme_low = city_set.get('factor_extreme_low', default_factor_extreme_low)
        
        region_discount = city_set.get('region_discount', 1.0)
        city_premium = city_set.get('city_premium', 1.0)
        
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
                    
                    # 도시별 기준값으로 가격 계수 결정
                    if stock_ratio > ratio_extreme_high:
                        price_factor = factor_extreme_high
                    elif stock_ratio > ratio_high:
                        price_factor = factor_high
                    elif stock_ratio > ratio_above_normal:
                        price_factor = factor_above_normal
                    elif stock_ratio > ratio_normal:
                        price_factor = factor_normal
                    elif stock_ratio > ratio_low:
                        price_factor = factor_low
                    else:
                        price_factor = factor_extreme_low
                    
                    # 지역 특산물 할인
                    region_discounts = {
                        "부산": ["생선", "멸치", "굴비", "대구", "명태"],
                        "제주": ["감귤", "해산물", "돼지고기"],
                        "강원도": ["감자", "옥수수", "송이버섯"],
                        "전라도": ["쌀", "배추", "고추"],
                        "경상도": ["사과", "배", "소고기"],
                        "충청도": ["인삼", "약초"],
                        "함흥": ["북어", "명태"],
                    }
                    
                    for region, items in region_discounts.items():
                        if v_name == region and i_name in items:
                            price_factor *= region_discount
                            break
                    
                    # 도시 프리미엄 적용
                    price_factor *= city_premium
                    
                    i_info['price'] = int(base * price_factor)
                    
                    # 최소/최대 가격 제한
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
        
        avg_price = sum(batch_prices) // len(batch_prices)
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
        
        avg_price = sum(batch_prices) // len(batch_prices)
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
                player['week'],
                player['month'],
                player['year'],
                device_id
            ]
            play_ws.update(f'A{row_idx}:J{row_idx}', [save_values])
            return True
    except Exception as e:
        st.error(f"❌ 저장 실패: {e}")
        return False

# --- 7. 메인 실행 ---
doc = connect_gsheet()
init_session_state()

if doc:
    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        st.markdown("---")
        
        settings, items_info, merc_data, villages, initial_stocks, slots, city_settings = load_game_data()        
        
        if slots:
            st.subheader("📋 세이브 슬롯 선택")
            
            cols = st.columns(3)
            for i, s in enumerate(slots[:3]):
                with cols[i]:
                    st.info(f"**슬롯 {s['slot']}**\n\n"
                           f"📍 {s['pos']}\n"
                           f"💰 {s['money']:,}냥\n"
                           f"📅 {s['year']}년 {s['month']}월")
            
            slot_choice = st.selectbox("슬롯 번호", options=[1, 2, 3], index=0)
            
            if st.button("🎮 게임 시작", use_container_width=True):
                selected = next((s for s in slots if s['slot'] == slot_choice), None)
                if selected:
                    st.session_state.player = selected
                    st.session_state.settings = settings
                    st.session_state.items_info = items_info
                    st.session_state.merc_data = merc_data
                    st.session_state.villages = villages
                    st.session_state.initial_stocks = initial_stocks
                    # ✅ 여기에 city_settings 저장 추가
                    st.session_state.city_settings = city_settings
                    st.session_state.last_time_update = time.time()
                    st.session_state.trade_logs = {}
                    
                    market_data = {}
                    for v_name, v_data in villages.items():
                        if v_name != "용병 고용소":
                            market_data[v_name] = {}
                            for item_name, stock in v_data['items'].items():
                                market_data[v_name][item_name] = {
                                    'stock': stock,
                                    'price': items_info[item_name]['base']
                                }
                    st.session_state.market_data = market_data
                    
                    st.session_state.game_started = True
                    st.rerun()
                else:
                    st.error("❌ 존재하지 않는 슬롯입니다.")
    
    else:
        player = st.session_state.player
        settings = st.session_state.settings
        items_info = st.session_state.items_info
        merc_data = st.session_state.merc_data
        villages = st.session_state.villages
        market_data = st.session_state.market_data
        initial_stocks = st.session_state.initial_stocks
        
        current_time = time.time()
        if current_time - st.session_state.last_update > 1:
            player, events = update_game_time(player, settings, market_data, initial_stocks)
            if events:
                st.session_state.events = events
            st.session_state.last_update = current_time
        
        update_prices(settings, items_info, market_data, initial_stocks, st.session_state.city_settings)
        cw, tw = get_weight(player, items_info, merc_data)
        
        if st.session_state.events:
            for event_type, message in st.session_state.events:
                st.markdown(f"<div class='event-message'>{message}</div>", unsafe_allow_html=True)
            st.session_state.events = []
        
       # 상단 정보
        st.title(f"🏯 {player['pos']}")
        
        col1, col2, col3, col4 = st.columns(4)
        money_placeholder = col1.empty()
        money_placeholder.metric("💰 소지금", f"{player['money']:,}냥")
        
        weight_placeholder = col2.empty()
        weight_placeholder.metric("⚖️ 무게", f"{cw}/{tw}근")
        
        time_placeholder = col3.empty()
        time_placeholder.metric("📅 시간", get_time_display(player))
        
        # ✅ settings에서 seconds_per_month 가져와서 남은 시간 계산
        seconds_per_month = int(settings.get('seconds_per_month', 180))
        elapsed = time.time() - st.session_state.last_time_update
        remaining = max(0, seconds_per_month - int(elapsed))
        time_left_placeholder = col4.empty()
        time_left_placeholder.metric("⏰ 다음 달까지", f"{remaining}초")
        
        st.markdown(f"<div style='text-align: right; color: #666; margin-bottom: 10px;'>📊 거래 횟수: {st.session_state.stats['trade_count']}회</div>", unsafe_allow_html=True)
        
        st.divider()
        
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 거래", "📦 인벤토리", "⚔️ 용병", "📊 통계", "⚙️ 기타"])
        
        with tab1:
            if player['pos'] == "용병 고용소":
                st.subheader("⚔️ 용병 고용")
                if merc_data:
                    for name, data in merc_data.items():
                        owned = "✓" if name in player['mercs'] else ""
                        with st.container():
                            st.info(f"**{name}** {owned}\n\n"
                                   f"💰 고용비: {data['price']:,}냥\n"
                                   f"⚖️ 무게보너스: +{data['w_bonus']}근")
                            if owned:
                                st.button(f"✅ 이미 고용됨", key=f"merc_{name}", disabled=True, use_container_width=True)
                            else:
                                if st.button(f"⚔️ {name} 고용", key=f"merc_{name}", use_container_width=True):
                                    if player['money'] >= data['price']:
                                        player['money'] -= data['price']
                                        player['mercs'].append(name)
                                        cw, tw = get_weight(player, items_info, merc_data)
                                        weight_placeholder.metric("⚖️ 무게", f"{cw}/{tw}근")
                                        money_placeholder.metric("💰 소지금", f"{player['money']:,}냥")
                                        st.success(f"✅ {name} 고용 완료!")
                                        st.rerun()
                                    else:
                                        st.error("❌ 잔액 부족")
                else:
                    st.warning("고용 가능한 용병이 없습니다.")
            
            elif player['pos'] in market_data:
                items = list(market_data[player['pos']].keys())
                if items:
                    st.subheader(f"🛒 {player['pos']} 시세")
                    
                    for item_name in items:
                        d = market_data[player['pos']][item_name]
                        base_price = items_info[item_name]['base']
                        
                        if d['price'] > base_price * 1.2:
                            price_class = "price-up"
                            trend = "▲▲"
                        elif d['price'] > base_price:
                            price_class = "price-up"
                            trend = "▲"
                        elif d['price'] < base_price * 0.8:
                            price_class = "price-down"
                            trend = "▼▼"
                        elif d['price'] < base_price:
                            price_class = "price-down"
                            trend = "▼"
                        else:
                            price_class = "price-same"
                            trend = "■"
                        
                        with st.container():
                            st.markdown(f"**{item_name}** {trend}")
                            
                            # 저장된 결과 로그 표시
                            result_key = f"result_{player['pos']}_{item_name}"
                            if result_key in st.session_state:
                                st.markdown(f"<div class='trade-complete'>{st.session_state[result_key]}</div>", unsafe_allow_html=True)
                            
                            col1, col2, col3 = st.columns([2,1,1])
                            price_ph = col1.empty()
                            price_ph.markdown(f"<span class='{price_class}'>{d['price']:,}냥</span>", unsafe_allow_html=True)
                            
                            stock_ph = col2.empty()
                            stock_ph.write(f"📦 {d['stock']}개")
                            
                            max_buy = calculate_max_purchase(
                                player, items_info, market_data, 
                                player['pos'], item_name, d['price']
                            )
                            max_ph = col3.empty()
                            max_ph.write(f"⚡ {max_buy}개")
                            
                            col_a, col_b, col_c = st.columns([2,1,1])
                            
                            default_qty = st.session_state.last_qty.get(f"{player['pos']}_{item_name}", "1")
                            qty = col_a.text_input("수량", value=default_qty, key=f"qty_{player['pos']}_{item_name}", label_visibility="collapsed")
                            
                            # 진행상황 표시 영역
                            progress_ph = st.empty()
                            
                            # 저장된 로그가 있으면 표시
                            for key in list(st.session_state.trade_logs.keys()):
                                if key.startswith(f"{player['pos']}_{item_name}"):
                                    with progress_ph.container():
                                        st.markdown("<div class='trade-progress'>", unsafe_allow_html=True)
                                        for log in st.session_state.trade_logs[key][-10:]:
                                            st.markdown(f"<div class='trade-line'>{log}</div>", unsafe_allow_html=True)
                                        st.markdown("</div>", unsafe_allow_html=True)
                                    break
                            
                            if col_b.button("💰 매수", key=f"buy_{item_name}", use_container_width=True):
                                try:
                                    qty_int = int(qty)
                                    if qty_int > 0:
                                        actual_qty = min(qty_int, max_buy)
                                        if actual_qty > 0:
                                            st.session_state.last_qty[f"{player['pos']}_{item_name}"] = "1"
                                            
                                            log_key = f"{player['pos']}_{item_name}_{time.time()}"
                                            
                                            bought, spent = process_buy(
                                                player, items_info, market_data,
                                                player['pos'], item_name, actual_qty, progress_ph, log_key
                                            )
                                            
                                            if bought > 0:
                                                st.session_state.stats['total_bought'] += bought
                                                st.session_state.stats['total_spent'] += spent
                                                st.session_state.stats['trade_count'] += 1
                                                
                                                money_placeholder.metric("💰 소지금", f"{player['money']:,}냥")
                                                cw, tw = get_weight(player, items_info, merc_data)
                                                weight_placeholder.metric("⚖️ 무게", f"{cw}/{tw}근")
                                                
                                                price_ph.markdown(f"<span class='{price_class}'>{d['price']:,}냥</span>", unsafe_allow_html=True)
                                                stock_ph.write(f"📦 {d['stock']}개")
                                                
                                                new_max_buy = calculate_max_purchase(
                                                    player, items_info, market_data, 
                                                    player['pos'], item_name, d['price']
                                                )
                                                max_ph.write(f"⚡ {new_max_buy}개")
                                                
                                                avg_price = spent // bought
                                                # 초록색 결과 로그를 세션에 저장
                                                result_key = f"result_{player['pos']}_{item_name}"
                                                st.session_state[result_key] = f"✅ 총 {bought}개 매수 완료! (총 {spent:,}냥 | 평균가: {avg_price}냥)"
                                                
                                                # 저장된 결과 로그 표시
                                                if result_key in st.session_state:
                                                    st.markdown(f"<div class='trade-complete'>{st.session_state[result_key]}</div>", unsafe_allow_html=True)
                                            else:
                                                st.error("❌ 구매 실패")
                                        else:
                                            st.error("❌ 구매 가능한 수량이 없습니다")
                                    else:
                                        st.error("❌ 0보다 큰 수량을 입력하세요")
                                except ValueError:
                                    st.error("❌ 올바른 숫자를 입력하세요")
                            
                            if col_c.button("📦 매도", key=f"sell_{item_name}", use_container_width=True):
                                try:
                                    qty_int = int(qty)
                                    if qty_int > 0:
                                        max_sell = player['inv'].get(item_name, 0)
                                        actual_qty = min(qty_int, max_sell)
                                        if actual_qty > 0:
                                            st.session_state.last_qty[f"{player['pos']}_{item_name}"] = "1"
                                            
                                            log_key = f"{player['pos']}_{item_name}_{time.time()}"
                                            
                                            sold, earned = process_sell(
                                                player, items_info, market_data,
                                                player['pos'], item_name, actual_qty, progress_ph, log_key
                                            )
                                            
                                            if sold > 0:
                                                st.session_state.stats['total_sold'] += sold
                                                st.session_state.stats['total_earned'] += earned
                                                st.session_state.stats['trade_count'] += 1
                                                
                                                money_placeholder.metric("💰 소지금", f"{player['money']:,}냥")
                                                cw, tw = get_weight(player, items_info, merc_data)
                                                weight_placeholder.metric("⚖️ 무게", f"{cw}/{tw}근")
                                                
                                                price_ph.markdown(f"<span class='{price_class}'>{d['price']:,}냥</span>", unsafe_allow_html=True)
                                                stock_ph.write(f"📦 {d['stock']}개")
                                                
                                                new_max_buy = calculate_max_purchase(
                                                    player, items_info, market_data, 
                                                    player['pos'], item_name, d['price']
                                                )
                                                max_ph.write(f"⚡ {new_max_buy}개")
                                                
                                                avg_price = earned // sold
                                                # 초록색 결과 로그를 세션에 저장
                                                result_key = f"result_{player['pos']}_{item_name}"
                                                st.session_state[result_key] = f"✅ 총 {sold}개 매도 완료! (총 {earned:,}냥 | 평균가: {avg_price}냥)"
                                                
                                                # 저장된 결과 로그 표시
                                                if result_key in st.session_state:
                                                    st.markdown(f"<div class='trade-complete'>{st.session_state[result_key]}</div>", unsafe_allow_html=True)
                                            else:
                                                st.error("❌ 판매 실패")
                                        else:
                                            st.error("❌ 판매 가능한 수량이 없습니다")
                                    else:
                                        st.error("❌ 0보다 큰 수량을 입력하세요")
                                except ValueError:
                                    st.error("❌ 올바른 숫자를 입력하세요")
                            
                            st.divider()
                else:
                    st.warning("이 마을에는 판매 품목이 없습니다.")
            else:
                st.warning("시장 정보를 불러올 수 없습니다.")
        
        with tab2:
            st.subheader("📦 내 인벤토리")
            if player['inv']:
                total_value = 0
                total_weight = 0
                
                for item, qty in sorted(player['inv'].items()):
                    if qty > 0 and item in items_info:
                        item_value = items_info[item]['base'] * qty
                        item_weight = items_info[item]['w'] * qty
                        total_value += item_value
                        total_weight += item_weight
                        
                        col1, col2, col3 = st.columns([2,1,1])
                        col1.write(f"• **{item}**")
                        col2.write(f"{qty}개")
                        col3.write(f"{item_weight}근")
                
                st.divider()
                col1, col2 = st.columns(2)
                col1.info(f"💰 총 가치: {total_value:,}냥")
                col2.info(f"⚖️ 총 무게: {total_weight}/{tw}근")
            else:
                st.write("인벤토리가 비어있습니다")
        
        with tab3:
            st.subheader("⚔️ 내 용병")
            if player['mercs']:
                total_bonus = 0
                for merc in player['mercs']:
                    if merc in merc_data:
                        bonus = merc_data[merc]['w_bonus']
                        total_bonus += bonus
                        st.write(f"• **{merc}** (무게 +{bonus}근)")
                
                st.info(f"⚖️ 총 무게 보너스: +{total_bonus}근")
            else:
                st.write("고용한 용병이 없습니다")
        
        with tab4:
            st.subheader("📊 거래 통계")
            stats = st.session_state.stats
            
            col1, col2 = st.columns(2)
            col1.metric("총 구매", f"{stats['total_bought']}개")
            col2.metric("총 판매", f"{stats['total_sold']}개")
            
            col3, col4 = st.columns(2)
            col3.metric("총 지출", f"{stats['total_spent']:,}냥")
            col4.metric("총 수익", f"{stats['total_earned']:,}냥")
            
            if stats['total_spent'] > 0:
                profit = stats['total_earned'] - stats['total_spent']
                profit_rate = (profit / stats['total_spent']) * 100
                st.metric("순이익", f"{profit:+,}냥", f"{profit_rate:+.1f}%")
            
            st.metric("거래 횟수", f"{stats['trade_count']}회")
        
        with tab5:
            st.subheader("⚙️ 게임 메뉴")
            
            st.write("**🚚 마을 이동**")
            towns = list(villages.keys())
            if player['pos'] in villages:
                curr_v = villages[player['pos']]
                move_options = []
                move_dict = {}
                
                for t in towns:
                    if t != player['pos']:
                        dist = math.sqrt((curr_v['x'] - villages[t]['x'])**2 + (curr_v['y'] - villages[t]['y'])**2)
                        cost = int(dist * settings.get('travel_cost', 15))
                        option_text = f"{t} (💰 {cost:,}냥)"
                        move_options.append(option_text)
                        move_dict[option_text] = (t, cost)
                
                if move_options:
                    selected = st.selectbox("이동할 마을", move_options)
                    if st.button("🚀 이동", use_container_width=True):
                        dest, cost = move_dict[selected]
                        if player['money'] >= cost:
                            player['money'] -= cost
                            # 현재 도시의 로그 삭제 (이동 전 도시)
                            current_city = player['pos']
                            keys_to_delete = []
                            for key in list(st.session_state.trade_logs.keys()):
                                if key.startswith(f"{current_city}_"):
                                    keys_to_delete.append(key)
                            for key in keys_to_delete:
                                del st.session_state.trade_logs[key]
                            # 결과 로그도 삭제
                            result_keys_to_delete = []
                            for key in list(st.session_state.keys()):
                                if key.startswith(f"result_{current_city}_"):
                                    result_keys_to_delete.append(key)
                            for key in result_keys_to_delete:
                                del st.session_state[key]
                            
                            player['pos'] = dest
                            money_placeholder.metric("💰 소지금", f"{player['money']:,}냥")
                            st.success(f"✅ {dest}로 이동했습니다!")
                            st.rerun()
                        else:
                            st.error("❌ 잔액 부족")
                else:
                    st.write("이동 가능한 마을이 없습니다")
            
            st.divider()
            
            st.write("**⏰ 시간 시스템**")
            st.info(f"30초 = 게임 1달\n\n현재 시간: {get_time_display(player)}")
            
            st.divider()
            
            if st.button("💾 저장", use_container_width=True):
                if save_player_data(doc, player, st.session_state.stats, st.session_state.device_id):
                    st.success("✅ 저장 완료!")
            
            if st.button("🚪 메인으로", use_container_width=True):
                st.session_state.game_started = False
                st.cache_data.clear()
                st.rerun()
        
        # 0.5초마다 자동 새로고침
        time.sleep(0.5)
        st.rerun()


























