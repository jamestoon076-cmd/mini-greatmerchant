import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 페이지 설정 및 스타일 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

st.markdown("""
<style>
    /* 마을 이동 리스트를 위한 스크롤 박스 스타일 */
    .scroll-container {
        max-height: 400px;
        overflow-y: auto;
        padding: 10px;
        border: 1px solid #ddd;
        border-radius: 10px;
        background-color: #f9f9f9;
    }
    .stButton button { width: 100%; margin: 5px 0; padding: 12px; font-size: 16px; }
</style>
""", unsafe_allow_html=True)

# --- 2. 데이터 연동 로직 ---
@st.cache_resource
def connect_gsheet():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
                                                     ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("조선거상_DB")
    except: return None

def load_game_data():
    doc = connect_gsheet()
    if not doc: return None
    
    # 시트 데이터 읽기
    settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
    items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
    mercs_data = {r['name']: {'price': int(r['price']), 'weight_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
    
    # 마을 및 재고 (도시 자동 리스트화)
    vil_ws = doc.worksheet("Village_Data")
    vals = vil_ws.get_all_values()
    headers = vals[0]
    villages = {}
    item_max_stocks = {name: 0 for name in items_info.keys()}
    
    for row in vals[1:]:
        if not row[0]: continue
        v_name = row[0]
        villages[v_name] = {'x': int(row[1]), 'y': int(row[2]), 'items': {}}
        for i in range(3, len(headers)):
            item_name = headers[i]
            if item_name in items_info and i < len(row) and row[i]:
                stock = int(row[i])
                villages[v_name]['items'][item_name] = stock
                if stock > item_max_stocks[item_name]: item_max_stocks[item_name] = stock
                
    player_recs = doc.worksheet("Player_Data").get_all_records()
    return doc, settings, items_info, mercs_data, villages, item_max_stocks, player_recs

# --- 3. 시세 로직 (상대적 희소성 적용) ---
def update_market_prices(settings, items_info, market_data, item_max_stocks):
    vol = settings.get('volatility', 5000) / 1000 
    for v_name, items in market_data.items():
        if v_name == "용병 고용소": continue
        for i_name, i_info in items.items():
            if i_name in items_info:
                base = items_info[i_name]['base']
                curr_s = i_info['stock']
                max_s = item_max_stocks.get(i_name, 100)
                if curr_s <= 0: i_info['price'] = base * 10
                else:
                    # 예: 평양 생선(200) vs 부산 생선(5000) -> 25배 차이 반영
                    ratio = max_s / curr_s 
                    factor = math.pow(ratio, (vol / 4)) 
                    i_info['price'] = int(base * max(0.5, min(20.0, factor)))

# --- 4. 메인 루프 ---
res = load_game_data()
if res:
    doc, settings, items_info, mercs_data, villages, item_max_stocks, player_records = res

    if 'game_started' not in st.session_state: st.session_state.game_started = False

    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        slot = st.selectbox("슬롯 선택", [1, 2, 3])
        if st.button("게임 시작"):
            p_rec = player_records[slot-1]
            st.session_state.player = {
                'money': int(p_rec['money']) if p_rec['money'] else 10000,
                'pos': p_rec['pos'] if p_rec['pos'] else "한양",
                'mercs': json.loads(p_rec['mercs']) if p_rec['mercs'] else [],
                'inventory': json.loads(p_rec['inventory']) if p_rec['inventory'] else {},
                'start_time': time.time()
            }
            st.session_state.stats = {'slot': slot}
            market = {v: {i: {'stock': s, 'price': items_info[i]['base']} for i, s in info['items'].items()} for v, info in villages.items()}
            st.session_state.market_prices = market
            update_market_prices(settings, items_info, market, item_max_stocks)
            st.session_state.game_started = True
            st.rerun()
    else:
        player = st.session_state.player
        market = st.session_state.market_prices
        curr_pos = player['pos']
        
        st.header(f"📍 {curr_pos}")
        st.metric("💰 소지금", f"{player['money']:,}냥")

        tab1, tab2, tab3 = st.tabs(["🛒 장터", "🚩 이동", "👤 정보"])

        with tab1:
            if curr_pos != "용병 고용소":
                for i_name, i_data in market[curr_pos].items():
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"**{i_name}** ({i_data['stock']})")
                    c2.write(f"{i_data['price']:,}냥")
                    if c3.button("선택", key=f"t_{i_name}"): st.session_state.target = i_name
                
                if 'target' in st.session_state:
                    t = st.session_state.target
                    amt = st.number_input(f"{t} 수량", 1, 1000, 1)
                    if st.button("매수"):
                        cost = market[curr_pos][t]['price'] * amt
                        if player['money'] >= cost:
                            player['money'] -= cost
                            player['inventory'][t] = player['inventory'].get(t, 0) + amt
                            market[curr_pos][t]['stock'] -= amt
                            update_market_prices(settings, items_info, market, item_max_stocks)
                            st.rerun()

        with tab2:
            st.subheader("🚩 이동할 마을 선택")
            # 💡 [핵심] 마을이 몇 개든 스크롤 박스 안에 버튼으로 자동 생성
            with st.container(border=True):
                # 도시가 많아질 것에 대비해 내부를 스크롤 가능하게 구성
                dests = [n for n in villages.keys() if n != curr_pos]
                
                for dest in dests:
                    d_info = villages[dest]
                    dist = math.sqrt((villages[curr_pos]['x']-d_info['x'])**2 + (villages[curr_pos]['y']-d_info['y'])**2)
                    cost = int(dist * settings.get('travel_cost', 15))
                    
                    if st.button(f"🏯 {dest} 이동 ({cost}냥 / {int(dist)}리)", key=f"m_btn_{dest}"):
                        if player['money'] >= cost:
                            player['money'] -= cost
                            player['pos'] = dest
                            st.success(f"{dest}로 이동 완료!")
                            st.rerun()

        with tab3:
            st.write(f"🎒 소지품: {player['inventory']}")
            if st.button("💾 저장", key="save_btn"):
                ws = doc.worksheet("Player_Data")
                data = [st.session_state.stats['slot'], player['money'], player['pos'], json.dumps(player['mercs'], ensure_ascii=False), json.dumps(player['inventory'], ensure_ascii=False), datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{st.session_state.stats['slot']+1}:F{st.session_state.stats['slot']+1}", [data])
                st.success("저장되었습니다.")
