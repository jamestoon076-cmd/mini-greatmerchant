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
def update_prices(settings,
