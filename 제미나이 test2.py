import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime
import hashlib
import uuid

# --- 1. 페이지 설정 및 디자인 (UI개선 파일에서) ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

st.markdown("""
<style>
    .slot-container { background-color: #ffffff; padding: 20px; border-radius: 15px; border: 1px solid #e1e4e8; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .stButton button { width: 100%; font-weight: bold; }
    .trade-container { background-color: #f8f9fa; padding: 15px; border-radius: 10px; margin-top: 10px; border: 1px solid #dee2e6; }
    .price-up { color: #ff4b4b; font-weight: bold; }
    .price-down { color: #4b7bff; font-weight: bold; }
    .price-same { color: #808080; }
</style>
""", unsafe_allow_html=True)

# --- 2. 구글 시트 연결 (공통) ---
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

# --- 3. 데이터 로드 (가격변동 파일에서 가져옴) ---
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
                    'inv': json.loads(r['inventory']) if r.get('inventory') else {},
                    'mercs': json.loads(r['mercs']) if r.get('mercs') else [],
                    'week': 1, 'month': 1, 'year': 1592,
                    'last_save': r.get('last_save', '')
                })
        
        return settings, items_info, merc_data, villages, initial_stocks, slots
    
    except Exception as e:
        st.error(f"❌ 데이터 로드 에러: {e}")
        return None, None, None, None, None, None

# --- 4. 가격 계산 함수 (가격변동 파일에서) ---
def calculate_price(settings, items_info, market_data, v_name, i_name, initial_stocks):
    base = items_info[i_name]['base']
    stock = market_data[v_name][i_name]['stock']
    initial_stock = initial_stocks.get(v_name, {}).get(i_name, 100)
    
    if initial_stock <= 0:
        initial_stock = 100
    
    if stock <= 0:
        return int(base * 3.0)
    
    stock_ratio = stock / initial_stock
    
    # 설정값 가져오기
    ratio_extreme_high = settings.get('ratio_extreme_high', 2.0)
    ratio_high = settings.get('ratio_high', 1.5)
    ratio_above_normal = settings.get('ratio_above_normal', 1.0)
    ratio_normal = settings.get('ratio_normal', 0.7)
    ratio_low = settings.get('ratio_low', 0.4)
    
    factor_extreme_high = settings.get('factor_extreme_high', 0.5)
    factor_high = settings.get('factor_high', 0.7)
    factor_above_normal = settings.get('factor_above_normal', 0.85)
    factor_normal = settings.get('factor_normal', 1.0)
    factor_low = settings.get('factor_low', 1.3)
    factor_extreme_low = settings.get('factor_extreme_low', 2.0)
    
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
    
    return int(base * price_factor)

# --- 5. 세션 초기화 (공통) ---
def init_session_state():
    if 'game_started' not in st.session_state:
        st.session_state.game_started = False
    if 'player' not in st.session_state:
        st.session_state.player = None
    if 'slot_num' not in st.session_state:
        st.session_state.slot_num = None

# --- 6. 메인 실행 ---
doc = connect_gsheet()
init_session_state()

if doc:
    if not st.session_state.game_started:
        st.title("🏯 거상: 대륙의 시작")
        
        settings, items_info, merc_data, villages, initial_stocks, slots = load_game_data()
        
        if slots:
            for i, s in enumerate(slots):
                slot_id = i + 1
                with st.container():
                    st.markdown(f"""<div class="slot-container"><b>💾 슬롯 {slot_id}</b><br>
                    📍 현재 위치: {s.get('pos','한양')} | 💰 소지금: {s.get('money',0):,}냥<br>
                    🕒 마지막 저장: {s.get('last_save','기록 없음')}</div>""", unsafe_allow_html=True)
                    if st.button(f"슬롯 {slot_id} 접속", key=f"slot_{slot_id}"):
                        st.session_state.player = s
                        st.session_state.slot_num = slot_id
                        st.session_state.settings = settings
                        st.session_state.items_info = items_info
                        st.session_state.merc_data = merc_data
                        st.session_state.villages = villages
                        st.session_state.initial_stocks = initial_stocks
                        
                        market_data = {}
                        for v_name, v_data in villages.items():
                            if v_name != "용병 고용소":
                                market_data[v_name] = {}
                                for item_name, stock in v_data['items'].items():
                                    market_data[v_name][item_name] = {'stock': stock}
                        st.session_state.market_data = market_data
                        
                        st.session_state.game_started = True
                        st.rerun()
    
    else:
        player = st.session_state.player
        settings = st.session_state.settings
        items_info = st.session_state.items_info
        villages = st.session_state.villages
        market_data = st.session_state.market_data
        initial_stocks = st.session_state.initial_stocks
        
        # 현재 마을의 모든 아이템 가격 업데이트
        for item_name in market_data[player['pos']]:
            price = calculate_price(settings, items_info, market_data, player['pos'], item_name, initial_stocks)
            market_data[player['pos']][item_name]['price'] = price
        
        st.header(f"📍 현재 위치: {player['pos']}")
        st.subheader(f"💰 소지금: {player['money']:,}냥")
        
        tab1, tab2, tab3 = st.tabs(["🛒 저잣거리", "🚩 이동", "👤 정보"])
        
        with tab1:  # 장터
            if player['pos'] in market_data:
                for item_name, item_data in market_data[player['pos']].items():
                    with st.container():
                        st.markdown(f"<div class='trade-container'>", unsafe_allow_html=True)
                        c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                        c1.write(f"**{item_name}**")
                        c2.write(f"📦 {item_data['stock']}개")
                        
                        # 가격 변동에 따른 색상
                        base = items_info[item_name]['base']
                        if item_data['price'] > base * 1.2:
                            price_disp = f"<span class='price-up'>{item_data['price']:,}냥 ▲</span>"
                        elif item_data['price'] < base * 0.8:
                            price_disp = f"<span class='price-down'>{item_data['price']:,}냥 ▼</span>"
                        else:
                            price_disp = f"<span class='price-same'>{item_data['price']:,}냥</span>"
                        
                        c3.markdown(price_disp, unsafe_allow_html=True)
                        
                        if c4.button("거래", key=f"trade_{item_name}"):
                            st.session_state.active_trade = {
                                'name': item_name, 
                                'price': item_data['price'],
                                'stock': item_data['stock']
                            }
                        st.markdown("</div>", unsafe_allow_html=True)
                
                if 'active_trade' in st.session_state:
                    with st.container(border=True):
                        at = st.session_state.active_trade
                        st.write(f"### {at['name']} 거래")
                        amt = st.number_input("수량", 1, min(at['stock'], 10000), 1)
                        b_col, s_col = st.columns(2)
                        if b_col.button("💰 매수"):
                            cost = at['price'] * amt
                            if player['money'] >= cost:
                                player['money'] -= cost
                                player['inv'][at['name']] = player['inv'].get(at['name'], 0) + amt
                                market_data[player['pos']][at['name']]['stock'] -= amt
                                del st.session_state.active_trade
                                st.rerun()
                        if s_col.button("📦 매도"):
                            if player['inv'].get(at['name'], 0) >= amt:
                                player['money'] += at['price'] * amt
                                player['inv'][at['name']] -= amt
                                market_data[player['pos']][at['name']]['stock'] += amt
                                del st.session_state.active_trade
                                st.rerun()
        
        with tab2:  # 이동
            # 국가 구분 없이 모든 마을 표시
            cols = st.columns(3)
            for idx, (v_name, v_data) in enumerate(villages.items()):
                if v_name == player['pos'] or v_name == "용병 고용소":
                    continue
                with cols[idx % 3]:
                    with st.container(border=True):
                        st.write(f"**{v_name}**")
                        dist = math.sqrt((villages[player['pos']]['x'] - v_data['x'])**2 + 
                                       (villages[player['pos']]['y'] - v_data['y'])**2)
                        cost = int(dist * settings.get('travel_cost', 15))
                        st.caption(f"이동비: {cost:,}냥")
                        if st.button("이동", key=f"move_{v_name}"):
                            if player['money'] >= cost:
                                player['money'] -= cost
                                player['pos'] = v_name
                                st.rerun()
        
        with tab3:  # 정보
            st.write("### 📦 인벤토리")
            if player['inv']:
                for item, qty in player['inv'].items():
                    if qty > 0:
                        st.write(f"• {item}: {qty}개")
            else:
                st.write("비어있음")
            
            st.divider()
            
            if st.button("💾 저장"):
                try:
                    ws = doc.worksheet("Player_Data")
                    save_data = [
                        st.session_state.slot_num,
                        player['money'],
                        player['pos'],
                        json.dumps(player.get('mercs', []), ensure_ascii=False),
                        json.dumps(player['inv'], ensure_ascii=False),
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ]
                    ws.update(f"A{st.session_state.slot_num + 1}:F{st.session_state.slot_num + 1}", [save_data])
                    st.success("✅ 저장 완료!")
                except Exception as e:
                    st.error(f"❌ 저장 실패: {e}")
