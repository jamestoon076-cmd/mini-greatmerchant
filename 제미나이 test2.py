import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import time
import json
import math
from datetime import datetime

# --- 1. 데이터 로드 및 시세 변동 로직 ---
def calc_realtime_price(item, stock, items_info, settings):
    """가격변동개선.py의 로직 + volatility 반영"""
    base = items_info[item]['base']
    volatility = settings.get('volatility', 5000)
    
    # 재고 기반 기본 배율
    initial_stock = 100 
    ratio = stock / initial_stock if stock > 0 else 0
    if ratio < 0.5: factor = 2.5
    elif ratio < 1.0: factor = 1.8
    else: factor = 1.0
    
    # 변동성 미세 조정 (예시: 재고가 100개 변할 때마다 시세에 영향)
    vol_effect = (volatility / 10000) * (1.0 / (ratio + 0.1))
    
    return int(base * factor)

# --- 2. 실시간 분할 체결 시스템 (0.3초당 100개) ---
def execute_trade(item_name, target_qty, mode="buy"):
    """0.3초마다 최대 100개씩 체결하며 메세지 출력"""
    p = st.session_state.player
    items_info = st.session_state.items_info
    settings = st.session_state.settings
    
    # 현재 마을 재고 데이터 가져오기 (세션 내 복사본 사용)
    v_data = st.session_state.current_village_data
    current_stock = int(v_data.get(item_name, 0))
    
    progress_log = st.empty() # 메세지 출력용 공간
    log_content = [f"**{'매수' if mode == 'buy' else '매도'} 수량 >> {target_qty}**"]
    
    total_executed = 0
    total_cost = 0
    
    while total_executed < target_qty:
        # 이번 턴에 체결할 수량 (최대 100개)
        batch_qty = min(100, target_qty - total_executed)
        
        # 실시간 가격 계산
        current_price = calc_realtime_price(item_name, current_stock, items_info, settings)
        
        # 자금/재고 체크
        if mode == "buy":
            if p['money'] < current_price * batch_qty:
                log_content.append(f"❌ 자금 부족으로 중단 ({total_executed}개까지 완료)")
                break
            p['money'] -= current_price * batch_qty
            p['inv'][item_name] = p['inv'].get(item_name, 0) + batch_qty
            current_stock -= batch_qty
        else: # sell
            if p['inv'].get(item_name, 0) < batch_qty:
                log_content.append(f"❌ 물량 부족으로 중단")
                break
            p['money'] += current_price * batch_qty
            p['inv'][item_name] -= batch_qty
            current_stock += batch_qty
            
        total_executed += batch_qty
        total_cost += (current_price * batch_qty)
        avg_price = int(total_cost / total_executed)
        
        # 메세지 업데이트
        log_content.append(f"➤ {total_executed}/{target_qty} {'구매' if mode=='buy' else '판매'} 중... (체결가 {current_price}냥 / 평균가: {avg_price}냥)")
        progress_log.markdown("\n".join(log_content))
        
        time.sleep(0.3) # 0.3초 대기
    
    log_content.append(f"**✅ 총 {total_executed}개 {'구매' if mode=='buy' else '판매'} 완료했습니다.**")
    progress_log.markdown("\n".join(log_content))
    # 실제 마을 재고 반영 (DB 업데이트는 별도 저장 시)
    v_data[item_name] = current_stock

# --- 3. 시간 시스템 (180초 = 1달, 1주마다 메세지) ---
def handle_time_system():
    settings = st.session_state.settings
    sec_per_month = settings.get("seconds_per_month", 180)
    sec_per_week = sec_per_month / 4
    
    elapsed = time.time() - st.session_state.start_real_time
    total_weeks = int(elapsed // sec_per_week)
    
    # 1주(45초)마다 알림 출력
    if 'last_week_notified' not in st.session_state:
        st.session_state.last_week_notified = 0
        
    if total_weeks > st.session_state.last_week_notified:
        st.toast(f"🔔 {total_weeks % 4 + 1}주차 일정이 시작되었습니다!")
        st.session_state.last_week_notified = total_weeks

    # 달 계산
    total_months = int(elapsed // sec_per_month)
    curr_month = (st.session_state.game_base_month + total_months - 1) % 12 + 1
    curr_year = st.session_state.game_base_year + (st.session_state.game_base_month + total_months - 1) // 12
    
    return curr_year, curr_month, elapsed

# --- 4. 메인 UI ---
# 상단 타이틀: 도시 이름 + 실시간 타이머
p = st.session_state.player
year, month, elapsed = handle_time_system()

st.title(f"📍 {p['pos']}")
st.markdown(f"**📅 {year}년 {month}월** (다음 달까지 {int(180 - (elapsed % 180))}초)")

# 상점 UI 예시
with st.expander("쌀 저잣거리"):
    qty = st.number_input("거래 수량", min_value=1, value=420)
    if st.button("매수 시작"):
        execute_trade("쌀", qty, "buy")

# 실시간 갱신을 위한 루프
time.sleep(1)
st.rerun()
