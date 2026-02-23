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

# --- 2. [핵심] 시트의 Setting_Data를 활용한 가격 변동 수식 ---
def get_dynamic_price(item_name, stock, items_info, settings, city, initial_stocks):
    base = items_info[item_name]['base']
    # 시트의 volatility (5000) 반영
    vol = settings.get('volatility', 5000) / 1000 
    # 초기 재고 대비 비율 계산 (초기값이 없으면 100으로 가정)
    init_s = initial_stocks.get(city, {}).get(item_name, 100)
    
    if stock <= 0: return base * 5
    
    # [수식] (초기재고 / 현재재고) ^ (변동성 / 4)
    ratio = init_s / stock
    factor = math.pow(ratio, (vol / 4))
    
    # 시트의 min_price_rate(0.4), max_price_rate(3.0) 적용
    min_r = settings.get('min_price_rate', 0.4)
    max_r = settings.get('max_price_rate', 3.0)
    final_factor = max(min_r, min(max_r, factor))
    
    return int(base * final_factor)

# --- 3. 매매 실행 함수 (사용자님 원본: 100개씩 실제 루프 체결) ---
def execute_trade_loop(mode, item_name, target_amt, player, market_data, city, items_info, settings, initial_stocks):
    log_placeholder = st.empty()
    logs = []
    unit_w = items_info[item_name]['w']
    step = 100
    completed = 0
    
    while completed < target_amt:
        batch = min(step, target_amt - completed)
        
        # [실시간 체크] 매 루프마다 현재 무게와 변동된 시세를 다시 계산 (99999 입력 대응)
        # 용병 보너스 포함된 최대 무게 계산
        max_w = 200 + sum([st.session_state.mercs_info[m]['weight_bonus'] for m in player['mercs']])
        curr_w = sum([items_info[it]['w'] * qty for it, qty in player['inventory'].items() if it in items_info])
        
        # 현재 재고 기반 실시간 가격 호출
        current_p = get_dynamic_price(item_name, market_data[city][item_name]['stock'], items_info, settings, city, initial_stocks)
        
        if mode == "매수":
            if player['money'] < current_p * batch:
                logs.append(f"❌ 잔액 부족으로 중단 (체결: {completed}개)")
                break
            if curr_w + (unit_w * batch) > max_w:
                logs.append(f"❌ 무게 초과로 중단 (체결: {completed}개)")
                break
            if market_data[city][item_name]['stock'] < batch:
                logs.append(f"❌ 재고 부족으로 중단 (체결: {completed}개)")
                break
            
            # 실제 데이터 차감
            player['money'] -= current_p * batch
            player['inventory'][item_name] = player['inventory'].get(item_name, 0) + batch
            market_data[city][item_name]['stock'] -= batch
        else: # 매도
            if player['inventory'].get(item_name, 0) < batch:
                logs.append(f"❌ 물량 부족으로 중단 (체결: {completed}개)")
                break
            player['money'] += current_p * batch
            player['inventory'][item_name] -= batch
            market_data[city][item_name]['stock'] += batch

        completed += batch
        logs.append(f"📦 {item_name} {batch}개 {mode} 중... ({completed}/{target_amt})")
        
        with log_placeholder.container():
            st.markdown(f'<div style="background:#f0f2f6;padding:10px;border-radius:5px;font-family:monospace;">{"<br>".join(logs[-5:])}</div>', unsafe_allow_html=True)
        time.sleep(0.01)
    return completed

# --- 4. 메인 로직 ---
# 데이터 로드 시 items_info, settings, mercs_info, initial_stocks를 session_state에 저장한다고 가정
if not st.session_state.game_started:
    st.title("🏯 조선거상 미니")
    # (생략: 슬롯 선택 버튼 클릭 시 데이터 로드 및 game_started = True)
else:
    # 모든 변수를 session_state에서 안전하게 로드
    player = st.session_state.player
    items_info = st.session_state.items_info
    settings = st.session_state.settings
    mercs_info = st.session_state.mercs_info
    market_data = st.session_state.market_data
    initial_stocks = st.session_state.initial_stocks

    # 상단 정보 메트릭 (소지금, 무게, 시간초)
    max_w = 200 + sum([mercs_info[m]['weight_bonus'] for m in player['mercs']])
    curr_w = sum([items_info[it]['w'] * qty for it, qty in player['inventory'].items() if it in items_info])
    elapsed = int(time.time() - player['start_time'])
    sec_left = 30 - (elapsed % 30)

    st.info(f"💰 {player['money']:,}냥 | 📦 {curr_w}/{max_w}근 | ⏰ {sec_left}초")

    tab1, tab2, tab3 = st.tabs(["🛒 저잣거리", "🛡️ 용병 관리", "🚩 이동"])

    with tab1:
        city = player['pos']
        target_item = st.selectbox("품목 선택", list(items_info.keys()))
        trade_amt = st.number_input("수량 입력 (99999 등 큰 숫자 가능)", 1, 1000000, 100)
        
        c1, c2 = st.columns(2)
        if c1.button("🚀 매수 실행"):
            execute_trade_loop("매수", target_item, trade_amt, player, market_data, city, items_info, settings, initial_stocks)
            st.rerun()

    with tab2:
        st.write("### 🛡️ 상단 용병 해고")
        # 시트의 fire_refund_rate (0.5) 연동
        refund_rate = settings.get('fire_refund_rate', 0.5)
        for i, m_name in enumerate(player['mercs']):
            col_m, col_b = st.columns([3, 1])
            refund = int(mercs_info[m_name]['price'] * refund_rate)
            col_m.write(f"**{m_name}** (+{mercs_info[m_name]['weight_bonus']}근)")
            if col_b.button(f"해고 ({refund:,}냥)", key=f"fire_{i}"):
                player['money'] += refund
                player['mercs'].pop(i)
                st.rerun()
