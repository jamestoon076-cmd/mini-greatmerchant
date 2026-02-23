import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import time
import math
from datetime import datetime

# --- 1. 초기화 및 데이터 로드 ---
@st.cache_resource
def get_db_client():
    creds = Credentials.from_service_account_info(st.secrets["gspread"], 
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
    return gspread.authorize(creds).open("조선거상_DB")

def init_session():
    """필수 데이터 세션 로드 및 에러 방지 초기화"""
    if 'settings' not in st.session_state:
        doc = get_db_client()
        # 시트 데이터 일괄 로드
        st.session_state.settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
        st.session_state.items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        st.session_state.all_villages = doc.worksheet("Village_Data").get_all_records()
        st.session_state.mercs_db = {r['name']: {'price': int(r['price']), 'w_bonus': int(r.get('weight_bonus', 0))} for r in doc.worksheet("Balance_Data").get_all_records()}
        
        # 플레이어 초기값 (Player_Data 1번 슬롯 기준)
        p_raw = doc.worksheet("Player_Data").get_all_records()[0]
        st.session_state.player = {
            'money': int(p_raw['money']), 'pos': p_raw['pos'],
            'inv': json.loads(p_raw['inventory']) if p_raw['inventory'] else {},
            'mercs': json.loads(p_raw['mercs']) if p_raw['mercs'] else [],
            'start_real_time': time.time()
        }
        st.session_state.base_date = {"year": 1592, "month": 1}

init_session()

# 변수 할당
settings = st.session_state.settings
p = st.session_state.player
items_info = st.session_state.items_info

# --- 2. 시간 시스템 (180초 = 1달 / 45초 = 1주) ---
def handle_game_time():
    sec_per_month = settings.get("seconds_per_month", 180) # DB 연동
    sec_per_week = sec_per_month / 4
    
    elapsed = time.time() - p['start_real_time']
    
    # 달/년 계산
    total_months = int(elapsed // sec_per_month)
    curr_month = (st.session_state.base_date['month'] + total_months - 1) % 12 + 1
    curr_year = st.session_state.base_date['year'] + (st.session_state.base_date['month'] + total_months - 1) // 12
    
    # 1주 단위 알림 로직
    total_weeks = int(elapsed // sec_per_week)
    if 'last_week' not in st.session_state: st.session_state.last_week = -1
    if total_weeks > st.session_state.last_week:
        st.toast(f"🔔 {(total_weeks % 4) + 1}주차 일정이 시작되었습니다!")
        st.session_state.last_week = total_weeks
        
    return curr_year, curr_month, elapsed

# --- 3. 실시간 분할 체결 로직 (0.3초당 100개) ---
def get_dynamic_price(item, current_stock):
    """재고와 변동성(volatility)을 반영한 실시간 시세 계산"""
    base = items_info[item]['base']
    vol = settings.get('volatility', 5000)
    ratio = current_stock / 100  # 기준 재고 100
    
    # 재고에 따른 기본 배율 (가격변동개선.py 로직)
    factor = 2.5 if ratio < 0.5 else 1.8 if ratio < 1.0 else 1.0
    # 변동성 적용 (많이 살수록 가격 상승 가속)
    vol_adj = 1 + (vol / 50000) * (1 / (ratio + 0.1))
    return int(base * factor * vol_adj)

def run_trade_ui(item_name, target_qty, mode="buy"):
    v_row = next((v for v in st.session_state.all_villages if v['village_name'] == p['pos']), None)
    stock = int(v_row.get(item_name, 0)) if v_row else 0
    
    log_area = st.empty()
    logs = [f"**{ '매수' if mode == 'buy' else '매도' } 수량 >> {target_qty}**"]
    
    executed = 0
    total_cost = 0
    
    while executed < target_qty:
        batch = min(100, target_qty - executed)
        price = get_dynamic_price(item_name, stock)
        
        if mode == "buy":
            if p['money'] < price * batch:
                logs.append("❌ 잔액 부족으로 중단")
                break
            p['money'] -= price * batch
            p['inv'][item_name] = p['inv'].get(item_name, 0) + batch
            stock -= batch
        else: # sell
            if p['inv'].get(item_name, 0) < batch:
                logs.append("❌ 소지 물량 부족으로 중단")
                break
            p['money'] += price * batch
            p['inv'][item_name] -= batch
            stock += batch
            
        executed += batch
        total_cost += (price * batch)
        avg_p = int(total_cost / executed)
        
        # 메세지 출력 (요청 양식)
        logs.append(f" ➤ {executed}/{target_qty} {'구매' if mode=='buy' else '판매'} 중... (체결가 {price}냥 / 평균가 : {avg_p} )")
        log_area.markdown("\n".join(logs))
        time.sleep(0.3)
        
    st.success(f"총 {executed}개 거래 완료했습니다.")

# --- 4. 메인 UI 화면 ---
year, month, elapsed = handle_game_time()

# 상단바: 도시 이름 + 실시간 시간
st.title(f"📍 {p['pos']}")
st.markdown(f"📅 **{year}년 {month}월** | ⏱️ {int(elapsed)}초 경과")

# 상태 요약
curr_w = sum(p['inv'].get(i, 0) * items_info[i]['w'] for i in p['inv'] if i in items_info)
max_w = 200 + sum(st.session_state.mercs_db[m]['w_bonus'] for m in p['mercs'] if m in st.session_state.mercs_db)
st.info(f"💰 {p['money']:,}냥 | ⚖️ {curr_w}/{max_w}근")

tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🚩 이동", "🎒 상단 정보", "⚔️ 고용소"])

with tab1: # 저잣거리
    v_data = next((v for v in st.session_state.all_villages if v['village_name'] == p['pos']), None)
    if v_data and p['pos'] != "용병 고용소":
        for item in items_info.keys():
            s = int(v_data.get(item, 0)) if v_data.get(item) else 0
            pr = get_dynamic_price(item, s)
            with st.expander(f"{item} (시세: {pr}냥 | 재고: {s})"):
                t_qty = st.number_input("수량", 1, 10000, key=f"q_{item}", value=420)
                if st.button("매수 시작", key=f"b_{item}"):
                    run_trade_ui(item, t_qty, "buy")
    else:
        st.write("이곳에는 상점이 없습니다.")

with tab2: # 이동
    for v in st.session_state.all_villages:
        if v['village_name'] != p['pos']:
            if st.button(f"{v['village_name']}로 이동", key=f"mv_{v['village_name']}"):
                p['pos'] = v['village_name']
                st.rerun()

with tab3: # 상단 정보 및 해고
    st.subheader("👨‍전 상단 관리")
    col_inv, col_merc = st.columns(2)
    with col_inv:
        st.write("**[소지품]**")
        for it, count in p['inv'].items():
            if count > 0: st.write(f"- {it}: {count}개")
    with col_merc:
        st.write("**[용병]**")
        for idx, m_name in enumerate(p['mercs']):
            c1, c2 = st.columns([3, 1])
            c1.write(f"{m_name}")
            if c2.button("해고", key=f"fire_{idx}"):
                p['mercs'].pop(idx)
                st.rerun()

# 1초마다 루프 (시간 갱신용)
time.sleep(1)
st.rerun()
