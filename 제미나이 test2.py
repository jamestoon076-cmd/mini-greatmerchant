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
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

# 기존 UI 스타일 유지
st.markdown("""
<style>
    .stButton button { width: 100%; margin: 5px 0; padding: 15px; font-size: 18px; }
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
    if not doc: return None
    
    # 세팅 및 아이템 로드
    settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
    items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
    mercs = {r['name']: {'price': int(r['price']), 'weight_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
    
    # 마을 및 초기 재고(기준점) 로드
    vil_ws = doc.worksheet("Village_Data")
    vals = vil_ws.get_all_values()
    headers = vals[0]
    villages = {}
    initial_stocks = {}
    for row in vals[1:]:
        v_name = row[0]
        villages[v_name] = {'x': int(row[1]), 'y': int(row[2]), 'items': {}}
        initial_stocks[v_name] = {}
        for i in range(3, len(headers)):
            item_name = headers[i]
            if item_name and i < len(row) and row[i]:
                stock = int(row[i])
                villages[v_name]['items'][item_name] = stock
                initial_stocks[v_name][item_name] = stock
                
    player_records = doc.worksheet("Player_Data").get_all_records()
    return doc, settings, items_info, mercs, villages, initial_stocks, player_records

# --- 3. 핵심: 시세 업데이트 (volatility 기반) ---
def update_market_prices(settings, items_info, market_data, initial_stocks):
    # 민감도 (5000인 경우를 대비해 0.001 스케일링 적용)
    vol = settings.get('volatility', 5000) * 0.0001 
    
    for v_name, items in market_data.items():
        if v_name == "용병 고용소": continue
        for i_name, i_info in items.items():
            if i_name in items_info:
                base = items_info[i_name]['base']
                curr_s = i_info['stock']
                init_s = initial_stocks.get(v_name, {}).get(i_name, 100)
                
                if curr_s <= 0:
                    i_info['price'] = base * 5
                else:
                    # (초기재고 / 현재재고) 비율로 시세 결정
                    ratio = init_s / curr_s
                    # volatility를 변동폭에 곱함
                    factor = ((ratio - 1) * vol) + 1
                    i_info['price'] = int(base * max(0.5, min(10.0, factor)))

# --- 4. 메인 엔진 (기존 UI 로직 완벽 유지) ---
res = load_game_data()
if res:
    doc, settings, items_info, mercenary_data, villages, initial_stocks, player_records = res

    if 'game_started' not in st.session_state:
        st.session_state.game_started = False

    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        slot = st.selectbox("슬롯 선택", [1, 2, 3])
        if st.button("게임 시작"):
            p_rec = player_records[slot-1]
            # 안전한 인벤토리 초기화
            try:
                inv = json.loads(p_rec['inventory']) if p_rec['inventory'] else {}
            except:
                inv = {n: 0 for n in items_info}
                
            st.session_state.player = {
                'money': int(p_rec['money']),
                'pos': p_rec['pos'] if p_rec['pos'] else "한양",
                'mercs': json.loads(p_rec['mercs']) if p_rec['mercs'] else [],
                'inventory': inv,
                'start_time': time.time()
            }
            st.session_state.stats = {'slot': slot}
            # 마켓 초기화
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
        
        # UI 상단 정보 (KeyError 방지)
        max_w = 200 + sum(mercenary_data.get(m, {}).get('weight_bonus', 0) for m in player['mercs'])
        curr_w = sum(player['inventory'].get(n, 0) * items_info.get(n, {}).get('w', 0) for n in player['inventory'])
        
        st.header(f"📍 {curr_pos}")
        c1, c2 = st.columns(2)
        c1.metric("💰 소지금", f"{player['money']:,}냥")
        c2.metric("📦 무게", f"{curr_w}/{max_w}근")

        tab1, tab2, tab3 = st.tabs(["🛒 장터", "🚩 이동", "👤 내 정보"])

        with tab1:
            if curr_pos == "용병 고용소":
                for m_name, m_info in mercenary_data.items():
                    col_m1, col_m2 = st.columns([3, 1])
                    col_m1.write(f"**{m_name}** (+{m_info['weight_bonus']}근)")
                    if col_m2.button(f"{m_info['price']:,}냥", key=f"m_{m_name}"):
                        if player['money'] >= m_info['price'] and len(player['mercs']) < settings['max_mercenaries']:
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
                    if cc1.button("매수", use_container_width=True):
                        cost = market[curr_pos][sel]['price'] * amt
                        if player['money'] >= cost and market[curr_pos][sel]['stock'] >= amt and curr_w + (items_info[sel]['w']*amt) <= max_w:
                            player['money'] -= cost
                            player['inventory'][sel] = player['inventory'].get(sel, 0) + amt
                            market[curr_pos][sel]['stock'] -= amt
                            update_market_prices(settings, items_info, market, st.session_state.initial_stocks)
                            st.success("매수 완료")
                            st.rerun()
                    if cc2.button("매도", use_container_width=True):
                        if player['inventory'].get(sel, 0) >= amt:
                            player['money'] += market[curr_pos][sel]['price'] * amt
                            player['inventory'][sel] -= amt
                            market[curr_pos][sel]['stock'] += amt
                            update_market_prices(settings, items_info, market, st.session_state.initial_stocks)
                            st.success("매도 완료")
                            st.rerun()

        with tab2:
            for dest, d_info in villages.items():
                if dest != curr_pos:
                    dist = math.sqrt((villages[curr_pos]['x']-d_info['x'])**2 + (villages[curr_pos]['y']-d_info['y'])**2)
                    cost = int(dist * settings['travel_cost'])
                    if st.button(f"{dest} 이동 ({cost}냥)"):
                        if player['money'] >= cost:
                            player['money'] -= cost
                            player['pos'] = dest
                            st.rerun()

        with tab3:
            st.write(f"보유 용병: {player['mercs']}")
            st.write("인벤토리:")
            for k, v in player['inventory'].items():
                if v > 0: st.write(f"- {k}: {v}개")
            if st.button("🚪 메인으로"):
                st.session_state.game_started = False
                st.rerun()
