import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- [핵심] 1. 세션 초기화 (하얀 화면 방지) ---
# 앱이 시작되자마자 이 코드가 실행되어야 AttributeError가 발생하지 않습니다.
if 'game_started' not in st.session_state:
    st.session_state.game_started = False
if 'player' not in st.session_state:
    st.session_state.player = None

# --- 2. 시세 변동 로직 (Setting_Data의 volatility 반영) ---
def get_dynamic_price(item_name, current_stock, items_info, settings, initial_stocks, city):
    base = items_info[item_name]['base']
    # 초기 재고 대비 현재 재고 비율 계산
    init_stock = initial_stocks.get(city, {}).get(item_name, 100)
    vol = settings.get('volatility', 5000) / 1000  # 5000 -> 5.0
    
    if current_stock <= 0: return base * 5
    
    # [공식] 가격 = 기본가 * (초기재고/현재재고)^(vol/4)
    ratio = init_stock / current_stock
    factor = math.pow(ratio, (vol / 4))
    
    # Setting_Data의 min/max_price_rate 적용
    factor = max(settings.get('min_price_rate', 0.4), min(settings.get('max_price_rate', 3.0), factor))
    return int(base * factor)

# --- 3. 매매 실행 함수 (100개씩 실제 체결 & 로그 출력) ---
def execute_trade_loop(mode, item_name, target_amt, player, market_data, city, items_info, settings, initial_stocks):
    log_placeholder = st.empty()
    logs = []
    unit_weight = items_info[item_name]['w']
    step = 100
    completed = 0
    
    while completed < target_amt:
        batch = min(step, target_amt - completed)
        
        # 현재 무게와 시세 실시간 재계산
        curr_w = sum([items_info[it]['w'] * qty for it, qty in player['inventory'].items() if it in items_info])
        max_w = 200 + sum([mercs_data[m]['weight_bonus'] for m in player['mercs']])
        current_price = get_dynamic_price(item_name, market_data[city][item_name]['stock'], items_info, settings, initial_stocks, city)
        
        if mode == "매수":
            if player['money'] < current_price * batch:
                logs.append(f"❌ 잔액 부족으로 중단 (체결: {completed})")
                break
            if curr_w + (unit_weight * batch) > max_w:
                logs.append(f"❌ 무게 초과로 중단 (체결: {completed})")
                break
            if market_data[city][item_name]['stock'] < batch:
                logs.append(f"❌ 재고 부족으로 중단 (체결: {completed})")
                break
            
            player['money'] -= current_price * batch
            player['inventory'][item_name] = player['inventory'].get(item_name, 0) + batch
            market_data[city][item_name]['stock'] -= batch
        else:
            if player['inventory'].get(item_name, 0) < batch:
                logs.append(f"❌ 물량 부족으로 중단 (체결: {completed})")
                break
            player['money'] += current_price * batch
            player['inventory'][item_name] -= batch
            market_data[city][item_name]['stock'] += batch

        completed += batch
        logs.append(f"📦 {item_name} {batch}개 {mode} 중... ({completed}/{target_amt})")
        
        with log_placeholder.container():
            st.markdown(f'<div class="trade-progress">{"<br>".join(logs[-5:])}</div>', unsafe_allow_html=True)
        time.sleep(0.01)
    return completed

# --- 4. 메인 UI 및 실행 로직 ---
# (데이터 로드 부분 생략 - 사용자님 기존 함수 사용)

if not st.session_state.game_started:
    # [초기 화면: 슬롯 선택]
    st.title("🏯 조선거상 미니")
    # ... 슬롯 선택 버튼 클릭 시 ...
    # st.session_state.game_started = True 설정
else:
    player = st.session_state.player
    
    # 상단 정보바 (시간초 포함)
    elapsed = int(time.time() - player['start_time'])
    sec_left = 30 - (elapsed % 30)
    
    # 실시간 무게 계산
    max_w = 200 + sum([mercs_data[m]['weight_bonus'] for m in player['mercs']])
    curr_w = sum([items_info[it]['w'] * qty for it, qty in player['inventory'].items() if it in items_info])

    st.info(f"💰 {player['money']:,}냥 | 📦 {curr_w}/{max_w}근 | ⏰ 다음 달: {sec_left}초")

    tab1, tab2, tab3 = st.tabs(["🛒 저잣거리", "🛡️ 용병 관리", "🚩 이동"])

    with tab1:
        city = player['pos']
        target_item = st.selectbox("품목", list(items_info.keys()))
        trade_amt = st.number_input("수량 입력 (99999 등)", 1, 1000000, 100)
        
        c1, c2 = st.columns(2)
        if c1.button("🚀 분할 매수"):
            done = execute_trade_loop("매수", target_item, trade_amt, player, market_data, city, items_info, settings, initial_stocks)
            st.success(f"결과: {done}개 체결 완료")
            st.rerun()

    with tab2:
        st.write("### 🛡️ 용병 관리")
        # Setting_Data의 fire_refund_rate(0.5) 연동
        for i, m_name in enumerate(player['mercs']):
            col_m, col_b = st.columns([3, 1])
            refund = int(mercs_data[m_name]['price'] * settings.get('fire_refund_rate', 0.5))
            col_m.write(f"**{m_name}** (+{mercs_data[m_name]['weight_bonus']}근)")
            if col_b.button(f"해고 ({refund:,}냥)", key=f"fire_{i}"):
                player['money'] += refund
                player['mercs'].pop(i)
                st.rerun()
