import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 세션 초기화 (최상단 배치로 하얀 화면/먹통 방지) ---
if 'game_started' not in st.session_state:
    st.session_state.game_started = False
if 'player' not in st.session_state:
    st.session_state.player = None
if 'market_data' not in st.session_state:
    st.session_state.market_data = {}

# --- 2. 시세 변동 핵심 수식 (Setting_Data의 volatility 반영) ---
def calculate_dynamic_price(item_name, current_stock, items_info, settings, city):
    base = items_info[item_name]['base']
    vol = settings.get('volatility', 5000) / 1000
    # 초기 재고 대비 비율 (초기값이 없으면 100으로 가정)
    init_stock = 100 
    
    if current_stock <= 0: return base * 5
    
    # [수식] 가격 = 기본가 * (초기재고/현재재고)^(vol/4)
    ratio = init_stock / current_stock
    factor = math.pow(ratio, (vol / 4))
    
    # 시트의 min/max_price_rate 적용
    factor = max(settings.get('min_price_rate', 0.4), min(settings.get('max_price_rate', 3.0), factor))
    return int(base * factor)

# --- 3. 매매 실행 함수 (100개씩 분할 체결 & 실시간 로그) ---
def execute_trade_loop(mode, item_name, target_amt, player, market_data, city, items_info, settings):
    log_placeholder = st.empty()
    logs = []
    unit_weight = items_info[item_name]['w']
    step = 100
    completed = 0
    
    while completed < target_amt:
        batch = min(step, target_amt - completed)
        
        # 매 순찰마다 실시간 무게와 시세 재계산
        curr_w = sum([items_info[it]['w'] * qty for it, qty in player['inventory'].items() if it in items_info])
        max_w = 200 + sum([mercs_data[m]['weight_bonus'] for m in player['mercs']])
        current_price = calculate_dynamic_price(item_name, market_data[city][item_name]['stock'], items_info, settings, city)
        
        if mode == "매수":
            if player['money'] < current_price * batch:
                logs.append(f"❌ 잔액 부족 중단 (체결: {completed})")
                break
            if curr_w + (unit_weight * batch) > max_w:
                logs.append(f"❌ 무게 초과 중단 (체결: {completed})")
                break
            if market_data[city][item_name]['stock'] < batch:
                logs.append(f"❌ 재고 부족 중단 (체결: {completed})")
                break
            
            player['money'] -= current_price * batch
            player['inventory'][item_name] = player['inventory'].get(item_name, 0) + batch
            market_data[city][item_name]['stock'] -= batch
        else:
            if player['inventory'].get(item_name, 0) < batch:
                logs.append(f"❌ 물량 부족 중단 (체결: {completed})")
                break
            player['money'] += current_price * batch
            player['inventory'][item_name] -= batch
            market_data[city][item_name]['stock'] += batch

        completed += batch
        logs.append(f"📦 {item_name} {batch}개 {mode} 중... ({completed}/{target_amt})")
        
        with log_placeholder.container():
            st.markdown(f'<div style="background:#f0f2f6;padding:10px;border-radius:5px;font-family:monospace;">{"<br>".join(logs[-5:])}</div>', unsafe_allow_html=True)
        time.sleep(0.01)
    return completed

# --- 4. 데이터 로드 (생략 - 사용자님 기존 함수 그대로 사용) ---
# items_info, mercs_data, settings, market_data 등을 로드하는 부분

# --- 5. 게임 메인 UI 로직 ---
if not st.session_state.game_started:
    st.title("🏯 조선거상 미니")
    st.subheader("저장된 슬롯을 선택해 주세요")
    
    # 사용자님 원본의 Player_Data 로드 로직
    for i in range(1, 4): # 1~3번 슬롯 예시
        with st.container(border=True):
            st.write(f"💾 **슬롯 {i}**")
            if st.button(f"슬롯 {i} 시작", key=f"start_{i}"):
                # 데이터 초기화 로직 (여기서 player 데이터를 세션에 담음)
                st.session_state.player = {"money": 10000, "pos": "한양", "inventory": {}, "mercs": [], "start_time": time.time()}
                st.session_state.game_started = True
                st.rerun()

else:
    player = st.session_state.player
    # 실시간 상단 정보 계산
    max_w = 200 + sum([mercs_data[m]['weight_bonus'] for m in player['mercs']])
    curr_w = sum([items_info[it]['w'] * qty for it, qty in player['inventory'].items() if it in items_info])
    
    # 상단 메트릭
    st.info(f"💰 {player['money']:,}냥 | 📦 {curr_w}/{max_w}근 | 📍 {player['pos']}")

    tab1, tab2, tab3 = st.tabs(["🛒 저잣거리", "🛡️ 용병 관리", "🚩 이동"])

    with tab1:
        city = player['pos']
        st.write(f"### {city} 물가 정보")
        # 시세 표시
        target_item = st.selectbox("품목 선택", list(items_info.keys()))
        trade_amt = st.number_input("수량 입력 (최대치 가능)", 1, 1000000, 100)
        
        c1, c2 = st.columns(2)
        if c1.button("🚀 분할 매수"):
            done = execute_trade_loop("매수", target_item, trade_amt, player, market_data, city, items_info, settings)
            st.success(f"완료: {done}개 체결")
            st.rerun()
            
        if c2.button("💰 분할 매도"):
            done = execute_trade_loop("매도", target_item, trade_amt, player, market_data, city, items_info, settings)
            st.success(f"완료: {done}개 체결")
            st.rerun()

    with tab2:
        st.write("### 🛡️ 상단 용병 해고")
        refund_rate = settings.get('fire_refund_rate', 0.5)
        for i, m_name in enumerate(player['mercs']):
            col_m, col_b = st.columns([3, 1])
            refund = int(mercs_data[m_name]['price'] * refund_rate)
            col_m.write(f"**{m_name}** (+{mercs_data[m_name]['weight_bonus']}근)")
            if col_b.button(f"해고 ({refund:,}냥)", key=f"fire_{i}"):
                player['money'] += refund
                player['mercs'].pop(i)
                st.rerun()
