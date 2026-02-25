import streamlit as st
from streamlit_autorefresh import st_autorefresh  # 이 줄을 추가
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
        return None, None, None, None, None, None  # 6개 반환
    
    try:
        # 설정 데이터 로드
        set_ws = doc.worksheet("Setting_Data")
        settings = {r['변수명']: float(r['값']) for r in set_ws.get_all_records()}
        # volatility 값이 settings 딕셔너리에 자동으로 포함됨
        
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
        
        # ✅ city_settings 관련 코드 모두 제거
        
        return settings, items_info, merc_data, villages, initial_stocks, slots  # 6개 반환
    
    except Exception as e:
        st.error(f"❌ 데이터 로드 에러: {e}")
        return None, None, None, None, None, None  # 6개 반환

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
    
    seconds_per_month = int(settings.get('seconds_per_month', 180))
    seconds_per_week = seconds_per_month / 4
    elapsed = current_time - st.session_state.last_time_update
    weeks_passed = int(elapsed // seconds_per_week)
    
    events = []
    
    if weeks_passed > 0:
        for _ in range(weeks_passed):
            player['week'] += 1
            if player['week'] > 4:
                player['week'] = 1
                player['month'] += 1
                
                # ⭐ [핵심 추가] 월이 바뀌면 재고를 초기화합니다.
                for v_name, v_items in initial_stocks.items():
                    if v_name in market_data:
                        for item_name, initial_stock_val in v_items.items():
                            if item_name in market_data[v_name]:
                                market_data[v_name][item_name]['stock'] = initial_stock_val
                
                events.append(("month", "📅 새 달이 밝아 모든 마을의 재고가 초기화되었습니다!"))
                
                if player['month'] > 12:
                    player['month'] = 1
                    player['year'] += 1
        
        st.session_state.last_time_update += weeks_passed * seconds_per_week
        
        # 주차 알림 저장
        st.session_state.event_display = {
            "message": f"🌟 {player['year']}년 {player['month']}월 {player['week']}주차 소식이 도착했습니다.",
            "time": time.time()
        }
    
    return player, events
    
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
        
        # ✅ season effect 관련 코드 완전히 삭제됨
        
        # volatility -> inventoryResponsivePrice로 변경
        inventoryResponsivePrice = settings.get('inventoryResponsivePrice', 5000)
        event_probability = inventoryResponsivePrice / 1000000
        
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
    month_names = ["1월", "2월", "3월", "4월", "5월", "6월", 
                   "7월", "8월", "9월", "10월", "11월", "12월"]
    return f"{player['year']}년 {month_names[player['month']-1]} {player['week']}주차"

# --- 6. 게임 로직 함수들 ---
def update_prices(settings, items_info, market_data, initial_stocks=None):
    if initial_stocks is None:
        initial_stocks = st.session_state.get('initial_stocks', {})
    
    min_price_rate = settings.get('min_price_rate', 0.4)
    max_price_rate = settings.get('max_price_rate', 3.0)
    
    inventoryResponsivePrice = settings.get('inventoryResponsivePrice', 5000)
    
    for v_name, v_data in market_data.items():
        if v_name == "용병 고용소":
            continue
            
        for i_name, i_info in v_data.items():
            if i_name in items_info:
                base = items_info[i_name]['base']
                stock = i_info['stock']
                
                # ✅ 절대 재고량으로 가격 결정
                if stock < 100:  # 재고 100개 미만
                    price_factor = 2.0  # 2배 비쌈
                elif stock < 500:  # 재고 500개 미만
                    price_factor = 1.5  # 1.5배 비쌈
                elif stock < 1000:  # 재고 1000개 미만
                    price_factor = 1.2  # 1.2배 비쌈
                elif stock < 2000:  # 재고 2000개 미만
                    price_factor = 1.0  # 기준가
                elif stock < 5000:  # 재고 5000개 미만
                    price_factor = 0.8  # 0.8배 쌈
                else:  # 재고 5000개 이상
                    price_factor = 0.6  # 0.6배 쌈
                
                i_info['price'] = int(base * price_factor)
                
                        
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
    batch_size = 100 # 연속 체결 단위
    
    st.session_state.trade_logs[log_key] = []
    
    while total_bought < qty:
        # 1. 매 루프마다 가격 업데이트 (재고 감소 반영)
        update_prices(st.session_state.settings, items_info, market_data, st.session_state.initial_stocks)
        target = market_data[pos][item_name]
        cw, tw = get_weight(player, items_info, st.session_state.merc_data)
        
        # 2. 현재 시점 최대 구매 가능 계산 (돈, 무게, 재고)
        can_pay = player['money'] // target['price'] if target['price'] > 0 else 0
        can_load = (tw - cw) // items_info[item_name]['w'] if items_info[item_name]['w'] > 0 else 999999
        
        # 3. 이번 턴에 체결할 양 (남은양, 100개단위, 재고, 돈, 무게 중 최소값)
        current_batch = min(batch_size, qty - total_bought, target['stock'], can_pay, can_load)
        
        if current_batch <= 0:
            break # 더 이상 살 수 없으면 중단
            
        # 4. 실제 데이터 반영 (돈 마이너스 방지)
        cost = current_batch * target['price']
        player['money'] -= cost
        total_spent += cost
        player['inv'][item_name] = player['inv'].get(item_name, 0) + current_batch
        target['stock'] -= current_batch
        total_bought += current_batch
        
        # 5. 실시간 로그 표시
        log_msg = f"➤ {total_bought}/{qty} 구매 중... (체결가: {target['price']}냥)"
        st.session_state.trade_logs[log_key].append(log_msg)
        
        with progress_placeholder.container():
            for log in st.session_state.trade_logs[log_key][-5:]:
                st.markdown(f"<div class='trade-line'>{log}</div>", unsafe_allow_html=True)
        
        time.sleep(0.05) # 체결되는 느낌을 위한 짧은 대기

    # 최종 결과 저장
    if total_bought > 0:
        st.session_state.last_trade_result = f"✅ {item_name} 총 {total_bought}개 구매 완료! (총 {total_spent:,}냥)"
    
    return total_bought, total_spent

def process_sell(player, items_info, market_data, pos, item_name, qty, progress_placeholder, log_key):
    total_sold = 0
    total_earned = 0
    batch_size = 100
    
    st.session_state.trade_logs[log_key] = []
    
    while total_sold < qty:
        update_prices(st.session_state.settings, items_info, market_data, st.session_state.initial_stocks)
        current_price = market_data[pos][item_name]['price']
        
        # 내가 가진 개수와 100개 단위 중 작은 값
        current_batch = min(batch_size, qty - total_sold, player['inv'].get(item_name, 0))
        
        if current_batch <= 0:
            break
            
        # 데이터 반영
        player['money'] += current_batch * current_price
        player['inv'][item_name] -= current_batch
        market_data[pos][item_name]['stock'] += current_batch
        total_sold += current_batch
        total_earned += current_batch * current_price
        
        log_msg = f"➤ {total_sold}/{qty} 판매 중... (체결가: {current_price}냥)"
        st.session_state.trade_logs[log_key].append(log_msg)
        
        with progress_placeholder.container():
            for log in st.session_state.trade_logs[log_key][-5:]:
                st.markdown(f"<div class='trade-line'>{log}</div>", unsafe_allow_html=True)
        
        time.sleep(0.05)

    if total_sold > 0:
        st.session_state.last_trade_result = f"✅ {item_name} 총 {total_sold}개 판매 완료! (총 {total_earned:,}냥)"
        
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
            
            settings, items_info, merc_data, villages, initial_stocks, slots = load_game_data()        
            
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
                
                # 게임 시작 부분 (슬롯 선택 후)
                if st.button("🎮 게임 시작", use_container_width=True):
                    selected = next((s for s in slots if s['slot'] == slot_choice), None)
                    if selected:
                        st.session_state.player = selected
                        st.session_state.settings = settings
                        st.session_state.items_info = items_info
                        st.session_state.merc_data = merc_data
                        st.session_state.villages = villages
                        st.session_state.initial_stocks = initial_stocks
                        st.session_state.last_time_update = time.time()
                        st.session_state.trade_logs = {}
                        
                        market_data = {}
                        for v_name, v_data in villages.items():
                            if v_name != "용병 고용소":
                                market_data[v_name] = {}
                                for item_name, stock in v_data['items'].items():
                                    market_data[v_name][item_name] = {
                                        'stock': stock,
                                        'price': items_info[item_name]['base']  # 임시로 base 설정
                                    }
                        
                        # ✅ 추가: market_data 생성 후 update_prices() 호출하여 가격 계산
                        update_prices(settings, items_info, market_data, initial_stocks)
                        
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
        
# --- 7. 메인 실행 ---
doc = connect_gsheet()
init_session_state()

# ⭐ 1. 자동 새로고침 (반드시 코드 최상단에 위치)
# --- 아래 내용을 완전히 삭제하세요 ---
from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=1000, key="gametimer_refresh")
# -------------------------------

if doc:
    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        st.markdown("---")
        
        # 데이터 로드
        settings, items_info, merc_data, villages, initial_stocks, slots = load_game_data()        
        
        if slots:
            st.subheader("📋 세이브 슬롯 선택")
            cols = st.columns(3)
            for i, s in enumerate(slots[:3]):
                with cols[i]:
                    st.info(f"**슬롯 {s['slot']}**\n\n📍 {s['pos']}\n💰 {s['money']:,}냥\n📅 {s['year']}년 {s['month']}월")
            
            slot_choice = st.selectbox("슬롯 번호", options=[1, 2, 3], index=0)
            
            if st.button("🎮 게임 시작", use_container_width=True):
                selected = next((s for s in slots if s['slot'] == slot_choice), None)
                if selected:
                    # ✅ 모든 중요 데이터를 세션에 저장 (NameError 방지 핵심)
                    st.session_state.player = selected
                    st.session_state.settings = settings
                    st.session_state.items_info = items_info
                    st.session_state.merc_data = merc_data
                    st.session_state.villages = villages
                    st.session_state.initial_stocks = initial_stocks
                    st.session_state.last_time_update = time.time()
                    st.session_state.trade_logs = {}
                    
                    market_data = {}
                    for v_name, v_data in villages.items():
                        if v_name != "용병 고용소":
                            market_data[v_name] = {}
                            for item_name, stock in v_data['items'].items():
                                market_data[v_name][item_name] = {'stock': stock, 'price': items_info[item_name]['base']}
                    
                    st.session_state.market_data = market_data
                    st.session_state.game_started = True
                    st.rerun()
    
    else:
        # 🎮 2. 게임 시작 후 데이터 불러오기
        player = st.session_state.player
        settings = st.session_state.settings
        items_info = st.session_state.items_info
        merc_data = st.session_state.merc_data
        market_data = st.session_state.market_data
        initial_stocks = st.session_state.initial_stocks
        villages = st.session_state.villages  # 👈 이제 NameError가 나지 않습니다.

        # 🕒 3. 시간 시스템 업데이트
        # update_game_time 함수 내에서 기준점을 += 연산으로 밀어줘야 폭주를 막습니다.
        player, _ = update_game_time(player, settings, market_data, initial_stocks)

        # ⚖️ 4. 가격 및 무게 업데이트
        update_prices(settings, items_info, market_data, initial_stocks)
        cw, tw = get_weight(player, items_info, merc_data)

        # 📢 5. 상단 알림 메시지 (5초 노출 로직)
        if 'event_display' in st.session_state:
            ed = st.session_state.event_display
            if time.time() - ed['time'] < 5:
                st.info(ed['message'])
            else:
                del st.session_state.event_display
        
        # --- 상단 UI 표시 ---
        # 상단 마을 이름 표시 아래에 추가
        st.title(f"🏯 {player['pos']}")
        
        if 'last_trade_result' in st.session_state:
            st.success(st.session_state.last_trade_result)
            # 선택사항: 사용자가 내용을 확인했으면 사라지게 하고 싶을 때
            # if st.button("알림 지우기"): del st.session_state.last_trade_result

        top_col1, top_col2 = st.columns(2)
        top_col1.metric("💰 소지금", f"{player['money']:,}냥")
        top_col2.metric("⚖️ 무게", f"{cw}/{tw}근")

        # ⭐ 시간 전용 프래그먼트 (새로고침 없이 내부 데이터만 갱신)
        @st.fragment(run_every="1s")
        def sync_time_ui():
            # 백그라운드에서 시간 및 재고 데이터 갱신 (리런 없이 실행)
            # 이 함수가 내부적으로 player['week']와 market_data를 직접 수정합니다.
            st.session_state.player, _ = update_game_time(
                st.session_state.player, 
                st.session_state.settings, 
                st.session_state.market_data, 
                st.session_state.initial_stocks
            )
            
            # 현재 남은 시간 계산
            sec_per_month = int(settings.get('seconds_per_month', 180))
            sec_per_week = sec_per_month / 4
            elapsed = time.time() - st.session_state.last_time_update
            remaining = max(0, int(sec_per_week - elapsed))
            
            t_col1, t_col2 = st.columns(2)
            # 현재 세션의 최신 시간 정보를 가져와 표시
            t_col1.metric("📅 시간", get_time_display(st.session_state.player))
            t_col2.metric("⏰ 다음 주까지", f"{int(remaining)}초")

        sync_time_ui()

        # 📑 7. 탭 메뉴 구성
        if 'current_tab' not in st.session_state:
            st.session_state.current_tab = 0
            
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 저잣거리", "📦 인벤토리", "⚔️ 용병", "📊 통계", "⚙️ 이동"])
        
        with tab1:
            if player['pos'] == "용병 고용소":
                st.subheader("⚔️ 용병 고용")
                if merc_data:
                    # settings에서 최대 용병 수 가져오기
                    max_mercs = int(settings.get('max_mercenaries', 5))
                    
                    # 현재 고용된 용병 수 표시
                    st.info(f"**현재 용병: {len(player['mercs'])}/{max_mercs}명**")
                    
                    for name, data in merc_data.items():
                        # 같은 이름의 용병이 몇 명 있는지 확인
                        count = sum(1 for m in player['mercs'] if m == name)
                        
                        with st.container():
                            st.info(f"**{name}** (고용중: {count}명)\n\n"
                                   f"💰 고용비: {data['price']:,}냥\n"
                                   f"⚖️ 무게보너스: +{data['w_bonus']}근")
                            
                            # 최대 인원 제한만 확인
                            if len(player['mercs']) >= max_mercs:
                                st.button(f"❌ 최대 인원({max_mercs}명)", key=f"merc_{name}_full", disabled=True, use_container_width=True)
                            else:
                                if st.button(f"⚔️ {name} 고용", key=f"merc_{name}_{count}", use_container_width=True):
                                    if player['money'] >= data['price']:
                                        player['money'] -= data['price']
                                        player['mercs'].append(name)
                                        cw, tw = get_weight(player, items_info, merc_data)
                                        weight_placeholder.metric("⚖️ 무게", f"{cw}/{tw}근")
                                        money_placeholder.metric("💰 소지금", f"{player['money']:,}냥")
                                        st.success(f"✅ {name} 고용 완료! (총 {len(player['mercs'])}/{max_mercs}명)")
                                        st.rerun()
                                    else:
                                        st.error("❌ 잔액 부족")
                else:
                    st.warning("고용 가능한 용병이 없습니다.")
            
            elif player['pos'] in market_data:
                # ... 일반 마을 거래 코드 ...
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
                            
                            # --- 💰 매수 버튼 로직 ---
                            if col_b.button("💰 매수", key=f"buy_{item_name}", use_container_width=True):
                                try:
                                    qty_int = int(qty)
                                    if qty_int > 0:
                                        # 1. 100개씩 끊어서 살 수 있는 로직(process_buy) 호출
                                        # 실제 최대 가능 수량은 함수 내부에서 다시 정밀하게 계산하므로 qty_int를 그대로 넘깁니다.
                                        log_key = f"{player['pos']}_{item_name}_{time.time()}"
                                        
                                        bought, spent = process_buy(
                                            player, items_info, market_data,
                                            player['pos'], item_name, qty_int, progress_ph, log_key
                                        )
                                        
                                        if bought > 0:
                                            # 통계 업데이트
                                            st.session_state.stats['total_bought'] += bought
                                            st.session_state.stats['total_spent'] += spent
                                            st.session_state.stats['trade_count'] += 1
                                            
                                            # ⭐ 핵심: 결과 메시지를 전역 세션에 저장 (상단 UI에서 출력하기 위함)
                                            avg_price = spent // bought
                                            st.session_state.last_trade_result = f"✅ {item_name} 총 {bought}개 매수 완료! (총 {spent:,}냥 | 평균가: {avg_price}냥)"
                                            
                                            # 입력을 '1'로 초기화 (선택 사항)
                                            st.session_state.last_qty[f"{player['pos']}_{item_name}"] = "1"
                                            
                                            # 화면 전체를 갱신하여 상단 소지금/무게/로그를 한꺼번에 업데이트
                                            st.rerun()
                                        else:
                                            st.error("❌ 구매 가능한 수량이 없거나 돈/무게가 부족합니다.")
                                    else:
                                        st.error("❌ 0보다 큰 수량을 입력하세요")
                                except ValueError:
                                    st.error("❌ 올바른 숫자를 입력하세요")

                            # --- 📦 매도 버튼 로직 ---
                            if col_c.button("📦 매도", key=f"sell_{item_name}", use_container_width=True):
                                try:
                                    qty_int = int(qty)
                                    if qty_int > 0:
                                        log_key = f"{player['pos']}_{item_name}_{time.time()}"
                                        
                                        # 1. 100개씩 연속 체결하는 함수 호출
                                        sold, earned = process_sell(
                                            player, items_info, market_data,
                                            player['pos'], item_name, qty_int, progress_ph, log_key
                                        )
                                        
                                        if sold > 0:
                                            # 통계 업데이트 (기존 코드 유지)
                                            st.session_state.stats['total_sold'] += sold
                                            st.session_state.stats['total_earned'] += earned
                                            st.session_state.stats['trade_count'] += 1
                                            
                                            # ⭐ [중요] 매수와 똑같은 변수명을 사용하여 결과를 저장합니다.
                                            avg_price = earned // sold
                                            st.session_state.last_trade_result = f"✅ {item_name} 총 {sold}개 매도 완료! (수익: {earned:,}냥 | 평균가: {avg_price}냥)"
                                            
                                            # 입력값 초기화
                                            st.session_state.last_qty[f"{player['pos']}_{item_name}"] = "1"
                                            
                                            # ⭐ [중요] 화면을 새로고침해야 상단 UI에 결과가 뜹니다.
                                            st.rerun() 
                                        else:
                                            st.error("❌ 판매할 수 있는 아이템이 없습니다.")
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
                # settings에서 해고 환불 비율 가져오기
                fire_refund_rate = settings.get('fire_refund_rate', 0.7)
                
                total_bonus = 0
                
                # 용병 목록을 딕셔너리로 변환하여 카운트
                merc_count = {}
                for merc in player['mercs']:
                    merc_count[merc] = merc_count.get(merc, 0) + 1
                
                for merc, count in merc_count.items():
                    if merc in merc_data:
                        bonus = merc_data[merc]['w_bonus']
                        refund = int(merc_data[merc]['price'] * fire_refund_rate)
                        total_bonus += bonus * count
                        
                        col1, col2, col3, col4 = st.columns([2,1,1,1])
                        col1.write(f"• **{merc}**")
                        col2.write(f"{count}명")
                        col3.write(f"무게 +{bonus * count}근")
                        
                        # 해고 버튼
                        if col4.button(f"❌ 해고", key=f"fire_{merc}", use_container_width=True):
                            # 해당 용병 1명 제거
                            for i, m in enumerate(player['mercs']):
                                if m == merc:
                                    player['mercs'].pop(i)
                                    player['money'] += refund
                                    break
                            st.success(f"✅ {merc} 1명 해고 완료! ({refund:,}냥 환불)")
                            st.rerun()
                
                st.info(f"⚖️ 총 무게 보너스: +{total_bonus}근")
                st.caption(f"💰 해고 시 {int(fire_refund_rate*100)}% 환불")
            else:
                st.write("고용한 용병이 없습니다")

        with tab4:
            st.subheader("📊 거래 통계")
            
            # 전체 통계 요약
            col1, col2 = st.columns(2)
            with col1:
                st.metric("💰 총 구매액", f"{st.session_state.stats['total_spent']:,}냥")
                st.metric("📦 총 구매량", f"{st.session_state.stats['total_bought']:,}개")
                st.metric("🔄 총 거래 횟수", f"{st.session_state.stats['trade_count']}회")
            
            with col2:
                st.metric("💵 총 판매액", f"{st.session_state.stats['total_earned']:,}냥")
                st.metric("📦 총 판매량", f"{st.session_state.stats['total_sold']:,}개")
                
                # 순이익 계산
                net_profit = st.session_state.stats['total_earned'] - st.session_state.stats['total_spent']
                profit_color = "🔴" if net_profit < 0 else "🟢"
                st.metric(f"{profit_color} 순이익", f"{net_profit:,}냥")
            
            st.divider()
            
            # 거래 내역 (최근 거래 로그)
            st.subheader("📋 최근 거래 내역")
            
            if st.session_state.trade_logs:
                # 최근 10개 거래 로그만 표시
                recent_logs = []
                for key, logs in list(st.session_state.trade_logs.items())[-5:]:
                    if logs:
                        recent_logs.extend(logs[-3:])  # 각 거래의 마지막 3개 로그만
                
                if recent_logs:
                    for log in recent_logs[-10:]:  # 최대 10개만 표시
                        st.markdown(f"<div class='trade-line'>{log}</div>", unsafe_allow_html=True)
                else:
                    st.info("거래 내역이 없습니다.")
            else:
                st.info("거래 내역이 없습니다.")
            
            st.divider()
            
            # 통계 초기화 버튼
            if st.button("🔄 통계 초기화", use_container_width=True):
                st.session_state.stats = {
                    'total_bought': 0,
                    'total_sold': 0,
                    'total_spent': 0,
                    'total_earned': 0,
                    'trade_count': 0
                }
                st.rerun()
        
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

                # --- 마을 이동 버튼 로직 부분 ---
                if move_options:
                    selected = st.selectbox("이동할 마을", move_options)
                    if st.button("🚀 이동", use_container_width=True):
                        dest, cost = move_dict[selected]
                        if player['money'] >= cost:
                            player['money'] -= cost
                            
                            # 이동 전 도시 이름 저장 (로그 삭제용)
                            current_city = player['pos']
                            
                            # 1. 상세 거래 로그 삭제 (기존 로직)
                            keys_to_delete = [k for k in st.session_state.trade_logs.keys() if k.startswith(f"{current_city}_")]
                            for key in keys_to_delete:
                                del st.session_state.trade_logs[key]
                                
                            result_keys_to_delete = [k for k in st.session_state.keys() if k.startswith(f"result_{current_city}_")]
                            for key in result_keys_to_delete:
                                del st.session_state[key]
                            
                            # ⭐ [추가] 상단 거래 결과 로그(초록색 박스) 삭제
                            if 'last_trade_result' in st.session_state:
                                del st.session_state['last_trade_result']
                            
                            # 2. 위치 변경 및 탭 초기화
                            player['pos'] = dest
                            # ⭐ 탭 인덱스를 0(저잣거리)으로 강제 설정
                            st.session_state.current_tab = 0
                            
                            st.success(f"✅ {dest}(으)로 이동했습니다! (비용: {cost:,}냥)")
                            
                            # 3. ✅ 도시가 바뀌었으므로 '강제 새로고침'
                            # 새로고침 시 current_tab이 0이므로 저잣거리 탭이 열립니다.
                            st.rerun()
                        else:
                            st.error("❌ 잔액이 부족합니다.")
                else:
                    st.write("이동 가능한 마을이 없습니다")
            
            st.divider()
            
            st.write("**⏰ 시간 시스템**")
            st.write(f"30초 = 게임 1달")
            st.write(f"현재 시간: {get_time_display(player)}")
            
            st.divider()
            
            if st.button("💾 저장", use_container_width=True):
                if save_player_data(doc, player, st.session_state.stats, st.session_state.device_id):
                    st.success("✅ 저장 완료!")
            
            if st.button("🚪 메인으로", use_container_width=True):
                st.session_state.game_started = False
                st.cache_data.clear()
                st.rerun()

























































































