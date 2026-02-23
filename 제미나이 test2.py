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
</style>
""", unsafe_allow_html=True)

# --- 2. 구글 시트 데이터 로드 함수 ---
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
    if not doc: return None, None, None, None, None, None
    
    # Setting_Data
    set_ws = doc.worksheet("Setting_Data")
    settings = {r['변수명']: float(r['값']) for r in set_ws.get_all_records() if r.get('변수명')}
    
    # Item_Data
    item_ws = doc.worksheet("Item_Data")
    items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in item_ws.get_all_records()}
    
    # Balance_Data (용병)
    bal_ws = doc.worksheet("Balance_Data")
    mercenary_data = {r['name']: {'price': int(r['price']), 'weight_bonus': int(r['weight_bonus'])} for r in bal_ws.get_all_records()}
    
    # Village_Data (초기 재고 로드)
    vil_ws = doc.worksheet("Village_Data")
    vals = vil_ws.get_all_values()
    headers = vals[0]
    villages = {}
    initial_stocks = {} # 시세 기준점 저장용
    
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
                
    # Player_Data
    play_ws = doc.worksheet("Player_Data")
    player_records = play_ws.get_all_records()
    
    return doc, settings, items_info, mercenary_data, villages, initial_stocks, player_records

# --- 3. 핵심: 시세 업데이트 로직 (수정됨) ---
def update_prices(settings, items_info, market_data, initial_stocks):
    """
    마을별 초기 재고 대비 현재 재고 비율과 volatility를 사용하여 가격 결정
    """
    volatility = settings.get('volatility', 1.0)
    
    for v_name, items in market_data.items():
        if v_name == "용병 고용소": continue
        if v_name not in initial_stocks: continue
        
        for i_name, i_info in items.items():
            if i_name in items_info:
                base_price = items_info[i_name]['base']
                current_stock = i_info['stock']
                # Village_Data에 있던 원래 재고가 기준
                init_stock = initial_stocks[v_name].get(i_name, 100) 
                
                if current_stock <= 0:
                    i_info['price'] = int(base_price * 5)
                else:
                    # 재고 비율 (많으면 1보다 작아짐, 적으면 1보다 커짐)
                    ratio = init_stock / current_stock
                    
                    # 민감도 적용: 가격배율 = ((비율-1) * 민감도) + 1
                    # 5000같은 너무 큰 값 방지를 위해 공식 최적화
                    factor = ((ratio - 1) * (volatility / 10)) + 1 
                    
                    # 최소 0.5배 ~ 최대 10배 제한
                    factor = max(0.5, min(10.0, factor))
                    i_info['price'] = int(base_price * factor)

# --- 4. 데이터 저장/로드 함수들 (기존 유지) ---
def get_device_id():
    if 'device_id' not in st.session_state:
        st.session_state.device_id = str(uuid.uuid4())[:8]
    return st.session_state.device_id

def save_player_data(doc, player, stats, device_id):
    try:
        ws = doc.worksheet("Player_Data")
        data = [
            stats['slot'],
            player['money'],
            player['pos'],
            json.dumps(player['mercs'], ensure_ascii=False),
            json.dumps(player['inventory'], ensure_ascii=False),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ]
        ws.update(f"A{stats['slot']+1}:F{stats['slot']+1}", [data])
        return True
    except: return False

# --- 5. 게임 메인 로직 ---
data = load_game_data()
if data[0]:
    doc, settings, items_info, mercenary_data, villages, initial_stocks, player_records = data
    
    if 'game_started' not in st.session_state:
        st.session_state.game_started = False

    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        st.write(f"기기 ID: `{get_device_id()}`")
        
        slot = st.selectbox("저장 슬롯 선택", [1, 2, 3])
        if st.button("게임 시작", use_container_width=True):
            p_rec = player_records[slot-1] if slot <= len(player_records) else None
            
            # 플레이어 초기화
            st.session_state.player = {
                'money': int(p_rec['money']) if p_rec and p_rec['money'] else 10000,
                'pos': p_rec['pos'] if p_rec and p_rec['pos'] else "한양",
                'mercs': json.loads(p_rec['mercs']) if p_rec and p_rec['mercs'] else [],
                'inventory': json.loads(p_rec['inventory']) if p_rec and p_rec['inventory'] else {name: 0 for name in items_info}
            }
            st.session_state.stats = {'slot': slot}
            
            # 마켓 초기화 (전체 재고 복사)
            market = {}
            for v_name, v_info in villages.items():
                market[v_name] = {}
                for i_name, stock in v_info['items'].items():
                    market[v_name][i_name] = {'stock': stock, 'price': items_info[i_name]['base']}
            
            st.session_state.market_prices = market
            st.session_state.initial_stocks = initial_stocks
            st.session_state.game_started = True
            
            # 초기 가격 계산
            update_prices(settings, items_info, st.session_state.market_prices, st.session_state.initial_stocks)
            st.rerun()

    else:
        # --- 실제 게임 화면 ---
        player = st.session_state.player
        market = st.session_state.market_prices
        curr_pos = player['pos']
        
        st.header(f"📍 현재 위치: {curr_pos}")
        
        # 소지금 & 무게 표시
        max_w = 200 + sum(mercenary_data[m]['weight_bonus'] for m in player['mercs'])
        curr_w = sum(player['inventory'][name] * items_info[name]['w'] for name in player['inventory'])
        
        col1, col2 = st.columns(2)
        col1.metric("💰 소지금", f"{player['money']:,}냥")
        col2.metric("📦 무게", f"{curr_w}/{max_w}근")

        # 탭 구성 (장터, 이동, 내 정보)
        tab1, tab2, tab3 = st.tabs(["🛒 장터", "🚩 이동", "👤 내 정보"])

        with tab1:
            if curr_pos == "용병 고용소":
                st.subheader("👥 용병 고용")
                for m_name, m_info in mercenary_data.items():
                    c1, c2 = st.columns([2, 1])
                    c1.write(f"**{m_name}** (무게 +{m_info['weight_bonus']})")
                    if c2.button(f"{m_info['price']:,}냥", key=f"buy_{m_name}"):
                        if player['money'] >= m_info['price'] and len(player['mercs']) < settings.get('max_mercenaries', 5):
                            player['money'] -= m_info['price']
                            player['mercs'].append(m_name)
                            st.success(f"{m_name} 고용 완료!")
                            st.rerun()
            else:
                st.subheader(f"🏟️ {curr_pos} 시장")
                for i_name, i_data in market[curr_pos].items():
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"**{i_name}**\n({i_data['stock']}개)")
                    c2.write(f"{i_data['price']:,}냥")
                    
                    if c3.button("거래", key=f"trade_{i_name}"):
                        st.session_state.selected_item = i_name
                
                if 'selected_item' in st.session_state:
                    sel = st.session_state.selected_item
                    st.divider()
                    st.write(f"**선택됨: {sel}**")
                    amt = st.number_input("수량", min_value=1, max_value=max(1, market[curr_pos][sel]['stock']), step=1)
                    
                    cc1, cc2 = st.columns(2)
                    if cc1.button("매수", use_container_width=True):
                        total_p = market[curr_pos][sel]['price'] * amt
                        total_w = items_info[sel]['w'] * amt
                        if player['money'] >= total_p and curr_w + total_w <= max_w and market[curr_pos][sel]['stock'] >= amt:
                            player['money'] -= total_p
                            player['inventory'][sel] += amt
                            market[curr_pos][sel]['stock'] -= amt
                            update_prices(settings, items_info, market, st.session_state.initial_stocks)
                            st.success("매수 완료!")
                            st.rerun()
                        else: st.error("조건 부족(잔액, 무게, 혹은 재고)")
                        
                    if cc2.button("매도", use_container_width=True):
                        if player['inventory'][sel] >= amt:
                            total_p = market[curr_pos][sel]['price'] * amt
                            player['money'] += total_p
                            player['inventory'][sel] -= amt
                            market[curr_pos][sel]['stock'] += amt
                            update_prices(settings, items_info, market, st.session_state.initial_stocks)
                            st.success("매도 완료!")
                            st.rerun()
                        else: st.error("
