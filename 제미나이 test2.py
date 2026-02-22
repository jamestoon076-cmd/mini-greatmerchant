import time
import json
import sys
import math
import gspread
import streamlit as st
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- 1. 유틸리티 함수 ---
def safe_int_input(prompt, min_val=None, max_val=None):
    """사용자로부터 안전하게 정수 입력을 받는 함수 (웹용 st.text_input 활용 권장하나 로직 유지를 위해 남김)"""
    while True:
        try:
            line = input(prompt).strip()
            if not line: continue
            val = int(line)
            if min_val is not None and val < min_val:
                print(f"⚠️ {min_val} 이상의 숫자를 입력하세요.")
                continue
            if max_val is not None and val > max_val:
                print(f"⚠️ {max_val} 이하의 숫자를 입력하세요.")
                continue
            return val
        except ValueError:
            print("❌ 숫자만 입력하세요.")

# --- 2. 시트 연결 (가장 중요한 수정 부분!) ---
def connect_gsheet():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        # [수정] 내 컴퓨터 주소(C:/Users/...)를 지우고 스트림릿 Secrets를 사용합니다.
        creds_info = st.secrets["gspread"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"❌ 연결 실패: {e}. 스트림릿 Secrets 설정을 확인하세요!")
        sys.exit()

# 프로그램 실행 시 시트 연결
doc = connect_gsheet()

# --- 3. 데이터 로드 및 초기화 (원본 로직 100% 유지) ---
def load_all_data():
    try:
        set_ws = doc.worksheet("Setting_Data")
        settings = {r['변수명']: float(r['값']) for r in set_ws.get_all_records()}
        
        item_ws = doc.worksheet("Item_Data")
        items_info = {str(r['item_name']).strip(): {'base': int(r['base_price']), 'w': int(r['weight'])} 
                      for r in item_ws.get_all_records() if r.get('item_name')}
        
        bal_ws = doc.worksheet("Balance_Data")
        merc_data = {r['name'].strip(): {'price': int(r['price']), 'w_bonus': int(r.get('weight_bonus', 0))} 
                     for r in bal_ws.get_all_records()}
        
        vil_ws = doc.worksheet("Village_Data")
        vil_vals = vil_ws.get_all_values()
        headers = [h.strip() for h in vil_vals[0]]
        villages = {}
        initial_stocks = {}
        for row in vil_vals[1:]:
            v_name = row[0].strip()
            if not v_name: continue
            villages[v_name] = {'items': {}, 'x': int(row[1]), 'y': int(row[2])}
            initial_stocks[v_name] = {}
            if v_name != "용병 고용소":
                for i in range(3, len(headers)):
                    if i < len(row) and headers[i] in items_info and row[i]:
                        stock = int(row[i])
                        villages[v_name]['items'][headers[i]] = stock
                        initial_stocks[v_name][headers[i]] = stock
        
        play_ws = doc.worksheet("Player_Data")
        slots = play_ws.get_all_records()
        
       # --- 기존 코드 수정 구간 ---
st.write("### 💾 세이브 슬롯 선택")
for s in slots:
    st.write(f"[{s['slot']}] 위치: {s['pos']} | 잔액: {int(s.get('money', 0)):,}냥")

# 1. 숫자를 입력받고
choice = st.number_input("슬롯 번호를 선택하세요", min_value=1, max_value=len(slots), step=1)

# 2. 엔터 대신 누를 수 있는 '확인 버튼' 추가
if st.button("🎮 게임 시작하기"):
    p_row = next(s for s in slots if s['slot'] == choice)
    
    # 세션 상태(session_state)에 플레이어 정보를 저장해야 페이지가 새로고침되어도 유지됩니다.
    st.session_state.player = {
        'slot': choice, 'money': int(p_row.get('money', 0)), 'pos': str(p_row.get('pos', '한양')),
        'inv': json.loads(p_row.get('inventory', '{}')) if p_row.get('inventory') else {},
        'mercs': json.loads(p_row.get('mercs', '[]')) if p_row.get('mercs') else [],
        'year': int(p_row.get('year', 1)), 'month': int(p_row.get('month', 1)), 'week': int(p_row.get('week', 1)),
        'last_tick': time.time(),
        'stats': {'total_bought': 0, 'total_sold': 0, 'total_spent': 0, 'total_earned': 0, 'trade_count': 0}
    }
    st.success(f"{choice}번 슬롯으로 시작합니다!")
        
        # 사용자 입력 (웹용으로 간단히 구현)
        choice = st.number_input("슬롯 번호를 입력하고 Enter를 누르세요", min_value=1, max_value=len(slots), step=1)
        
        p_row = next(s for s in slots if s['slot'] == choice)
        
        player = {
            'slot': choice, 'money': int(p_row.get('money', 0)), 'pos': str(p_row.get('pos', '한양')),
            'inv': json.loads(p_row.get('inventory', '{}')) if p_row.get('inventory') else {},
            'mercs': json.loads(p_row.get('mercs', '[]')) if p_row.get('mercs') else [],
            'year': int(p_row.get('year', 1)), 'month': int(p_row.get('month', 1)), 'week': int(p_row.get('week', 1)),
            'last_tick': time.time(),
            'stats': {'total_bought': 0, 'total_sold': 0, 'total_spent': 0, 'total_earned': 0, 'trade_count': 0}
        }
        return settings, items_info, merc_data, villages, initial_stocks, player
    except Exception as e:
        st.error(f"❌ 데이터 로드 오류: {e}"); sys.exit()

# 글로벌 변수 초기화
SETTINGS, ITEMS_INFO, MERC_DATA, VILLAGES, INITIAL_STOCKS, player = load_all_data()
market_data = {v: {i: {'stock': q, 'price': 0, 'old_price': 0} for i, q in data['items'].items()} for v, data in VILLAGES.items()}

# --- 이후 원본 로직(update_prices, buy, sell 등)이 동일하게 이어집니다 ---
# [사용자님의 원본 main.py 로직을 아래에 그대로 붙여넣으시면 됩니다.]

