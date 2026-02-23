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

# --- 1. 페이지 설정 (최상단 고정) ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

# --- 2. [중요] 세션 초기화 (AttributeError 방지) ---
# 이 부분이 코드 실행 직후 가장 먼저 돌아가야 흰 화면이 안 뜹니다.
if 'game_started' not in st.session_state:
    st.session_state.game_started = False
if 'player' not in st.session_state:
    st.session_state.player = None

# --- 3. 데이터 로드 로직 (사용자 원본 함수 활용) ---
@st.cache_resource
def load_all_initial_data():
    try:
        # 여기에 사용자님의 gspread 인증 및 데이터 로드 코드가 들어갑니다.
        # 인증 후 settings, items_info, mercs_info, regions 등을 dict로 반환
        pass 
    except: return None

# --- 4. 매매 실행 함수 (사용자님 원본의 100개 루프 체결 방식) ---
def execute_trade_loop(mode, item_name, target_amt, player, market_data, city, items_info, settings):
    log_placeholder = st.empty()
    logs = []
    unit_weight = items_info[item_name]['w']
    step = 100
    completed = 0
    
    while completed < target_amt:
        batch = min(step, target_amt - completed)
        
        # 현재 무게 및 시세 실시간 계산 (99999 입력 시 한도 자동 중단용)
        curr_w = sum([items_info[it]['w'] * qty for it, qty in player['inventory'].items() if it in items_info])
        max_w = 200 + sum([st.session_state.mercs_info[m]['weight_bonus'] for m in player['mercs']])
        
        # 재고 기반 가격 계산 (volatility 반영)
        vol = settings.get('volatility', 5000) / 1000
        base = items_info[item_name]['base']
        stock = market_data[city][item_name]['stock']
        price = int(base * math.pow(100/max(1, stock), vol/4)) if stock > 0 else base * 5

        if mode == "매수":
            if player['money'] < price * batch:
                logs.append(f"❌ 자금 부족 중단 (체결: {completed})")
                break
            if curr_w + (unit_weight * batch) > max_w:
                logs.append(f"❌ 무게 초과 중단 (체결: {completed})")
                break
            player['money'] -= price * batch
            player['inventory'][item_name] = player['inventory'].get(item_name, 0) + batch
            market_data[city][item_name]['stock'] -= batch
        else:
            if player['inventory'].get(item_name, 0) < batch:
                logs.append(f"❌ 물량 부족 중단 (체결: {completed})")
                break
            player['money'] += price * batch
            player['inventory'][item_name] -= batch
            market_data[city][item_name]['stock'] += batch

        completed += batch
        logs.append(f"📦 {item_name} {batch}개 {mode} 중... ({completed}/{target_amt})")
        with log_placeholder.container():
            st.markdown(f'<div style="background:#f0f2f6;padding:10px;border-radius:5px;">{"<br>".join(logs[-5:])}</div>', unsafe_allow_html=True)
        time.sleep(0.01)
    return completed

# --- 5. 메인 게임 루프 ---
# 데이터가 로드되었다고 가정하고 session_state에서 안전하게 꺼내 쓰기
if not st.session_state.game_started:
    st.title("🏯 조선거상 미니")
    # (여기서 슬롯을 클릭하면 세션에 데이터를 담고 game_started를 True로 바꿈)
    if st.button("슬롯 1 접속 (예시)"):
        # 임시 데이터 할당 (실제론 gspread 데이터 사용)
        st.session_state.settings = {"volatility": 5000, "fire_refund_rate": 0.5}
        st.session_state.items_info = {"비단": {"base": 1000, "w": 5}}
        st.session_state.mercs_info = {"짐꾼": {"price": 5000, "weight_bonus": 200}}
        st.session_state.player = {"money": 100000, "pos": "한양", "inventory": {}, "mercs": ["짐꾼"], "start_time": time.time()}
        st.session_state.game_started = True
        st.rerun()

else:
    # 에러 방지를 위해 변수들을 미리 할당
    p = st.session_state.player
    s = st.session_state.settings
    i_info = st.session_state.items_info
    m_info = st.session_state.mercs_info

    # 상단 정보 메트릭
    max_w = 200 + sum([m_info[m]['weight_bonus'] for m in p['mercs']])
    curr_w = sum([i_info[it]['w'] * qty for it, qty in p['inventory'].items() if it in i_info])
    
    st.info(f"💰 {p['money']:,}냥 | 📦 {curr_w}/{max_w}근 | ⏰ {30 - int(time.time() - p['start_time']) % 30}초 후 다음 달")

    tab1, tab2, tab3 = st.tabs(["🛒 저잣거리", "🛡️ 용병 관리", "🚩 이동"])

    with tab1:
        # 사용자 원본 방식의 매매 입력
        target_item = st.selectbox("품목", list(i_info.keys()))
        amt = st.number_input("수량 (큰 숫자 입력 가능)", 1, 1000000, 100)
        c1, c2 = st.columns(2)
        if c1.button("🚀 매수 실행"):
            execute_trade_loop("매수", target_item, amt, p, st.session_state.market_data, p['pos'], i_info, s)
            st.rerun()

    with tab2:
        st.write("### 🛡️ 상단 용병 해고")
        # fire_refund_rate(0.5)를 적용한 해고 기능
        refund_rate = s.get('fire_refund_rate', 0.5)
        for i, m_name in enumerate(p['mercs']):
            col_m, col_b = st.columns([3, 1])
            refund = int(m_info[m_name]['price'] * refund_rate)
            col_m.write(f"**{m_name}** (+{m_info[m_name]['weight_bonus']}근)")
            if col_b.button(f"해고 ({refund:,}냥 환불)", key=f"fire_{i}"):
                p['money'] += refund
                p['mercs'].pop(i)
                st.rerun()
