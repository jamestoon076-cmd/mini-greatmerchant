import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import time
import math
from datetime import datetime

# --- 1. 페이지 설정 및 디자인 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

# --- 2. 데이터 연동 및 시트 찾기 함수 ---
@st.cache_resource
def get_gsheet_client():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"DB 연결 실패: {e}")
        return None

def get_worksheet_safe(doc, name):
    """시트 이름이 정확하지 않아도 유사한 이름을 찾아주는 안전 함수"""
    try:
        return doc.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        sheets = doc.worksheets()
        for s in sheets:
            if name.strip().lower() in s.title.strip().lower():
                return s
        raise gspread.exceptions.WorksheetNotFound(f"'{name}' 시트를 찾을 수 없습니다.")

def init_session():
    """모든 필수 데이터를 세션에 로드 (WorksheetNotFound 및 AttributeError 방지)"""
    if 'player' not in st.session_state:
        # 에러 방지용 기본값 선언
        st.session_state.base_date = {"year": 1592, "month": 1}
        st.session_state.last_week = -1
        
        doc = get_gsheet_client()
        if not doc: return

        # 1. 설정 및 아이템 정보 로드 (유연한 시트 찾기 적용)
        set_ws = get_worksheet_safe(doc, "Setting_Data")
        item_ws = get_worksheet_safe(doc, "Item_Data")
        vill_ws = get_worksheet_safe(doc, "Village_Data")
        bal_ws = get_worksheet_safe(doc, "Balance_Data")
        play_ws = get_worksheet_safe(doc, "Player_Data")

        st.session_state.settings = {r['변수명']: float(r['값']) for r in set_ws.get_all_records() if r.get('변수명')}
        st.session_state.items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in item_ws.get_all_records()}
        st.session_state.all_villages = vill_ws.get_all_records()
        st.session_state.mercs_db = {r['name']: {'price': int(r['price']), 'w_bonus': int(r.get('weight_bonus', 0))} for r in bal_ws.get_all_records()}
        
        # 2. 플레이어 데이터 (1번 슬롯 기준)
        p_raw = play_ws.get_all_records()[0]
        st.session_state.player = {
            'money': int(p_raw['money']),
            'pos': p_raw['pos'],
            'inv': json.loads(p_raw['inventory']) if p_raw['inventory'] else {},
            'mercs': json.loads(p_raw['mercs']) if p_raw['mercs'] else [],
            'start_real_time': time.time()
        }

init_session()

# 변수 연결
p = st.session_state.player
settings = st.session_state.settings
items_info = st.session_state.items_info

# --- 3. 시간 시스템 (180초 = 1달, 45초 = 1주 알림) ---
def handle_game_time():
    sec_per_month = settings.get("seconds_per_month", 180)
    sec_per_week = sec_per_month / 4
    elapsed = time.time() - p['start_real_time']
    
    total_months = int(elapsed // sec_per_month)
    curr_month = (st.session_state.base_date['month'] + total_months - 1) % 12 + 1
    curr_year = st.session_state.base_date['year'] + (st.session_state.base_date['month'] + total_months - 1) // 12
    
    # 45초마다 주차 알림
    total_weeks = int(elapsed // sec_per_week)
    if total_weeks > st.session_state.last_week:
        st.toast(f"🔔 {(total_weeks % 4) + 1}주차 일정이 시작되었습니다!")
        st.session_state.last_week = total_weeks
        
    return curr_year, curr_month, elapsed

# --- 4. 실시간 분할 체결 시스템 (0.3초당 100개) ---
def execute_trade(item_name, target_qty, mode="buy"):
    v_row = next((v for v in st.session_state.all_villages if v['village_name'] == p['pos']), None)
    stock = int(v_row.get(item_name, 0)) if v_row else 0
    vol = settings.get('volatility', 5000)
    
    log_area = st.empty()
    logs = [f"**{mode.upper()} 수량 >> {target_qty}**"]
    
    done = 0
    total_cost = 0
    
    while done < target_qty:
        batch = min(100, target_qty - done)
        
        # 시세 계산 로직 (가격변동개선.py 기준)
        ratio = stock / 100
        factor = 2.5 if ratio < 0.5 else 1.8 if ratio < 1.0 else 1.0
        current_price = int(items_info[item_name]['base'] * factor * (1 + vol/100000))
        
        if mode == "buy":
            if p['money'] < current_price * batch: break
            p['money'] -= current_price * batch
            p['inv'][item_name] = p['inv'].get(item_name, 0) + batch
            stock -= batch
        else:
            if p['inv'].get(item_name, 0) < batch: break
            p['money'] += current_price * batch
            p['inv'][item_name] -= batch
            stock += batch
            
        done += batch
        total_cost += (current_price * batch)
        avg_p = int(total_cost / done)
        
        logs.append(f" ➤ {done}/{target_qty} 진행 중... (체결가 {current_price}냥 / 평균가 : {avg_p} )")
        log_area.markdown("\n".join(logs))
        time.sleep(0.3)
    
    st.success(f"✅ 총 {done}개 거래 완료!")

# --- 5. UI 메인 렌더링 ---
year, month, elapsed = handle_game_time()

# 요청하신 상단 제목: 도시 이름 + 실시간 시간
st.title(f"📍 {p['pos']}")
st.markdown(f"📅 **{year}년 {month}월** | ⏱️ {int(elapsed)}초 경과")

# 무게 계산
curr_w = sum(p['inv'].get(i, 0) * items_info[i]['w'] for i in p['inv'] if i in items_info)
max_w = 200 + sum(st.session_state.mercs_db[m]['w_bonus'] for m in p['mercs'] if m in st.session_state.mercs_db)

st.info(f"💰 {p['money']:,}냥 | ⚖️ {curr_w}/{max_w}근")

tab1, tab2, tab3 = st.tabs(["🛒 저잣거리", "🚩 팔도이동", "🎒 상단정보"])

with tab1:
    v_data = next((v for v in st.session_state.all_villages if v['village_name'] == p['pos']), None)
    if v_data and p['pos'] != "용병 고용소":
        for item in items_info.keys():
            s = int(v_data.get(item, 0)) if v_data.get(item) else 0
            with st.expander(f"{item} (재고: {s})"):
                t_qty = st.number_input("거래 수량", 1, 10000, key=f"t_{item}", value=420)
                if st.button("매수 시작", key=f"b_{item}"):
                    execute_trade(item, t_qty, "buy")
                if st.button("매도 시작", key=f"s_{item}"):
                    execute_trade(item, t_qty, "sell")
    else:
        st.warning("이곳은 상점이 없습니다.")

with tab2:
    st.subheader("🚩 이동할 행선지")
    for v in st.session_state.all_villages:
        if v['village_name'] != p['pos']:
            if st.button(f"{v['village_name']}로 이동", key=f"mv_{v['village_name']}"):
                p['pos'] = v['village_name']
                st.rerun()

# 실시간 시간 업데이트를 위한 리런
time.sleep(1)
st.rerun()
