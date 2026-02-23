import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import time
from datetime import datetime

# --- 1. 페이지 설정 및 초기화 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

@st.cache_resource
def get_db_client():
    # Streamlit Secrets 사용
    creds = Credentials.from_service_account_info(st.secrets["gspread"], 
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
    return gspread.authorize(creds).open("조선거상_DB")

def init_session():
    """세션 상태 초기화 (AttributeError 방지)"""
    if 'player' not in st.session_state:
        doc = get_db_client()
        
        # 1. 시트 데이터 로드
        st.session_state.settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
        st.session_state.items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        st.session_state.all_villages = doc.worksheet("Village_Data").get_all_records()
        st.session_state.mercs_db = {r['name']: {'price': int(r['price']), 'w_bonus': int(r.get('weight_bonus', 0))} for r in doc.worksheet("Balance_Data").get_all_records()}
        
        # 2. 플레이어 데이터 (첫 번째 슬롯 예시)
        p_raw = doc.worksheet("Player_Data").get_all_records()[0]
        st.session_state.player = {
            'money': int(p_raw['money']),
            'pos': p_raw['pos'],
            'inv': json.loads(p_raw['inventory']) if p_raw['inventory'] else {},
            'mercs': json.loads(p_raw['mercs']) if p_raw['mercs'] else [],
            'start_real_time': time.time()
        }
        
        # 3. 에러 발생했던 날짜 변수 초기화
        st.session_state.base_date = {"year": 1592, "month": 1}
        st.session_state.last_week = -1

# 초기화 실행
init_session()

# 편의를 위한 변수 할당
p = st.session_state.player
settings = st.session_state.settings
items_info = st.session_state.items_info

# --- 2. 시간 시스템 (180초 = 1달, 45초 = 1주 알림) ---
def handle_game_time():
    sec_per_month = settings.get("seconds_per_month", 180) # DB의 180초 연동
    sec_per_week = sec_per_month / 4
    
    elapsed = time.time() - p['start_real_time']
    
    # 월/년 계산 (SyntaxError 방지를 위해 괄호 체크 완료)
    total_months = int(elapsed // sec_per_month)
    curr_month = (st.session_state.base_date['month'] + total_months - 1) % 12 + 1
    curr_year = st.session_state.base_date['year'] + (st.session_state.base_date['month'] + total_months - 1) // 12
    
    # 1주 단위 알림 (45초마다)
    total_weeks = int(elapsed // sec_per_week)
    if total_weeks > st.session_state.last_week:
        st.toast(f"🔔 {(total_weeks % 4) + 1}주차 일정이 시작되었습니다!")
        st.session_state.last_week = total_weeks
        
    return curr_year, curr_month, elapsed

# --- 3. 실시간 분할 체결 (0.3초당 100개) ---
def get_current_price(item, stock):
    base = items_info[item]['base']
    vol = settings.get('volatility', 5000)
    # 재고 비례 시세 공식
    ratio = stock / 100
    factor = 2.5 if ratio < 0.5 else 1.8 if ratio < 1.0 else 1.0
    return int(base * factor * (1 + vol/100000))

def start_trade(item_name, target_qty, mode="buy"):
    # 현재 마을 재고 찾기
    v_row = next((v for v in st.session_state.all_villages if v['village_name'] == p['pos']), None)
    stock = int(v_row.get(item_name, 0)) if v_row else 0
    
    log_area = st.empty()
    logs = [f"**구매 수량 >> {target_qty}**" if mode == "buy" else f"**판매 수량 >> {target_qty}**"]
    
    done = 0
    total_spent = 0
    
    while done < target_qty:
        batch = min(100, target_qty - done)
        price = get_current_price(item_name, stock)
        
        if mode == "buy":
            if p['money'] < price * batch:
                logs.append("❌ 잔액 부족으로 중단되었습니다.")
                break
            p['money'] -= price * batch
            p['inv'][item_name] = p['inv'].get(item_name, 0) + batch
            stock -= batch
        else: # sell
            if p['inv'].get(item_name, 0) < batch:
                logs.append("❌ 소지 물량 부족으로 중단되었습니다.")
                break
            p['money'] += price * batch
            p['inv'][item_name] -= batch
            stock += batch
            
        done += batch
        total_spent += (price * batch)
        avg_p = int(total_spent / done)
        
        # 메세지 실시간 출력
        logs.append(f" ➤ {done}/{target_qty} {'구매' if mode=='buy' else '판매'} 중... (체결가 {price}냥 / 평균가 : {avg_p} )")
        log_area.markdown(f"""<div style="background-color:#f0f2f6; padding:10px; border-radius:5px; font-family:monospace;">
            {"<br>".join(logs)}</div>""", unsafe_allow_html=True)
        
        time.sleep(0.3) # 0.3초 간격
    
    st.success(f"총 {done}개 거래가 완료되었습니다.")

# --- 4. 메인 UI 화면 ---
year, month, elapsed = handle_game_time()

# 상단 제목: 도시 이름 + 실시간 타이머
st.title(f"📍 {p['pos']}")
st.markdown(f"📅 **{year}년 {month}월** | ⏱️ {int(elapsed)}초 경과")

# 상태 요약 (소지금, 무게)
curr_w = sum(p['inv'].get(i, 0) * items_info[i]['w'] for i in p['inv'] if i in items_info)
max_w = 200 + sum(st.session_state.mercs_db[m]['w_bonus'] for m in p['mercs'] if m in st.session_state.mercs_db)
st.divider()
col_info1, col_info2 = st.columns(2)
col_info1.metric("💰 소지금", f"{p['money']:,}냥")
col_info2.metric("⚖️ 무게", f"{curr_w}/{max_w}근")

# 메뉴 탭
tab1, tab2, tab3 = st.tabs(["🛒 저잣거리", "🚩 팔도이동", "🎒 상단정보"])

with tab1:
    v_data = next((v for v in st.session_state.all_villages if v['village_name'] == p['pos']), None)
    if v_data and p['pos'] != "용병 고용소":
        for item in items_info.keys():
            s = int(v_data.get(item, 0)) if v_data.get(item) else 0
            pr = get_current_price(item, s)
            with st.expander(f"{item} (시세: {pr}냥 | 재고: {s})"):
                t_qty = st.number_input("수량 입력", 1, 10000, key=f"q_{item}", value=420)
                if st.button("매수", key=f"b_{item}"):
                    start_trade(item, t_qty, "buy")
                if st.button("매도", key=f"s_{item}"):
                    start_trade(item, t_qty, "sell")
    else:
        st.info("이곳은 상점이 없는 특수 지역입니다.")

with tab2:
    st.subheader("이동할 마을 선택")
    for v in st.session_state.all_villages:
        if v['village_name'] != p['pos']:
            if st.button(f"{v['village_name']}로 이동", key=f"mv_{v['village_name']}"):
                p['pos'] = v['village_name']
                st.rerun()

# 1초마다 화면 갱신 (시간 흐름 구현)
time.sleep(1)
st.rerun()
