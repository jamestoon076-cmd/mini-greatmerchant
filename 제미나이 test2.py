import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime
import hashlib
import uuid
import random

# --- 1. 페이지 설정 및 스타일 (원본 유지) ---
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
    div[data-testid="column"] { gap: 10px; }
    .price-up { color: #ff4b4b; font-weight: bold; }
    .price-down { color: #4b7bff; font-weight: bold; }
    .price-same { color: #808080; }
    .trade-progress {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
        font-family: monospace;
        font-size: 14px;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. 데이터 로드 로직 (스프레드시트 100% 연동) ---
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

def load_game_data():
    doc = connect_gsheet()
    if not doc: return None
    
    # 1) Setting_Data (volatility 등)
    settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
    
    # 2) Item_Data (base_price)
    items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
    
    # 3) Balance_Data (용병)
    mercs = {r['name']: {'price': int(r['price']), 'weight_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
    
    # 4) Village_Data (마을별 시트 재고 로드)
    vil_ws = doc.worksheet("Village_Data")
    vals = vil_ws.get_all_values()
    headers = vals[0]
    villages = {}
    initial_stocks = {} # 시세 기준점 (시트의 초기값)
    
    for row in vals[1:]:
        if not row[0]: continue
        v_name = row[0]
        villages[v_name] = {'x': int(row[1]), 'y': int(row[2]), 'items': {}}
        initial_stocks[v_name] = {}
        for i in range(3, len(headers)):
            item_name = headers[i]
            if item_name and i < len(row) and row[i]:
                try:
                    stock = int(row[i])
                    villages[v_name]['items'][item_name] = stock
                    initial_stocks[v_name][item_name] = stock
                except: continue
                
    player_records = doc.worksheet("Player_Data").get_all_records()
    return doc, settings, items_info, mercs, villages, initial_stocks, player_records

# --- 3. 핵심: 시세 변동 로직 (스프레드시트 재고 기반) ---
def update_prices(settings, items_info, market_data, initial_stocks):
    # 시트의 volatility(5000)를 활용한 민감도 계산
    vol = settings.get('volatility', 5000) / 1000  # 기본값 5.0 수준
    
    for v_name, items in market_data.items():
        if v_name == "용병 고용소": continue
        
        for i_name, i_info in items.items():
            if i_name in items_info:
                base = items_info[i_name]['base']
                curr_s = i_info['stock']
                
                # 모든 마을의 해당 아이템 초기 재고 중 '최대치'를 절대 기준으로 잡음
                # 예: 생선은 부산의 5000이 전 세계의 기준 공급량이 됨
                item_max_init = max([v.get(i_name, 0) for v in initial_stocks.values()])
                if item_max_init == 0: item_max_init = 100
                
                if curr_s <= 0:
                    i_info['price'] = base * 10
                else:
                    # 절대 기준(부산 5000) 대비 현재 재고(평양 200)의 비율
                    # 평양 생선은 5000 / 200 = 25배 희귀함
                    ratio = item_max_init / curr_s
                    
                    # 지수 함수를 사용하여 재고 차이에 따른 가격 격차를 극대화
                    # (ratio가 25이면, 가격은 약 10~20배 폭등)
                    factor = math.pow(ratio, (vol / 5)) 
                    
                    # 하한 0.5배 ~ 상한 30배 제한
                    final_factor = max(0.5, min(30.0, factor))
                    i_info['price'] = int(base * final_factor)

# --- 4. 유틸리티 및 시간 시스템 (원본 유지) ---
def get_time_display(player):
    elapsed = time.time() - player.get('start_time', time.time())
    months = int(elapsed / 30)
    year = 1592 + (months // 12)
    month = (months % 12) + 1
    return f"{year}년 {month}월"

def save_player_data(doc, player, stats, device_id):
    try:
        ws = doc.worksheet("Player_Data")
        inv_json = json.dumps(player['inventory'], ensure_ascii=False)
        mercs_json = json.dumps(player['mercs'], ensure_ascii=False)
        data = [stats['slot'], player['money'], player['pos'], mercs_json, inv_json, datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
        ws.update(f"A{stats['slot']+1}:F{stats['slot']+1}", [data])
        return True
    except: return False

# --- 5. 게임 메인 엔진 ---
data_res = load_game_data()
if data_res:
    doc, settings, items_info, mercenary_data, villages, initial_stocks, player_records = data_res

    if 'game_started' not in st.session_state:
        st.session_state.game_started = False
        st.session_state.device_id = str(uuid.uuid4())[:8]

    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        slot = st.selectbox("저장 슬롯 선택", [1, 2, 3])
        if st.button("게임 시작", use_container_width=True):
            p_rec = player_records[slot-1]
            st.session_state.player = {
                'money': int(p_rec['money']) if p_rec['money'] else 10000,
                'pos': p_rec['pos'] if p_rec['pos'] else "한양",
                'mercs': json.loads(p_rec['mercs']) if p_rec['mercs'] else [],
                'inventory': json.loads(p_rec['inventory']) if p_rec['inventory'] else {},
                'start_time': time.time()
            }
            st.session_state.stats = {'slot': slot}
            # 마켓 데이터 초기화 (시트의 실시간 재고 반영)
            market = {v: {i: {'stock': s, 'price': items_info[i]['base']} 
                      for i, s in info['items'].items()} for v, info in villages.items()}
            st.session_state.market_prices = market
            st.session_state.initial_stocks = initial_stocks
            update_prices(settings, items_info, market, initial_stocks)
            st.session_state.game_started = True
            st.rerun()

    else:
        player = st.session_state.player
        market = st.session_state.market_prices
        curr_pos = player['pos']
        
        # 상단 정보바
        max_w = 200 + sum(mercenary_data.get(m, {}).get('weight_bonus', 0) for m in player['mercs'])
        curr_w = sum(player['inventory'].get(n, 0) * items_info.get(n, {}).get('w', 0) for n in player['inventory'])
        
        st.header(f"📍 {curr_pos}")
        c1, c2 = st.columns(2)
        c1.metric("💰 소지금", f"{player['money']:,}냥")
        c2.metric("📦 무게", f"{curr_w}/{max_w}근")

        tab1, tab2, tab3 = st.tabs(["🛒 장터", "🚩 이동", "👤 내 정보"])

        with tab1:
            if curr_pos == "용병 고용소":
                for m_name, m_info in mercenary_data.items():
                    col1, col2 = st.columns([3, 1])
                    col1.write(f"**{m_name}** (+{m_info['weight_bonus']}근)")
                    if col2.button(f"{m_info['price']:,}냥", key=f"m_{m_name}"):
                        if player['money'] >= m_info['price']:
                            player['money'] -= m_info['price']
                            player['mercs'].append(m_name)
                            st.success(f"{m_name} 고용!")
                            st.rerun()
            else:
                for i_name, i_data in market[curr_pos].items():
                    col1, col2, col3 = st.columns([2, 1, 1])
                    col1.write(f"**{i_name}** ({i_data['stock']}개)")
                    col2.write(f"{i_data['price']:,}냥")
                    if col3.button("거래", key=f"t_{i_name}"):
                        st.session_state.trade_target = i_name

                if 'trade_target' in st.session_state:
                    t_item = st.session_state.trade_target
                    st.divider()
                    amt = st.number_input(f"{t_item} 수량", 1, 10000, 1)
                    cc1, cc2 = st.columns(2)
                    if cc1.button("매수", use_container_width=True):
                        cost = market[curr_pos][t_item]['price'] * amt
                        weight = items_info[t_item]['w'] * amt
                        if player['money'] >= cost and market[curr_pos][t_item]['stock'] >= amt and curr_w + weight <= max_w:
                            player['money'] -= cost
                            player['inventory'][t_item] = player['inventory'].get(t_item, 0) + amt
                            market[curr_pos][t_item]['stock'] -= amt
                            update_prices(settings, items_info, market, st.session_state.initial_stocks)
                            st.success("매수 완료")
                            st.rerun()
                    if cc2.button("매도", use_container_width=True):
                        if player['inventory'].get(t_item, 0) >= amt:
                            player['money'] += market[curr_pos][t_item]['price'] * amt
                            player['inventory'][t_item] -= amt
                            market[curr_pos][t_item]['stock'] += amt
                            update_prices(settings, items_info, market, st.session_state.initial_stocks)
                            st.success("매도 완료")
                            st.rerun()

        with tab2:
            for dest, d_info in villages.items():
                if dest != curr_pos:
                    dist = math.sqrt((villages[curr_pos]['x']-d_info['x'])**2 + (villages[curr_pos]['y']-d_info['y'])**2)
                    cost = int(dist * settings['travel_cost'])
                    if st.button(f"{dest} 이동 ({cost}냥)"):
                        if player['money'] >= cost:
                            player['money'] -= cost
                            player['pos'] = dest
                            st.rerun()

        with tab3:
            st.write(f"⏰ 현재 시간: {get_time_display(player)}")
            st.write(f"🎒 인벤토리:")
            for k, v in player['inventory'].items():
                if v > 0: st.write(f"- {k}: {v}개")
            if st.button("💾 저장", use_container_width=True):
                save_player_data(doc, player, st.session_state.stats, st.session_state.device_id)
                st.success("저장 완료")
            if st.button("🚪 메인으로", use_container_width=True):
                st.session_state.game_started = False
                st.rerun()
