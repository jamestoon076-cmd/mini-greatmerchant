import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import time
from datetime import datetime

# --- 1. 초기 데이터 로드 및 세션 초기화 ---
def init_game():
    if 'settings' not in st.session_state:
        # DB 연결 및 데이터 로드 (실제 환경에선 gspread 함수 호출)
        # 예시 데이터 (실제 DB에서 settings['seconds_per_month'] = 180 로드됨)
        st.session_state.settings = {"seconds_per_month": 180.0, "volatility": 5000.0}
        st.session_state.items_info = {"쌀": {"base": 150, "w": 10}, "인삼": {"base": 320, "w": 3}}
        st.session_state.player = {
            "pos": "한양", "money": 925043, "inv": {"쌀": 0}, "mercs": [],
            "start_real_time": time.time()
        }
        st.session_state.game_base_date = {"year": 1592, "month": 1}

init_game()

# 변수 단축 지정
p = st.session_state.player
settings = st.session_state.settings

# --- 2. 시간 시스템 (180초 = 1달, 45초 = 1주 알림) ---
def handle_time():
    sec_per_month = settings.get("seconds_per_month", 180)
    sec_per_week = sec_per_month / 4
    
    elapsed = time.time() - p['start_real_time']
    
    # [SyntaxError 해결 구간] 괄호를 정확히 닫음
    total_months = int(elapsed // sec_per_month)
    curr_month = (st.session_state.game_base_date['month'] + total_months - 1) % 12 + 1
    curr_year = st.session_state.game_base_date['year'] + (st.session_state.game_base_date['month'] + total_months - 1) // 12
    
    # 1주마다 알림
    total_weeks = int(elapsed // sec_per_week)
    if 'last_notified_week' not in st.session_state: st.session_state.last_notified_week = -1
    if total_weeks > st.session_state.last_notified_week:
        st.toast(f"🔔 { (total_weeks % 4) + 1 }주차 일정이 시작되었습니다!")
        st.session_state.last_notified_week = total_weeks
        
    return curr_year, curr_month, elapsed

# --- 3. 실시간 분할 체결 시스템 (0.3초당 100개) ---
def execute_realtime_trade(item_name, target_qty, mode="buy"):
    log_area = st.empty()
    logs = [f"**{mode} 수량 >> {target_qty}**"]
    
    done = 0
    total_cost = 0
    
    while done < target_qty:
        batch = min(100, target_qty - done)
        
        # 시세 계산 (간략화된 로직)
        base_price = st.session_state.items_info[item_name]['base']
        current_price = base_price # 여기에 volatility 반영 공식 추가 가능
        
        if mode == "buy":
            p['money'] -= current_price * batch
            p['inv'][item_name] = p['inv'].get(item_name, 0) + batch
        else:
            p['money'] += current_price * batch
            p['inv'][item_name] -= batch
            
        done += batch
        total_cost += (current_price * batch)
        avg_price = int(total_cost / done)
        
        # 요청하신 형식의 메세지 출력
        logs.append(f" ➤ {done}/{target_qty} 구매 중... (체결가 {current_price}냥 / 평균가 : {avg_price} )")
        log_area.markdown("\n".join(logs))
        
        time.sleep(0.3) # 0.3초 대기

# --- 4. 메인 UI 출력 ---
year, month, elapsed = handle_time()

# 상단 제목: 도시 이름 + 실시간 시간
st.title(f"📍 {p['pos']}")
st.markdown(f"📅 **{year}년 {month}월** | ⏱️ {int(elapsed)}초 경과")

# 거래소 예시
with st.expander("🌾 쌀 상점"):
    trade_num = st.number_input("거래 수량", value=420)
    if st.button("실시간 매수 시작"):
        execute_realtime_trade("쌀", trade_num, "buy")

# 실시간 갱신
time.sleep(1)
st.rerun()
