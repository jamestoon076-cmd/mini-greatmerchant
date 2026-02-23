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

# --- 1. 페이지 설정 (최상단) ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

# --- 2. [필독] 세션 초기화 (NameError/AttributeError 방지) ---
if 'game_started' not in st.session_state:
    st.session_state.game_started = False
if 'settings' not in st.session_state:
    st.session_state.settings = {}

# --- 3. 데이터 로드 (st.cache_resource 사용) ---
@st.cache_resource
def init_spreadsheet():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        client = gspread.authorize(creds)
        doc = client.open("조선거상_DB")
        
        # 📌 Setting_Data 로드 (이 변수가 settings가 됩니다)
        settings_ws = doc.worksheet("Setting_Data").get_all_records()
        settings = {r['변수명']: float(r['값']) for r in settings_ws if r.get('변수명')}
        
        # 나머지 데이터 로드
        items_ws = doc.worksheet("Item_Data").get_all_records()
        items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in items_ws}
        
        mercs_ws = doc.worksheet("Balance_Data").get_all_records()
        mercs_data = {r['name']: {'price': int(r['price']), 'weight_bonus': int(r['weight_bonus'])} for r in mercs_ws}
        
        market_data = {}
        initial_stocks = {}
        for ws in doc.worksheets():
            if "_Village_Data" in ws.title:
                rows = ws.get_all_records()
                for r in rows:
                    v_name = r.pop('village_name')
                    market_data[v_name] = {k: {'stock': int(v) if v != "" else 0} for k, v in r.items()}
                    initial_stocks[v_name] = {k: int(v) if v != "" else 100 for k, v in r.items()}
        
        player_slots = doc.worksheet("Player_Data").get_all_records()
        return doc, settings, items_info, mercs_data, market_data, player_slots, initial_stocks
    except Exception as e:
        st.error(f"시트 로드 실패: {e}")
        return None

# 데이터 호출 및 전역 변수화
db_data = init_spreadsheet()

if db_data:
    doc, settings, items_info, mercs_data, market_data, player_slots, initial_stocks = db_data
    # 📌 세션에도 저장하여 어디서든 호출 가능하게 함
    st.session_state.settings = settings
    st.session_state.items_info = items_info
    st.session_state.mercs_data = mercs_data

    # --- 4. 가격 변동 계산 (volatility 5000 반영) ---
    def get_dynamic_price(item_name, city):
        base = items_info[item_name]['base']
        stock = market_data[city][item_name]['stock']
        # 📌 시트의 volatility 반영
        vol = st.session_state.settings.get('volatility', 5000) / 1000
        init_s = initial_stocks.get(city, {}).get(item_name, 100)
        
        if stock <= 0: return base * 5
        # 수식: (초기재고/현재재고)^(vol/4)
        factor = math.pow(init_s / stock, vol / 4)
        factor = max(st.session_state.settings.get('min_price_rate', 0.4), 
                     min(st.session_state.settings.get('max_price_rate', 3.0), factor))
        return int(base * factor)

    # --- 5. 게임 메인 루프 ---
    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        # [슬롯 선택 로직 생략 - 사용자 원본과 동일]
        for i, p in enumerate(player_slots):
            if st.button(f"슬롯 {i+1} 접속", key=f"slot_{i}"):
                st.session_state.player = {
                    'money': int(p.get('money', 10000)),
                    'pos': p.get('pos', '한양'),
                    'inventory': json.loads(p['inventory']) if p.get('inventory') else {},
                    'mercs': json.loads(p['mercs']) if p.get('mercs') else [],
                    'start_time': time.time()
                }
                st.session_state.game_started = True
                st.rerun()
    else:
        player = st.session_state.player
        city = player['pos']
        
        # 상단 정보 (무게 실시간 계산)
        max_w = 200 + sum([mercs_data[m]['weight_bonus'] for m in player['mercs']])
        curr_w = sum([items_info[it]['w'] * qty for it, qty in player['inventory'].items() if it in items_info])
        
        st.info(f"💰 {player['money']:,}냥 | 📦 {curr_w}/{max_w}근")

        tab1, tab2, tab3 = st.tabs(["🛒 시장", "🛡️ 용병", "🚩 이동"])

        with tab1: # 시장 및 100개 루프 매매
            target = st.selectbox("품목", list(items_info.keys()))
            amt = st.number_input("수량(99999 등)", 1, 1000000, 100)
            
            if st.button("🚀 매수 시작"):
                log_p = st.empty()
                logs = []
                done = 0
                while done < amt:
                    batch = min(100, amt - done)
                    price = get_dynamic_price(target, city)
                    
                    # 99999 입력 시 한도 체크 후 자동 중단 (사용자 원본 로직)
                    if player['money'] < price * batch or curr_w + (items_info[target]['w'] * batch) > max_w:
                        logs.append("⚠️ 무게/자금 한도 도달 - 중단")
                        break
                    
                    player['money'] -= price * batch
                    player['inventory'][target] = player['inventory'].get(target, 0) + batch
                    market_data[city][target]['stock'] -= batch
                    curr_w += items_info[target]['w'] * batch
                    done += batch
                    
                    logs.append(f"📦 {target} {batch}개 매수 중... ({done}/{amt})")
                    log_p.markdown(f'<div style="background:#f0f2f6;padding:10px;border-radius:5px;">{"<br>".join(logs[-5:])}</div>', unsafe_allow_html=True)
                    time.sleep(0.01)
                st.rerun()

        with tab2: # 📌 문제의 그 부분: 용병 해고
            st.write("### 🛡️ 상단 용병 해고")
            # 📌 st.session_state.settings에서 안전하게 가져옴
            refund_rate = st.session_state.settings.get('fire_refund_rate', 0.5)
            for i, m_name in enumerate(player['mercs']):
                c1, c2 = st.columns([3, 1])
                refund = int(mercs_data[m_name]['price'] * refund_rate)
                c1.write(f"**{m_name}** (+{mercs_data[m_name]['weight_bonus']}근)")
                if c2.button(f"해고 ({refund:,}냥)", key=f"fire_{i}"):
                    player['money'] += refund
                    player['mercs'].pop(i)
                    st.rerun()
