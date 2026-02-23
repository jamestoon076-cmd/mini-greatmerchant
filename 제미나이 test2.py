import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- [수정 포인트 1] 시세 변동 로직: 시트의 volatility(5000)를 직접 대입 ---
def update_prices(settings, items_info, market_data, initial_stocks=None):
    if initial_stocks is None:
        initial_stocks = st.session_state.get('initial_stocks', {})
    
    # Setting_Data에서 직접 값 로드
    vol = settings.get('volatility', 5000) / 1000 # 5000 -> 5.0
    min_rate = settings.get('min_price_rate', 0.4)
    max_rate = settings.get('max_price_rate', 3.0)
    
    for v_name, v_data in market_data.items():
        if v_name == "용병 고용소": continue
            
        for i_name, i_val in v_data.items():
            if i_name in items_info:
                base = items_info[i_name]['base']
                stock = i_val['stock']
                init_s = initial_stocks.get(v_name, {}).get(i_name, 100)
                
                if stock <= 0:
                    i_val['price'] = int(base * max_rate)
                    continue
                
                # 📌 핵심 수식: (초기재고 / 현재재고) ^ (변동성 / 4)
                # 재고가 줄어들수록 가격이 지수함수적으로 폭등함
                ratio = init_s / stock
                factor = math.pow(ratio, (vol / 4))
                
                # 시트의 상하한선 적용
                final_factor = max(min_rate, min(max_rate, factor))
                i_val['price'] = int(base * final_factor)

# --- [수정 포인트 2] 분할 매매 로직: 100개씩 끊어서 현재 시세/무게 실시간 체크 ---
def process_buy(player, items_info, market_data, pos, item_name, qty, progress_placeholder, log_key):
    total_bought = 0
    total_spent = 0
    
    if log_key not in st.session_state.trade_logs:
        st.session_state.trade_logs[log_key] = []
    
    while total_bought < qty:
        # 매 루프마다 시세를 재계산 (재고가 줄어들면 가격이 오름)
        update_prices(st.session_state.settings, items_info, market_data, st.session_state.initial_stocks)
        target = market_data[pos][item_name]
        cw, tw = get_weight(player, items_info, st.session_state.merc_data)
        
        # 실시간 구매 가능 수량 체크
        can_pay = player['money'] // target['price'] if target['price'] > 0 else 0
        can_load = (tw - cw) // items_info[item_name]['w'] if items_info[item_name]['w'] > 0 else 999999
        
        # 100개 단위 또는 남은 수량 중 최소값
        batch = min(100, qty - total_bought, target['stock'], can_pay, can_load)
        
        if batch <= 0: # 돈이 없거나 무게가 차면 여기서 즉시 중단
            st.session_state.trade_logs[log_key].append("⚠️ 한도 도달: 거래가 자동 중단되었습니다.")
            break
        
        # 실제 데이터 차감
        player['money'] -= target['price'] * batch
        total_spent += target['price'] * batch
        player['inv'][item_name] = player['inv'].get(item_name, 0) + batch
        target['stock'] -= batch
        total_bought += batch
        
        log_msg = f"➤ {total_bought}/{qty} 구매 중... (현재가: {target['price']:,}냥)"
        st.session_state.trade_logs[log_key].append(log_msg)
        
        with progress_placeholder.container():
            st.markdown("<div class='trade-progress'>", unsafe_allow_html=True)
            for log in st.session_state.trade_logs[log_key][-5:]:
                st.markdown(f"<div class='trade-line'>{log}</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
        
        time.sleep(0.01) # 박진감을 위한 아주 짧은 딜레이
    
    return total_bought, total_spent

# --- [수정 포인트 3] 용병 해고: fire_refund_rate(0.5) 연동 ---
# (원본 코드의 tab3 해고 부분에서 아래 변수 활용)
refund_rate = settings.get('fire_refund_rate', 0.5)
refund = int(merc_data[merc]['price'] * refund_rate)
