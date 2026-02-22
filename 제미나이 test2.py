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

# --- 2. 시트 연결 ---
def connect_gsheet():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gspread"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"❌ 연결 실패: {e}. 스트림릿 Secrets 설정을 확인하세요!")
        sys.exit()

doc = connect_gsheet()

# --- 3. 데이터 로드 함수 ---
def load_all_data():
    try:
        # 설정 및 아이템 데이터 로드
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
        
        # 슬롯 데이터 로드
        play_ws = doc.worksheet("Player_Data")
        slots = play_ws.get_all_records()
        
        return settings, items_info, merc_data, villages, initial_stocks, slots
    except Exception as e:
        st.error(f"❌ 데이터 로드 오류: {e}")
        sys.exit()

# --- 4. 실행 로직 ---
# 데이터를 먼저 불러옵니다.
SETTINGS, ITEMS_INFO, MERC_DATA, VILLAGES, INITIAL_STOCKS, SLOTS = load_all_data()

st.title("🏯 조선거상 미니 게임")

# 세이브 슬롯 선택 화면
if 'player' not in st.session_state:
    st.write("### 💾 세이브 슬롯 선택")
    for s in SLOTS:
        st.write(f"[{s['slot']}] 위치: {s['pos']} | 잔액: {int(s.get('money', 0)):,}냥")
    
    choice = st.number_input("슬롯 번호를 선택하세요", min_value=1, max_value=len(SLOTS), step=1)
    
    if st.button("🎮 게임 시작하기"):
        p_row = next(s for s in SLOTS if s['slot'] == choice)
        st.session_state.player = {
            'slot': choice, 'money': int(p_row.get('money', 0)), 'pos': str(p_row.get('pos', '한양')),
            'inv': json.loads(p_row.get('inventory', '{}')) if p_row.get('inventory') else {},
            'mercs': json.loads(p_row.get('mercs', '[]')) if p_row.get('mercs') else [],
            'year': int(p_row.get('year', 1)), 'month': int(p_row.get('month', 1)), 'week': int(p_row.get('week', 1)),
            'last_tick': time.time(),
            'stats': {'total_bought': 0, 'total_sold': 0, 'total_spent': 0, 'total_earned': 0, 'trade_count': 0}
        }
        st.rerun() # 화면 새로고침해서 게임 본문으로 진입
else:
    # 플레이어가 선택된 이후 게임 로직 시작
    player = st.session_state.player
    st.write(f"📍 현재 위치: **{player['pos']}** | 💰 잔액: **{player['money']:,}냥**")
    # 여기에 나머지 게임 함수들(buy, sell 등)을 붙여넣으세요.
