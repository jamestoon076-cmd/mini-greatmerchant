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
        
        for row in vil_vals[1:]:
            if not row or not row[0].strip():
                continue
            v_name = row[0].strip()
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

# --- 5. 시간 시스템 함수 ---
def update_game_time(player, settings, market_data, initial_stocks):
    current_time = time.time()
    
    if 'last_time_update' not in st.session_state:
        st.session_state.last_time_update = current_time
        return player, []
    
    elapsed = current_time - st.session_state.last_time_update
    seconds_per_month = 30  # 30초 = 1달 (더 빠르게 체감되도록)
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
        st.session_state.last_update = current_time  # last_update도 함께 업데이트
        
        # 월간 이벤트
        if old_month != player['month'] or old_year != player['year']:
            events.append(("month", f"🌙 {player['year']}년 {player['month']}월이 시작되었습니다!"))
            
            # 재고 초기화 - 현재 도시만 초기화
            reset_count = 0
            current_city = player['pos']
            if current_city in initial_stocks and current_city in market_data:
                for item_name in market_data[current_city]:
                    if item_name in initial_stocks[current_city]:
                        old_stock = market_data[current_city][item_name]['stock']
                        market_data[current_city][item_name]['stock'] = initial_stocks[current_city][item_name]
                        if old_stock != initial_stocks[current_city][item_name]:
                            reset_count += 1
                if reset_count > 0:
                    events.append(("reset", f"🔄 {current_city}의 {reset_count}개 품목 재고 초기화"))
        
        events.append(("week", f"🌟 {player['year']}년 {player['month']}월 {player['week']}주차"))
        
        # 주차별 효과
        if player['week'] == 1:
            events.append(("week_effect", "📅 새 달의 시작! 모든 재고가 보충됩니다."))
            if player['pos'] in initial_stocks and player['pos'] in market_data:
                for item_name in market_data[player['pos']]:
                    if item_name in initial_stocks[player['pos']]:
                        market_data[player['pos']][item_name]['stock'] = initial_stocks[player['pos']][item_name]
        
        # 계절 효과
        season_effects = {
            (3,4,5): ("🌸 봄: 인삼/가죽 수요 증가!", ['인삼', '소가죽', '염색가죽'], 1.2),
            (6,7,8): ("☀️ 여름: 비단 수요 증가!", ['비단'], 1.3),
            (9,10,11): ("🍂 가을: 쌀 수요 증가!", ['쌀'], 1.3),
            (12,1,2): ("❄️ 겨울: 가죽갑옷 수요 급증!", ['가죽갑옷'], 1.5)
        }
        
        for months, (msg, items, factor) in season_effects.items():
            if player['month'] in months:
                events.append(("season", msg))
                for v_name in market_data:
                    for item_name in market_data[v_name]:
                        if item_name in items:
                            market_data[v_name][item_name]['price'] = int(market_data[v_name][item_name]['price'] * factor)
                break
        
        # 가격 변동성 추가 (랜덤 이벤트)
        if random.random() < 0.3:  # 30% 확률로 시세 변동
            vol_item = random.choice(list(market_data[player['pos']].keys()))
            vol_direction = random.choice(["상승", "하락"])
            vol_amount = random.randint(10, 30)
            
            if vol_direction == "상승":
                market_data[player['pos']][vol_item]['price'] = int(market_data[player['pos']][vol_item]['price'] * (1 + vol_amount/100))
                events.append(("volatility", f"📈 {vol_item} 가격 {vol_amount}% 급등!"))
            else:
                market_data[player['pos']][vol_item]['price'] = int(market_data[player['pos']][vol_item]['price'] * (1 - vol_amount/100))
                events.append(("volatility", f"📉 {vol_item} 가격 {vol_amount}% 급락!"))
    
    return player, events

def get_time_display(player):
    month_names = ["1월", "2월", "3월", "4월", "5월", "6월", 
                   "7월", "8월", "9월", "10월", "11월", "12월"]
    return f"{player['year']}년 {month_names[player['month']-1]} {player['week']}주차"

# --- 6. 게임 로직 함수들 ---
def update_prices(settings, items_info, market_data, initial_stocks=None):
    if initial_stocks is None:
        initial_stocks = st.session_state.get('initial_stocks', {})
    
    for v_name, v_data in market_data.items():
        for i_name, i_info in v_data.items():
            if i_name in items_info:
                base = items_info[i_name]['base']
                stock = i_info['stock']
                
                # 초기 재고량 가져오기
                initial_stock = initial_stocks.get(v_name, {}).get(i_name, 100)
                if initial_stock <= 0:
                    initial_stock = 100  # 안전장치
                
                if stock <= 0:
                    i_info['price'] = int(base * 10)  # 품절시 가격 10배
                else:
                    # 재고 비율에 따른 가격 결정
                    stock_ratio = stock / initial_stock
                    
                    # 재고 많을수록 가격 하락, 적을수록 상승
                    if stock_ratio > 2.0:  # 재고 매우 과다
                        price_factor = 0.5  # 50% 하락
                    elif stock_ratio > 1.5:  # 재고 과다
                        price_factor = 0.7  # 30% 하락
                    elif stock_ratio > 1.0:  # 재고 많음
                        price_factor = 0.9  # 10% 하락
                    elif stock_ratio > 0.7:  # 적정 재고
                        price_factor = 1.0  # 기준가
                    elif stock_ratio > 0.4:  # 재고 부족
                        price_factor = 1.3  # 30% 상승
                    elif stock_ratio > 0.2:  # 재고 매우 부족
                        price_factor = 1.6  # 60% 상승
                    else:  # 재고 거의 없음
                        price_factor = 2.0  # 100% 상승
                    
                    # 지역별 특산물 가격 보정
                    region_discounts = {
                        "부산": ["생선", "멸치", "굴비", "대구", "명태"],
                        "강원도": ["감자", "옥수수", "송이버섯"],
                        "전라도": ["쌀", "배추", "고추"],
                        "경상도": ["사과", "배", "소고기"],
                        "충청도": ["인삼", "약초"],
                        "제주도": ["감귤", "해산물", "돼지고기"],
                        "한양": []  # 수도는 모든 물가 비쌈
                    }
                    
                    # 지역별 보정
                    for region, items in region_discounts.items():
                        if v_name == region and i_name in items:
                            price_factor *= 0.8  # 산지는 20% 저렴
                            break
                    
                    # 한양은 모든 물가 20% 비쌈
                    if v_name == "한양":
                        price_factor *= 1.2
                    
                    # 용병 고용소는 가격 변동 없음
                    if v_name == "용병 고용소":
                        price_factor = 1.0
                    
                    i_info['price'] = int(base * price_factor)
                    
                    # 최소 가격 보장 (너무 싸지는 것 방지)
                    min_price = int(base * 0.3)
                    if i_info['price'] < min_price:
                        i_info['price'] = min_price

def get_weight(player, items_info, merc_data):
    cw = 0
    for item, qty in player['inv'].items():
        if item in items_info:
            cw += qty * items_info[item]['w']
    
    tw = 200  # 기본 무게 제한
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

def process_buy(player, items_info, market_data, pos, item_name, qty, progress_placeholder):
    total_bought = 0
    total_spent = 0
    trade_log = []
    batch_prices = []
    
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
        
        # 진행상황 로그 추가
        avg_price = sum(batch_prices) // len(batch_prices)
        trade_log.append(f"➤ {total_bought}/{qty} 구매 중... (체결가: {target['price']}냥 | 평균가: {avg_price}냥)")
        
        # 실시간 진행상황 표시
        with progress_placeholder.container():
            for log in trade_log[-5:]:
                st.markdown(f"<div class='trade-line'>{log}</div>", unsafe_allow_html=True)
        
        time.sleep(0.1)
    
    return total_bought, total_spent, trade_log

def process_sell(player, items_info, market_data, pos, item_name, qty, progress_placeholder):
    total_sold = 0
    total_earned = 0
    trade_log = []
    batch_prices = []
    
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
        
        # 진행상황 로그 추가
        avg_price = sum(batch_prices) // len(batch_prices)
        trade_log.append(f"➤ {total_sold}/{qty} 판매 중... (체결가: {current_price}냥 | 평균가: {avg_price}냥)")
        
        # 실시간 진행상황 표시
        with progress_placeholder.container():
            for log in trade_log[-5:]:
                st.markdown(f"<div class='trade-line'>{log}</div>", unsafe_allow_html=True)
        
        time.sleep(0.1)
    
    return total_sold, total_earned, trade_log

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
    # [화면 1] 슬롯 선택
    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        st.markdown("---")
        
        settings, items_info, merc_data, villages, initial_stocks, slots = load_game_data()
        
        if slots:
            st.subheader("📋 세이브 슬롯 선택")
            
            # 슬롯 정보 표시
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
                    st.session_state.last_time_update = time.time()
                    
                    # 시장 데이터 초기화
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
    
    # [화면 2] 게임 메인
    else:
        player = st.session_state.player
        settings = st.session_state.settings
        items_info = st.session_state.items_info
        merc_data = st.session_state.merc_data
        villages = st.session_state.villages
        market_data = st.session_state.market_data
        initial_stocks = st.session_state.initial_stocks
        
        # 시간 업데이트 (1초마다 체크)
current_time = time.time()
if current_time - st.session_state.last_update > 1:  # 1초마다 체크
    player, events = update_game_time(player, settings, market_data, initial_stocks)
    if events:
        st.session_state.events = events
    st.session_state.last_update = current_time
        
        # 시세 업데이트
        update_prices(settings, items_info, market_data, initial_stocks)
        cw, tw = get_weight(player, items_info, merc_data)
        
        # 이벤트 표시
        if st.session_state.events:
            for event_type, message in st.session_state.events:
                st.markdown(f"<div class='event-message'>{message}</div>", unsafe_allow_html=True)
            st.session_state.events = []
        
       # 상단 정보
      # 상단 정보
        st.title(f"🏯 {player['pos']}")
        
        col1, col2, col3, col4 = st.columns(4)
        money_placeholder = col1.empty()
        money_placeholder.metric("💰 소지금", f"{player['money']:,}냥")
        
        weight_placeholder = col2.empty()
        weight_placeholder.metric("⚖️ 무게", f"{cw}/{tw}근")
        
        time_placeholder = col3.empty()
        time_placeholder.metric("📅 시간", get_time_display(player))
        
        # 다음 달까지 남은 시간
        remaining = max(0, 30 - int(time.time() - st.session_state.last_time_update))
        time_left_placeholder = col4.empty()
        time_left_placeholder.metric("⏰ 다음 달까지", f"{remaining}초")
        
        # 거래 횟수는 탭 안으로 이동하거나 다른 곳에 표시
        trade_count_placeholder = st.empty()  # 별도로 표시
        
        st.divider()
        
        # 거래 횟수 표시 (상단 정보 아래에 작게)
        trade_count_placeholder.markdown(f"<div style='text-align: right; color: #666;'>📊 거래 횟수: {st.session_state.stats['trade_count']}회</div>", unsafe_allow_html=True)
        
        st.divider()
        
        # 탭 메뉴
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 거래", "📦 인벤토리", "⚔️ 용병", "📊 통계", "⚙️ 기타"])
        
        # [탭1] 거래
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
                        
                        # 가격 변동 표시
                        if d['price'] > base_price * 1.1:
                            price_class = "price-up"
                            trend = "▲▲"
                        elif d['price'] > base_price:
                            price_class = "price-up"
                            trend = "▲"
                        elif d['price'] < base_price * 0.9:
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
                            
                            col1, col2, col3 = st.columns([2,1,1])
                            price_placeholder = col1.empty()
                            price_placeholder.markdown(f"<span class='{price_class}'>{d['price']:,}냥</span>", unsafe_allow_html=True)
                            
                            # 재고용 placeholder
                            stock_placeholder = col2.empty()
                            stock_placeholder.write(f"📦 {d['stock']}개")
                            
                            max_buy = calculate_max_purchase(
                                player, items_info, market_data, 
                                player['pos'], item_name, d['price']
                            )
                            max_placeholder = col3.empty()
                            max_placeholder.write(f"⚡ {max_buy}개")
                            
                            # 거래 UI
                            col_a, col_b, col_c = st.columns([2,1,1])
                            qty = col_a.text_input("수량", value="1", key=f"qty_{item_name}", label_visibility="collapsed")
                            
                            # 진행상황 표시 영역
                            progress_placeholder = st.empty()
                            
                            # 매수 버튼
                            if col_b.button("💰 매수", key=f"buy_{item_name}", use_container_width=True):
                                try:
                                    qty_int = int(qty)
                                    if qty_int > 0:
                                        actual_qty = min(qty_int, max_buy)
                                        if actual_qty > 0:
                                            progress_placeholder.markdown("<div class='trade-progress'></div>", unsafe_allow_html=True)
                                            
                                            bought, spent, trade_log = process_buy(
                                                player, items_info, market_data,
                                                player['pos'], item_name, actual_qty, progress_placeholder
                                            )
                                            
                                            if bought > 0:
                                                st.session_state.stats['total_bought'] += bought
                                                st.session_state.stats['total_spent'] += spent
                                                st.session_state.stats['trade_count'] += 1
                                                
                                                money_placeholder.metric("💰 소지금", f"{player['money']:,}냥")
                                                cw, tw = get_weight(player, items_info, merc_data)
                                                weight_placeholder.metric("⚖️ 무게", f"{cw}/{tw}근")
                                                trade_placeholder.metric("📊 거래", f"{st.session_state.stats['trade_count']}회")
                                                
                                                price_placeholder.markdown(f"<span class='{price_class}'>{d['price']:,}냥</span>", unsafe_allow_html=True)
                                                
                                                # 재고 업데이트
                                                stock_placeholder.write(f"📦 {d['stock']}개")
                                                
                                                # 최대 구매량 재계산
                                                new_max_buy = calculate_max_purchase(
                                                    player, items_info, market_data, 
                                                    player['pos'], item_name, d['price']
                                                )
                                                max_placeholder.write(f"⚡ {new_max_buy}개")
                                                
                                                avg_price = spent // bought
                                                st.markdown(f"<div class='trade-complete'>✅ 총 {bought}개 매수 완료! (총 {spent:,}냥 | 평균가: {avg_price}냥)</div>", unsafe_allow_html=True)
                                            else:
                                                st.error("❌ 구매 실패")
                                        else:
                                            st.error("❌ 구매 가능한 수량이 없습니다")
                                    else:
                                        st.error("❌ 0보다 큰 수량을 입력하세요")
                                except ValueError:
                                    st.error("❌ 올바른 숫자를 입력하세요")
                            
                            # 매도 버튼
                            if col_c.button("📦 매도", key=f"sell_{item_name}", use_container_width=True):
                                try:
                                    qty_int = int(qty)
                                    if qty_int > 0:
                                        max_sell = player['inv'].get(item_name, 0)
                                        actual_qty = min(qty_int, max_sell)
                                        if actual_qty > 0:
                                            progress_placeholder.markdown("<div class='trade-progress'></div>", unsafe_allow_html=True)
                                            
                                            sold, earned, trade_log = process_sell(
                                                player, items_info, market_data,
                                                player['pos'], item_name, actual_qty, progress_placeholder
                                            )
                                            
                                            if sold > 0:
                                                st.session_state.stats['total_sold'] += sold
                                                st.session_state.stats['total_earned'] += earned
                                                st.session_state.stats['trade_count'] += 1
                                                
                                                money_placeholder.metric("💰 소지금", f"{player['money']:,}냥")
                                                cw, tw = get_weight(player, items_info, merc_data)
                                                weight_placeholder.metric("⚖️ 무게", f"{cw}/{tw}근")
                                                trade_placeholder.metric("📊 거래", f"{st.session_state.stats['trade_count']}회")
                                                
                                                price_placeholder.markdown(f"<span class='{price_class}'>{d['price']:,}냥</span>", unsafe_allow_html=True)
                                                
                                                # 재고 업데이트
                                                stock_placeholder.write(f"📦 {d['stock']}개")
                                                
                                                # 최대 구매량 재계산
                                                new_max_buy = calculate_max_purchase(
                                                    player, items_info, market_data, 
                                                    player['pos'], item_name, d['price']
                                                )
                                                max_placeholder.write(f"⚡ {new_max_buy}개")
                                                
                                                avg_price = earned // sold
                                                st.markdown(f"<div class='trade-complete'>✅ 총 {sold}개 매도 완료! (총 {earned:,}냥 | 평균가: {avg_price}냥)</div>", unsafe_allow_html=True)
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
        
        # [탭2] 인벤토리
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
        
        # [탭3] 용병
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
        
        # [탭4] 통계
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
        
        # [탭5] 기타
        with tab5:
            st.subheader("⚙️ 게임 메뉴")
            
            # 마을 이동
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
                            player['pos'] = dest
                            money_placeholder.metric("💰 소지금", f"{player['money']:,}냥")
                            st.success(f"✅ {dest}로 이동했습니다!")
                            st.rerun()
                        else:
                            st.error("❌ 잔액 부족")
                else:
                    st.write("이동 가능한 마을이 없습니다")
            
            st.divider()
            
            # 시간 정보
            st.write("**⏰ 시간 시스템**")
            remaining = 180 - int(time.time() - st.session_state.last_time_update)
            if remaining < 0:
                remaining = 0
            st.info(f"현실 3분 = 게임 1달\n\n다음 달까지: {remaining}초")
            
            st.divider()
            
            # 저장
            if st.button("💾 저장", use_container_width=True):
                if save_player_data(doc, player, st.session_state.stats, st.session_state.device_id):
                    st.success("✅ 저장 완료!")
            
            # 종료
            if st.button("🚪 메인으로", use_container_width=True):
                st.session_state.game_started = False
                st.cache_data.clear()
                st.rerun()

