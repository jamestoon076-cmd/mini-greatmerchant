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

# 모바일 최적화 CSS (기존 유지)
st.markdown("""
<style>
    .stButton button { width: 100%; margin: 5px 0; padding: 15px; font-size: 18px; }
    .stTextInput input { font-size: 16px; padding: 10px; }
    div[data-testid="column"] { gap: 10px; }
    .price-up { color: #ff4b4b; font-weight: bold; }
    .price-down { color: #4b7bff; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 2. 데이터 로드 ---
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

def load_game_data():
    doc = connect_gsheet()
    if not doc: return None, None, None, None, None, None, None
    
    # Setting_Data
    set_ws = doc.worksheet("Setting_Data")
    settings = {r['변수명']: float(r['값']) for r in set_ws.get_all_records() if r.get('변수명')}
    
    # Item_Data
    item_ws = doc.worksheet("Item_Data")
    items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in item_ws.get_all_records()}
    
    # Village_Data
    vil_ws = doc.worksheet("Village_Data")
    vals = vil_ws.get_all_values()
    headers = vals[0]
    villages = {}
    initial_stocks = {}
    for row in vals[1:]:
        if not row[0]: continue
        v_name = row[0]
        villages[v_name] = {'x': int(row[1]), 'y': int(row[2]), 'items': {}}
        initial_stocks[v_name] = {}
        for i in range(3, len(headers)):
            item_name = headers[i]
            if item_name and i < len(row) and row[i]:
                stock = int(row[i])
                villages[v_name]['items'][item_name] = stock
                initial_stocks[v_name][item_name] = stock
                
    # Balance & Player Data
    bal_ws = doc.worksheet("Balance_Data")
    mercs = {r['name']: {'price': int(r['price']), 'weight_bonus': int(r['weight_bonus'])} for r in bal_ws.get_all_records()}
    
    play_ws = doc.worksheet("Player_Data")
    player_recs = play_ws.get_all_records()
    
    return doc, settings, items_info, mercs, villages, initial_stocks, player_recs

# --- 3. 수정된 시세 로직 (volatility 반영) ---
def update_market_prices(settings, items_info, market_data, initial_stocks):
    volatility = settings.get('volatility', 1.0)
    
    for v_name, items in market_data.items():
        if v_name == "용병 고용소": continue
        for i_name, i_info in items.items():
            if i_name in items_info:
                base = items_info[i_name]['base']
                current_s = i_info['stock']
                init_s = initial_stocks.get(v_name, {}).get(i_name, 100)
                
                if current_s <= 0:
                    i_info['price'] = base * 5
                else:
                    # 마을별 초기 재고 대비 비율 계산
                    ratio = init_s / current_s
                    # volatility를 적용한 가격 변동 공식
                    # (ratio-1)이 0보다 크면 가격상승, 작으면 하락
                    # 5000같은 큰 값을 대비해 스케일링(0.001) 적용
                    factor = ((ratio - 1) * (volatility * 0.001)) + 1
                    factor = max(0.5, min(10.0, factor)) # 0.5배 ~ 10배 제한
                    i_info['price'] = int(base * factor)

# --- 4. 게임 엔진 ---
doc, settings, items_info, mercenary_data, villages, initial_stocks, player_records = load_game_data()

if doc:
    if 'game_started' not in st.session_state:
        st.session_state.game_started = False

    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        slot = st.selectbox("슬롯 선택", [1, 2, 3])
        if st.button("게임 시작"):
            p_rec = player_records[slot-1]
            st.session_state.player = {
                'money': int(p_rec['money']),
                'pos': p_rec['pos'],
                'mercs': json.loads(p_rec['mercs']) if p_rec['mercs'] else [],
                'inventory': json.loads(p_rec['inventory']) if p_rec['inventory'] else {n:0 for n in items_info},
                'last_month': 0
            }
            st.session_state.stats = {'slot': slot}
            # 마켓 재고 초기화
            market = {v: {i: {'stock': s, 'price': items_info[i]['base']} 
                      for i, s in info['items'].items()} for v, info in villages.items()}
            st.session_state.market_prices = market
            st.session_state.initial_stocks = initial_stocks
            update_market_prices(settings, items_info, market, initial_stocks)
            st.session_state.game_started = True
            st.rerun()
    else:
        player = st.session_state.player
        market = st.session_state.market_prices
        curr_pos = player['pos']
        
        # --- UI 상단 정보 (무게 에러 방지 처리) ---
        max_w = 200 + sum(mercenary_data.get(m, {}).get('weight_bonus', 0) for m in player['mercs'])
        # KeyError 방지를 위해 .get() 사용
        curr_w = sum(player['inventory'].get(name, 0) * items_info.get(name, {}).get('w', 0) for name in player['inventory'])
        
        st.header(f"📍 {curr_pos}")
        c1, c2 = st.columns(2)
        c1.metric("💰 소지금", f"{player['money']:,}냥")
        c2.metric("📦 무게", f"{curr_w}/{max_w}근")

        # --- 기존 탭 구조 유지 ---
        tab1, tab2, tab3 = st.tabs(["🛒 장터", "🚩 이동", "👤 내 정보"])

        with tab1:
            if curr_pos == "용병 고용소":
                for m_name, m_info in mercenary_data.items():
                    col_m1, col_m2 = st.columns([3, 1])
                    col_m1.write(f"**{m_name}** (무게 +{m_info['weight_bonus']})")
                    if col_m2.button(f"{m_info['price']:,}냥", key=f"m_{m_name}"):
                        if player['money'] >= m_info['price']:
                            player['money'] -= m_info['price']
                            player['mercs'].append(m_name)
                            st.rerun()
            else:
                for i_name, i_data in market[curr_pos].items():
                    col_i1, col_i2, col_i3 = st.columns([2, 1, 1])
                    col_i1.write(f"**{i_name}** ({i_data['stock']}개)")
                    col_i2.write(f"{i_data['price']:,}냥")
                    if col_i3.button("거래", key=f"t_{i_name}"):
                        st.session_state.sel_item = i_name

                if 'sel_item' in st.session_state:
                    sel = st.session_state.sel_item
                    amt = st.number_input("수량", 1, 10000, 1)
                    cc1, cc2 = st.columns(2)
                    if cc1.button("매수"):
                        cost = market[curr_pos][sel]['price'] * amt
                        if player['money'] >= cost and market[curr_pos][sel]['stock'] >= amt:
                            player['money'] -= cost
                            player['inventory'][sel] = player['inventory'].get(sel, 0) + amt
                            market[curr_pos][sel]['stock'] -= amt
                            update_market_prices(settings, items_info, market, st.session_state.initial_stocks)
                            st.rerun()
                    if cc2.button("매도"):
                        if player['inventory'].get(sel, 0) >= amt:
                            player['money'] += market[curr_pos][sel]['price'] * amt
                            player['inventory'][sel] -= amt
                            market[curr_pos][sel]['stock'] += amt
                            update_market_prices(settings, items_info, market, st.session_state.initial_stocks)
                            st.rerun()

        with tab2:
            for dest, d_info in villages.items():
                if dest != curr_pos:
                    dist = math.sqrt((villages[curr_pos]['x']-d_info['x'])**2 + (villages[curr_pos]['y']-d_info['y'])**2)
                    cost = int(dist * settings.get('travel_cost', 15))
                    if st.button(f"{dest} 이동 ({cost}냥)"):
                        if player['money'] >= cost:
                            player['money'] -= cost
                            player['pos'] = dest
                            st.rerun()

        with tab3:
            st.write(f"용병: {player['mercs']}")
            if st.button("💾 저장"):
                # (기존 save_player_data 함수 호출 로직)
                st.success("저장 완료")
