import streamlit as st
from streamlit_autorefresh import st_autorefresh
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime
import hashlib
import uuid
import random

# --- 1. 페이지 설정 및 스타일 ---
st.set_page_config(
    page_title="조선거상 미니",
    page_icon="🏯",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .stButton button { width: 100%; margin: 5px 0; padding: 15px; font-size: 18px; }
    .stTextInput input { font-size: 16px; padding: 10px; }
    .price-up { color: #ff4b4b; font-weight: bold; }
    .price-down { color: #4b7bff; font-weight: bold; }
    .trade-progress {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
        font-family: monospace;
        font-size: 14px;
        max-height: 200px;
        overflow-y: auto;
    }
    .trade-line { padding: 3px 0; border-bottom: 1px solid #e0e0e0; }
</style>
""", unsafe_allow_html=True)

# --- 2. 구글 시트 연결 및 데이터 로드 ---
@st.cache_resource
def connect_gsheet():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gspread"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"❌ 시트 연결 에러: {e}")
        return None

@st.cache_data(ttl=10)
def load_game_data():
    doc = connect_gsheet()
    if not doc: return None, None, None, None, None, None
    try:
        set_ws = doc.worksheet("Setting_Data")
        settings = {r['변수명']: float(r['값']) for r in set_ws.get_all_records()}
        item_ws = doc.worksheet("Item_Data")
        items_info = {str(r['item_name']).strip(): {'base': int(r['base_price']), 'w': int(r['weight'])} for r in item_ws.get_all_records() if r.get('item_name')}
        bal_ws = doc.worksheet("Balance_Data")
        merc_data = {str(r['name']).strip(): {'price': int(r['price']), 'w_bonus': int(r.get('weight_bonus', 0))} for r in bal_ws.get_all_records() if r.get('name')}
        vil_ws = doc.worksheet("Village_Data")
        vil_vals = vil_ws.get_all_values()
        headers = [h.strip() for h in vil_vals[0]]
        villages, initial_stocks = {}, {}
        for row in vil_vals[1:]:
            if not row or not row[0].strip(): continue
            v_name = row[0].strip()
            x, y = int(row[1]) if len(row)>1 and row[1] else 0, int(row[2]) if len(row)>2 and row[2] else 0
            villages[v_name] = {'items': {}, 'x': x, 'y': y}
            initial_stocks[v_name] = {}
            if v_name != "용병 고용소":
                for i in range(3, len(headers)):
                    if headers[i] in items_info and len(row) > i and row[i].strip():
                        villages[v_name]['items'][headers[i]] = int(row[i])
                        initial_stocks[v_name][headers[i]] = int(row[i])
        play_ws = doc.worksheet("Player_Data")
        slots = []
        for r in play_ws.get_all_records():
            if str(r.get('slot', '')).strip():
                slots.append({
                    'slot': int(r['slot']), 'money': int(r.get('money', 0)), 'pos': str(r.get('pos', '한양')),
                    'inv': json.loads(r.get('inventory', '{}')) if r.get('inventory') else {},
                    'mercs': json.loads(r.get('mercs', '[]')) if r.get('mercs') else [],
                    'week': int(r.get('week', 1)), 'month': int(r.get('month', 1)), 'year': int(r.get('year', 1592))
                })
        return settings, items_info, merc_data, villages, initial_stocks, slots
    except Exception as e:
        st.error(f"❌ 로드 에러: {e}"); return None, None, None, None, None, None

# --- 3. 세션 초기화 (파일 상단에 위치해야 함) ---
def init_session_state():
    if 'game_started' not in st.session_state: st.session_state.game_started = False
    if 'player' not in st.session_state: st.session_state.player = None
    if 'tab_key' not in st.session_state: st.session_state.tab_key = 0 # 탭 초기화용 키
    if 'is_trading' not in st.session_state: st.session_state.is_trading = False # 매매 중 플래그
    if 'trade_logs' not in st.session_state: st.session_state.trade_logs = []
    # ... 기존의 다른 세션 초기화 코드들 ...

# --- 4. 매매 통합 함수 (무게/돈 한도까지 자동 반복) ---
def process_trade(mode, player, items_info, market_data, pos, item_name, target_qty):
    st.session_state.is_trading = True  # 시계 정지용 플래그 ON
    total_qty = 0
    total_cost = 0
    batch_size = 100 # 100개씩 끊어서 처리
    
    placeholder = st.empty() # 실시간 로그 출력용
    
    while total_qty < target_qty:
        # 1. 시세 재계산 (재고 변동 반영)
        update_prices(st.session_state.settings, items_info, market_data)
        current_price = market_data[pos][item_name]['price']
        
        # 2. 현재 무게 상태 확인
        curr_w, max_w = get_weight(player, items_info, st.session_state.merc_data)
        item_w = items_info[item_name]['w']
        
        if mode == "BUY":
            can_buy_money = player['money'] // current_price if current_price > 0 else 0
            can_buy_weight = (max_w - curr_w) // item_w if item_w > 0 else 99999
            # 이번 턴에 살 수 있는 최대치 계산
            current_batch = min(batch_size, target_qty - total_qty, 
                                market_data[pos][item_name]['stock'], 
                                can_buy_money, can_buy_weight)
        else: # SELL
            current_batch = min(batch_size, target_qty - total_qty, player['inv'].get(item_name, 0))

        if current_batch <= 0:
            break # 더 이상 살 수 없거나 팔 게 없으면 종료
            
        # 3. 데이터 반영
        cost = current_batch * current_price
        if mode == "BUY":
            player['money'] -= cost
            player['inv'][item_name] = player['inv'].get(item_name, 0) + current_batch
            market_data[pos][item_name]['stock'] -= current_batch
        else:
            player['money'] += cost
            player['inv'][item_name] -= current_batch
            market_data[pos][item_name]['stock'] += current_batch
            
        total_qty += current_batch
        total_cost += cost
        
        # 실시간 UI 업데이트 (선택 사항)
        placeholder.caption(f"🔄 체결 진행 중: {total_qty}개 완료...")
        time.sleep(0.01) # 아주 짧은 대기 (애니메이션 효과)

    placeholder.empty()
    st.session_state.is_trading = False # 시계 정지용 플래그 OFF
    return total_qty, total_cost

# --- 메인 루프 내부 ---
init_session_state() # 프로그램 시작 시 가장 먼저 실행

if st.session_state.game_started:
    # ... (데이터 로드 부분) ...
    
    # 에러 방지: tab_key가 세션에 없는 경우를 대비한 안전장치
    if 'tab_key' not in st.session_state:
        st.session_state.tab_key = 0
        
    # 1. 탭 생성 (고유 키 부여)
    tabs = st.tabs(["🛒 저잣거리", "📦 인벤토리", "⚔️ 용병", "⚙️ 메뉴"], key=f"tab_{st.session_state.tab_key}")
    
    with tabs[0]: # 저잣거리
        # 매수/매도 버튼 클릭 시 process_trade 호출
        # 예: q, c = process_trade("BUY", player, items_info, market_data, player['pos'], item_name, input_qty)
        pass
        
    with tabs[3]: # 메뉴 (이동)
        st.subheader("🚚 도시 이동")
        # ... 이동 대상 선택 코드 ...
        if st.button("도시 이동 실행"):
            # ... 이동 비용 계산 및 위치 변경 코드 ...
            
            # [수정포인트] 이동 시 로그 삭제 및 탭 초기화
            if 'last_trade_result' in st.session_state:
                del st.session_state['last_trade_result']
            
            st.session_state.tab_key += 1 # 이 값을 바꿔서 탭을 0번으로 돌림
            st.rerun()
