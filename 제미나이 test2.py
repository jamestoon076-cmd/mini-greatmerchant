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

# --- [기존 UI 설정 및 스타일 유지] ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

# --- [데이터 로드 및 시트 연결 로직 유지] ---
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

@st.cache_data(ttl=10)
def load_game_data():
    doc = connect_gsheet()
    if not doc: return None, None, None, None, None, None
    
    # Setting_Data 로드
    set_ws = doc.worksheet("Setting_Data")
    settings = {r['변수명']: float(r['값']) for r in set_ws.get_all_records()}
    
    # Item_Data 로드 (base_price, weight)
    item_ws = doc.worksheet("Item_Data")
    items_info = {str(r['item_name']).strip(): {'base': int(r['base_price']), 'w': int(r['weight'])} 
                  for r in item_ws.get_all_records() if r.get('item_name')}
    
    # Village_Data 로드 (마을별 초기 재고가 기준이 됨)
    vil_ws = doc.worksheet("Village_Data")
    vil_vals = vil_ws.get_all_values()
    headers = [h.strip() for h in vil_vals[0]]
    villages = {}
    initial_stocks = {}
    
    for row in vil_vals[1:]:
        if not row or not row[0].strip(): continue
        v_name = row[0].strip()
        villages[v_name] = {'items': {}, 'x': int(row[1]), 'y': int(row[2])}
        initial_stocks[v_name] = {}
        for i in range(3, len(headers)):
            if headers[i] in items_info and len(row) > i and row[i].strip():
                stock = int(row[i])
                villages[v_name]['items'][headers[i]] = stock
                initial_stocks[v_name][headers[i]] = stock
                
    # Balance, Player 데이터 로드 부분은 기존과 동일하므로 생략 (구조 유지)
    # ... (기존 load_game_data 로직 유지) ...
    return settings, items_info, {}, villages, initial_stocks, [] # (예시 반환)

# --- [핵심: 재고 기반 가격 변동 로직] ---
def update_prices(settings, items_info, market_data, initial_stocks):
    """
    재고가 초기값보다 적으면 가격 상승, 많으면 가격 하락.
    volatility(민감도) 변수를 사용하여 변동 폭을 조절함.
    """
    # Setting_Data에서 민감도 가져오기 (기본값 1.0)
    volatility = settings.get('volatility', 1.0)
    
    for v_name, items in market_data.items():
        if v_name not in initial_stocks: continue
        
        for i_name, i_info in items.items():
            if i_name in items_info:
                base_p = items_info[i_name]['base']
                current_s = i_info['stock']
                initial_s = initial_stocks[v_name].get(i_name, 100)
                
                if current_s <= 0:
                    i_info['price'] = int(base_p * 5) # 품절 시 5배
                    continue
                
                # 재고 비율 계산 (초기재고 / 현재재고)
                # 현재재고가 적을수록 ratio가 커짐 -> 가격 상승
                ratio = initial_s / current_s
                
                # 민감도(volatility) 적용: 
                # 변동폭 = (비율 - 1) * 민감도 + 1
                price_factor = ((ratio - 1) * volatility) + 1
                
                # 가격 상한선/하한선 설정 (0.5배 ~ 5배)
                price_factor = max(0.5, min(5.0, price_factor))
                
                i_info['price'] = int(base_p * price_factor)

# --- [이하 매수/매도 및 UI 로직은 기존 코드와 동일하게 유지] ---
# process_buy, process_sell 내부에 update_prices를 호출하여 
# 1개씩 거래될 때마다 실시간으로 가격이 변동되도록 함.
