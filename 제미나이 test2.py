import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 세션 초기화 (AttributeError 방지 핵심) ---
if 'game_started' not in st.session_state:
    st.session_state.game_started = False
if 'market_data' not in st.session_state:
    st.session_state.market_data = {}
if 'initial_stocks' not in st.session_state:
    st.session_state.initial_stocks = {}

# --- 2. 시세 변동 로직 (Setting_Data의 volatility 반영) ---
def update_dynamic_prices(settings, items_info, market_data):
    vol = settings.get('volatility', 5000) / 1000  # 예: 5000 -> 5.0
    initial_stocks = st.session_state.initial_stocks

    for city, items in market_data.items():
        if city == "용병 고용소": continue
        for i_name, i_data in items.items():
            if i_name in items_info:
                base = items_info[i_name]['base']
                curr_stock = i_data['stock']
                init_stock = initial_stocks.get(city, {}).get(i_name, 100)
                
                if curr_stock <= 0:
                    i_data['price'] = base * 5
                else:
                    # [공식] (초기재고/현재재고) ^ (변동성/4)
                    ratio = init_stock / curr_stock
                    factor = math.pow(ratio, (vol / 4))
                    # Setting_Data의 min/max_price_rate 적용
                    factor = max(settings.get('min_price_rate', 0.4), min(settings.get('max_price_rate', 3.0), factor))
                    i_data['price'] = int(base * factor)

# --- 3. 매매 실행 함수 (100개씩 분할 체결 & 실시간 로그) ---
def execute_trade_loop(mode, item_name, target_amt, current_price, player, market_data, current_city, max_w, items_info):
    log_placeholder = st.empty()
    logs = []
    unit_weight = items_info[item_name]['w']
    
    completed = 0
    step = 100
    
    while completed < target_amt:
        batch = min(step, target_amt - completed)
        
        # 현재 무게 실시간 계산
        curr_w = sum([items_info[it]['w'] * qty for it, qty in player['inventory'].items() if it in items_info])
        
        if mode == "매수":
            if player['money'] < current_price * batch:
                logs.append(f"❌ 잔액 부족으로 중단 (체결: {completed})")
                break
            if curr_w + (unit_weight * batch) > max_w:
                logs.append(f"❌ 무게 초과로 중단 (체결: {completed})")
                break
            if market_data[current_city][item_name]['stock'] < batch:
                logs.append(f"❌ 재고 부족으로 중단 (체결: {completed})")
                break
                
            player['money'] -= current_price * batch
            player['inventory'][item_name] = player['inventory'].get(item_name, 0) + batch
            market_data[current_city][item_name]['stock'] -= batch
        else:
            if player['inventory'].get(item_name, 0) < batch:
                logs.append(f"❌ 보유량 부족으로 중단 (체결: {completed})")
                break
            player['money'] += current_price * batch
            player['inventory'][item_name] -= batch
            market_data[current_city][item_name]['stock'] += batch

        completed += batch
        logs.append(f"📦 {item_name} {batch}개 {mode} 중... ({completed}/{target_amt})")
        
        with log_placeholder.container():
            st.markdown(f'<div class="trade-progress">{"<br>".join(logs[-5:])}</div>', unsafe_allow_html=True)
        time.sleep(0.01)
    
    return completed

# --- 4. 메인 게임 로직 (AttributeError 해결) ---
# [데이터 로드 부분은 기존 사용자 코드와 동일하게 유지]

if st.session_state.game_started:
    player = st.session_state.player
    settings = st.session_state.settings
    items_info = st.session_state.items_info
    mercs_data = st.session_state.mercs_data
    market_data = st.session_state.market_data

    # 상단 정보바용 무게 계산
    max_w = 200 + sum([mercs_data[m]['weight_bonus'] for m in player['mercs']])
    curr_w = sum([items_info[it]['w'] * qty for it, qty in player['inventory'].items() if it in items_info])

    # 시세 실시간 업데이트
    update_dynamic_prices(settings, items_info, market_data)

    # UI 출력
    st.info(f"📍 {player['pos']} | 💰 {player['money']:,}냥 | 📦 {curr_w}/{max_w}근")
    
    tab1, tab2, tab3 = st.tabs(["🛒 저잣거리", "🛡️ 용병 관리", "🚩 이동"])

    with tab1:
        current_city = player['pos']
        st.write(f"### {current_city} 시장")
        # 품목 선택 및 수량 입력 (원본 스타일)
        target_item = st.selectbox("품목", list(items_info.keys()))
        trade_amt = st.number_input("수량 입력 (99999 등 큰 숫자 가능)", 1, 1000000, 100)
        
        c1, c2 = st.columns(2)
        if c1.button("🔥 분할 매수"):
            done = execute_trade_loop("매수", target_item, trade_amt, market_data[current_city][target_item]['price'], 
                                     player, market_data, current_city, max_w, items_info)
            st.success(f"매수 완료: {done}개")
            st.rerun()
            
        if c2.button("💰 분할 매도"):
            done = execute_trade_loop("매도", target_item, trade_amt, market_data[current_city][target_item]['price'], 
                                     player, market_data, current_city, max_w, items_info)
            st.success(f"매도 완료: {done}개")
            st.rerun()

    with tab2:
        st.write("### 🛡️ 용병 해고 및 관리")
        refund_rate = settings.get('fire_refund_rate', 0.5)
        
        for i, m_name in enumerate(player['mercs']):
            col_m, col_b = st.columns([3, 1])
            refund_price = int(mercs_data[m_name]['price'] * refund_rate)
            col_m.write(f"**{m_name}** (+{mercs_data[m_name]['weight_bonus']}근)")
            if col_b.button(f"해고 ({refund_price:,}냥 환불)", key=f"fire_{i}"):
                player['money'] += refund_price
                player['mercs'].pop(i)
                st.warning(f"🛡️ {m_name}을(를) 해고했습니다.")
                st.rerun()
