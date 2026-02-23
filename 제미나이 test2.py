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

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

# 모바일 최적화 CSS 유지
st.markdown("""
<style>
    .stButton button { width: 100%; margin: 5px 0; padding: 15px; font-size: 18px; }
    .price-up { color: #ff4b4b; font-weight: bold; }
    .price-down { color: #4b7bff; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 2. 구글 시트 연결 및 데이터 로드 ---
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
    
    # 1. 설정 데이터 (volatility 포함)
    set_ws = doc.worksheet("Setting_Data")
    settings = {r['변수명']: float(r['값']) for r in set_ws.get_all_records() if r.get('변수명')}
    
    # 2. 아이템 데이터
    item_ws = doc.worksheet("Item_Data")
    items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in item_ws.get_all_records()}
    
    # 3. 마을 및 초기 재고 데이터
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
                
    return doc, settings, items_info, villages, initial_stocks

# --- 3. 핵심: 시세 변동 로직 ---
def calculate_dynamic_price(base_price, current_stock, initial_stock, volatility):
    """
    재고 비율에 따른 가격 계산
    volatility가 높을수록 가격 변동이 극심해짐
    """
    if current_stock <= 0: return base_price * 5 # 품절 시 5배
    
    # 비율 계산 (기준재고 / 현재재고)
    # 예: 평양 기준 200/100 = 2.0 (재고 부족)
    # 예: 부산 기준 5000/2500 = 2.0 (재고 부족)
    ratio = initial_stock / current_stock
    
    # 민감도(volatility) 적용 공식
    # volatility가 1이면 비율만큼 정비례, 2면 변동폭 2배
    adj_factor = ((ratio - 1) * volatility) + 1
    
    # 최소 0.3배 ~ 최대 10배 제한
    adj_factor = max(0.3, min(10.0, adj_factor))
    
    return int(base_price * adj_factor)

# --- 4. 세션 초기화 및 게임 엔진 ---
if 'game_data' not in st.session_state:
    data = load_game_data()
    if data:
        doc, settings, items_info, villages, initial_stocks = data
        st.session_state.game_data = {
            'doc': doc,
            'settings': settings,
            'items_info': items_info,
            'villages': villages, # 현재 재고가 담긴 데이터
            'initial_stocks': initial_stocks # 기준이 되는 초기 재고
        }
        # 마켓 데이터 초기화 (가격 계산 포함)
        market_prices = {}
        for v_name, v_info in villages.items():
            market_prices[v_name] = {}
            for i_name, stock in v_info['items'].items():
                base = items_info[i_name]['base']
                init_s = initial_stocks[v_name][i_name]
                vol = settings.get('volatility', 1.0)
                price = calculate_dynamic_price(base, stock, init_s, vol)
                market_prices[v_name][i_name] = {'price': price, 'stock': stock}
        st.session_state.market_prices = market_prices

# --- 5. UI 출력 로직 (생략된 기존 UI 부분 유지) ---
# ... (이후에는 기존 코드의 메인 화면, 매수/매도 버튼 로직을 그대로 붙여넣으시면 됩니다)
st.title("🏯 조선거상 미니 (시세 변동형)")

if 'game_data' in st.session_state:
    v_data = st.session_state.game_data['villages']
    market = st.session_state.market_prices
    
    # 마을 선택 (예시)
    current_village = st.selectbox("마을 선택", list(v_data.keys()))
    
    st.subheader(f"📍 {current_village} 장터")
    
    for item_name, info in market[current_village].items():
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.write(f"**{item_name}**")
        with col2:
            st.write(f"{info['price']:,}냥")
        with col3:
            st.write(f"재고: {info['stock']}")

    st.info(f"💡 현재 민감도(Volatility): {st.session_state.game_data['settings'].get('volatility', 1.0)}")
