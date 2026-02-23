import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 세션 초기화 (AttributeError 방지 최우선) ---
if 'game_started' not in st.session_state:
    st.session_state.game_started = False

# --- 2. [핵심] 시트의 Setting_Data를 활용한 가격 변동 수식 ---
def get_dynamic_price(item_name, city, items_info, market_data, settings, initial_stocks):
    """Setting_Data의 volatility(5000)를 수식에 직접 반영"""
    base = items_info[item_name]['base']
    stock = market_data[city][item_name]['stock']
    
    # 📌 시트의 volatility (5000) 반영
    vol = settings.get('volatility', 5000) / 1000  # 5000 -> 5.0
    init_s = initial_stocks.get(city, {}).get(item_name, 100)
    
    if stock <= 0: return base * 5
    
    # [수식] (초기재고 / 현재재고) ^ (변동성 / 4)
    # 재고가 줄어들수록 가격이 지수함수적으로 상승
    ratio = init_s / stock
    factor = math.pow(ratio, (vol / 4))
    
    # Setting_Data의 min/max_price_rate 적용 (기본값 0.4~3.0)
    min_r = settings.get('min_price_rate', 0.4)
    max_r = settings.get('max_price_rate', 3.0)
    final_factor = max(min_r, min(max_r, factor))
    
    return int(base * final_factor)

# --- 3. 매매 실행 함수 (100개씩 루프 돌며 실시간 시세/무게 체크) ---
def execute_trade_loop(mode, item_name, target_amt, player, market_data, city, items_info, settings, initial_stocks):
    log_placeholder = st.empty()
    logs = []
    unit_w = items_info[item_name]['w']
    step = 100
    completed = 0
    
    while completed < target_amt:
        batch = min(step, target_amt - completed)
        
        # 📌 매 루프마다 용병 보너스 포함된 실시간 최대 무게 계산
        max_w = 200 + sum([st.session_state.merc_data[m]['w_bonus'] for m in player['mercs']])
        curr_w = sum([items_info[it]['w'] * qty for it, qty in player['inv'].items() if it in items_info])
        
        # 📌 매 루프마다 변동된 재고에 따른 실시간 시세 재계산
        current_p = get_dynamic_price(item_name, city, items_info, market_data, settings, initial_stocks)
        
        if mode == "매수":
            if player['money'] < current_p * batch:
                logs.append(f"❌ 자금 부족으로 중단 (체결: {completed})")
                break
            if curr_w + (unit_w * batch) > max_w:
                logs.append(f"❌ 무게 초과로 중단 (체결: {completed})")
                break
            if market_data[city][item_name]['stock'] < batch:
                logs.append(f"❌ 마을 재고 부족으로 중단 (체결: {completed})")
                break
            
            player['money'] -= current_p * batch
            player['inv'][item_name] = player['inv'].get(item_name, 0) + batch
            market_data[city][item_name]['stock'] -= batch
        else: # 매도
            if player['inv'].get(item_name, 0) < batch:
                logs.append(f"❌ 보유 물량 부족으로 중단 (체결: {completed})")
                break
            player['money'] += current_p * batch
            player['inv'][item_name] -= batch
            market_data[city][item_name]['stock'] += batch

        completed += batch
        logs.append(f"📦 {item_name} {batch}개 {mode} 중... ({completed}/{target_amt})")
        
        with log_placeholder.container():
            st.markdown(f'<div class="trade-progress">{"<br>".join(logs[-5:])}</div>', unsafe_allow_html=True)
        time.sleep(0.01)
    return completed

# --- 4. 메인 인게임 화면 ---
if st.session_state.game_started:
    p = st.session_state.player
    s = st.session_state.settings
    i_info = st.session_state.items_info
    m_info = st.session_state.merc_data
    m_data = st.session_state.market_data
    init_s = st.session_state.initial_stocks

    # 📌 상단 바: seconds_per_month (180초) 반영
    sec_per_month = int(s.get('seconds_per_month', 180))
    elapsed = time.time() - st.session_state.last_time_update
    remaining = max(0, sec_per_month - int(elapsed))
    
    # 실시간 무게 및 소지금 표시
    curr_w, max_w = get_weight(p, i_info, m_info)
    
    st.title(f"🏯 {p['pos']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 소지금", f"{p['money']:,}냥")
    c2.metric("⚖️ 무게", f"{curr_w}/{max_w}근")
    c3.metric("📅 시간", get_time_display(p))
    c4.metric("⏰ 다음 달까지", f"{remaining}초")

    tab1, tab2, tab3 = st.tabs(["🛒 거래", "🛡️ 용병 관리", "🚩 이동"])

    with tab1:
        target_item = st.selectbox("품목 선택", list(i_info.keys()))
        trade_qty = st.number_input("거래 수량 (99999 등 큰 숫자 가능)", 1, 1000000, 100)
        
        col_b, col_s = st.columns(2)
        if col_b.button("🚀 매수 실행", use_container_width=True):
            execute_trade_loop("매수", target_item, trade_qty, p, m_data, p['pos'], i_info, s, init_s)
            st.rerun()
        if col_s.button("💰 매도 실행", use_container_width=True):
            execute_trade_loop("매도", target_item, trade_qty, p, m_data, p['pos'], i_info, s, init_s)
            st.rerun()

    with tab2:
        st.subheader("🛡️ 용병 해고 시스템")
        # 📌 시트의 fire_refund_rate (0.5) 연동
        refund_rate = s.get('fire_refund_rate', 0.5)
        for i, m_name in enumerate(p['mercs']):
            c_info, c_btn = st.columns([3, 1])
            refund = int(m_info[m_name]['price'] * refund_rate)
            c_info.write(f"**{m_name}** (+{m_info[m_name]['w_bonus']}근)")
            if c_btn.button(f"해고 ({refund:,}냥)", key=f"fire_{i}"):
                p['money'] += refund
                p['mercs'].pop(i)
                st.rerun()
