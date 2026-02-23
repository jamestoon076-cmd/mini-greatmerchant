import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 페이지 설정 및 디자인 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="wide")

# --- 2. 데이터 연동 (캐싱 강화) ---
@st.cache_resource
def get_gsheet_client():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        return None

@st.cache_data(ttl=600)
def load_static_db():
    doc = get_gsheet_client()
    if not doc: return None
    try:
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
        items = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        mercs = {r['name']: {'price': int(r['price']), 'w_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
        return settings, items, mercs
    except: return None

# --- 3. 시간 및 재고 동기화 (에러 방지 로직 추가) ---
def update_game_time_and_sync(doc):
    if 'start_time' not in st.session_state:
        st.session_state.start_time = time.time()
    
    elapsed = int(time.time() - st.session_state.start_time)
    current_total_months = elapsed // 180
    
    if 'last_reset_month' not in st.session_state:
        st.session_state.last_reset_month = 0
    
    # 달이 바뀌었을 때 재고 초기화
    if current_total_months > st.session_state.last_reset_month:
        try:
            new_villages = doc.worksheet("Village_Data").get_all_records()
            if new_villages:
                st.session_state.villages = new_villages
                st.session_state.last_reset_month = current_total_months
                st.toast("🌙 달이 바뀌어 시장 재고가 초기화되었습니다!", icon="♻️")
        except:
            # API 에러 시 다음 루프에서 재시도하도록 유지
            pass

    year = (current_total_months // 12) + 1
    month = (current_total_months % 12) + 1
    week = ((elapsed % 180) // 45) + 1
    return year, month, week, elapsed % 45

# --- 4. 핵심 함수 ---
def get_status(player, items_info, mercs_info):
    curr_w = sum(count * items_info.get(item, {}).get('w', 0) for item, count in player['inventory'].items())
    max_w = 1000 + sum(mercs_info.get(m, {}).get('w_bonus', 0) for m in player['mercs'])
    return curr_w, max_w

def calculate_price(item_name, stock, items_info, settings):
    base = items_info.get(item_name, {}).get('base', 100)
    vol = settings.get('volatility', 5000) / 1000
    curr_s = max(1, int(stock))
    ratio = 5000 / curr_s 
    return int(base * max(0.5, min(20.0, math.pow(ratio, (vol / 4)))))

# --- 5. 메인 엔진 ---
static_data = load_static_db()
if static_data:
    settings, items_info, mercs_info = static_data
    doc = get_gsheet_client()
    
    # 시간 및 재고 동기화
    year, month, week, next_week_remains = update_game_time_and_sync(doc)

    if 'game_started' not in st.session_state:
        st.session_state.game_started = False
        if 'villages' not in st.session_state:
            st.session_state.villages = doc.worksheet("Village_Data").get_all_records()

    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        # 접속 화면 생략 (기존 코드와 동일)
        # ... [슬롯 선택 코드] ...
        # (테스트를 위해 시작 버튼 로직이 있다고 가정)
        if st.button("게임 시작 (1번 슬롯)"): # 예시
             p = doc.worksheet("Player_Data").get_all_records()[0]
             st.session_state.player = {
                 'money': int(p['money']), 'pos': p['pos'],
                 'inventory': json.loads(p['inventory']) if p['inventory'] else {},
                 'mercs': json.loads(p['mercs']) if p['mercs'] else []
             }
             st.session_state.game_started = True
             st.rerun()

    else:
        player = st.session_state.player
        curr_w, max_w = get_status(player, items_info, mercs_info)

        # 상단 UI
        st.markdown(f"### 📅 {year}년 {month}월 {week}주차 | 💰 {player['money']:,}냥 | ⚖️ {curr_w:,}/{max_w:,}")
        
        tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🚩 이동", "🎒 정보", "⚔️ 주막"])

        with tab1:
            # [방어 코드] 마을 데이터를 세션에서 찾기
            villages = st.session_state.get('villages', [])
            v_data = next((v for v in villages if v['village_name'] == player['pos']), None)

            if v_data:
                for item in items_info.keys():
                    # [에러 수정 포인트] .get(item, 0) 결과가 공백일 경우 대비
                    raw_stock = v_data.get(item, 0)
                    stock = int(raw_stock) if str(raw_stock).isdigit() else 1
                    
                    price = calculate_price(item, stock, items_info, settings)
                    my_stock = player['inventory'].get(item, 0)
                    
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"**{item}** (시장: {stock:,} | 보유: {my_stock:,})")
                    c2.write(f"{price:,}냥")
                    if c3.button("선택", key=f"t_{item}"): st.session_state.active_trade = item
                
                # ... [매수/매도 로직 기존과 동일] ...
            else:
                st.error("현재 위치의 상점 데이터를 불러올 수 없습니다. 이동 탭을 이용해 주세요.")

        with tab2: # 이동
            # 이동 시 세션에 마을 데이터가 있는지 확인
            if 'villages' in st.session_state:
                for v in st.session_state.villages:
                    if v['village_name'] == player['pos']: continue
                    if st.button(f"{v['village_name']} 이동"):
                        player['pos'] = v['village_name']
                        st.rerun()
