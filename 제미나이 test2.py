import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import time
from datetime import datetime

# --- 1. DB 연결 및 초기 데이터 로드 ---
@st.cache_resource
def get_db_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gspread"], scopes=scopes)
    return gspread.authorize(creds).open("조선거상_DB")

def init_game_data():
    """앱 시작 시 딱 한 번 DB 데이터를 세션에 로드"""
    if 'settings' not in st.session_state:
        doc = get_db_client()
        # 시트 로드 (안전 함수)
        def get_ws(name):
            for s in doc.worksheets():
                if name in s.title: return s
            return None

        # 1. 설정값 (seconds_per_month, volatility 등)
        set_ws = get_ws("Setting_Data")
        st.session_state.settings = {r['변수명']: float(r['값']) for r in set_ws.get_all_records() if r.get('변수명')}
        
        # 2. 아이템 정보
        item_ws = get_ws("Item_Data")
        st.session_state.items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in item_ws.get_all_records()}
        
        # 3. 마을 데이터 (재고)
        vill_ws = get_ws("Village_Data")
        st.session_state.all_villages = vill_ws.get_all_records()
        
        # 4. 플레이어 세션 초기화
        play_ws = get_ws("Player_Data")
        p_init = play_ws.get_all_records()[0]
        st.session_state.player = {
            'slot': p_init['slot'], 'money': int(p_init['money']), 'pos': p_init['pos'],
            'inv': json.loads(p_init['inventory']) if p_init['inventory'] else {},
            'mercs': json.loads(p_init['mercs']) if p_init['mercs'] else [],
            'start_real_time': time.time()
        }
        st.session_state.game_base_date = {"year": 1592, "month": 1}

# 데이터 초기화 실행
init_game_data()

# 변수 할당
settings = st.session_state.settings
p = st.session_state.player
items_info = st.session_state.items_info

# --- 2. 시간 시스템 (180초 = 1달, 45초 = 1주) ---
def handle_time_system():
    sec_per_month = settings.get("seconds_per_month", 180)
    sec_per_week = sec_per_month / 4
    
    elapsed = time.time() - p['start_real_time']
    total_weeks = int(elapsed // sec_per_week)
    
    # 1주마다 토스트 메시지 알림
    if 'last_week_notified' not in st.session_state:
        st.session_state.last_week_notified = -1
    if total_weeks > st.session_state.last_week_notified:
        week_num = (total_weeks % 4) + 1
        st.toast(f"🔔 {week_num}주차 일정이 시작되었습니다!")
        st.session_state.last_week_notified = total_weeks

    total_months = int(elapsed // sec_per_month)
    curr_month = (st.session_state.game_base_date
