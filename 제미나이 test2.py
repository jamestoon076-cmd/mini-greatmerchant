import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
from datetime import datetime

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

st.markdown("""
<style>
    .slot-container { background-color: #ffffff; padding: 20px; border-radius: 15px; border: 1px solid #e1e4e8; margin-bottom: 15px; }
    .trade-row { padding: 10px; border-bottom: 1px solid #eee; display: flex; align-items: center; justify-content: space-between; }
    .stButton button { width: 100%; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 2. 데이터 연동 (최적화) ---
@st.cache_resource
def get_gsheet_client():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("조선거상_DB")
    except: return None

def load_game_data():
    doc = get_gsheet_client()
    if not doc: return None
    try:
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
        items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        mercs_data = {r['name']: {'price': int(r['price']), 'weight_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
        
        regions = {}
        item_max_stocks = {name: 0 for name in items_info.keys()}
        for ws in doc.worksheets():
            if "_Village_Data" in ws.title:
                country = ws.title.replace("_Village_Data", "")
                rows = ws.get_all_records()
                regions[country] = rows
                for row in rows:
                    for item, stock in row.items():
                        if item in item_max_stocks:
                            item_max_stocks[item] = max(item_max_stocks[item], int(stock or 0))
        
        player_slots = doc.worksheet("Player_Data").get_all_records()
        return doc, settings, items_info, mercs_data, regions, item_max_stocks, player_slots
    except Exception as e:
        st.error(f"데이터 로딩 중 오류 발생: {e}")
        return None

# --- 3. 시세 계산 로직 ---
def get_price(item_name, current_stock, item_max_stocks, items_info, settings):
    base = items_info[item_name]['base']
    max_s = item_max_stocks.get(item_name, 100)
    vol = settings.get('volatility', 5000) / 1000
    if current_stock <= 0: return base * 5
    ratio = max_s / current_stock
    factor = math.pow(ratio, (vol / 4))
    return int(base * max(0.5, min(20.0, factor)))

# --- 4. 메인 엔진 ---
data = load_game_data()
if data:
    doc, settings, items_info, mercs_data, regions, item_max_stocks, player_slots = data

    if 'game_started' not in st.session_state: st.session_state.game_started = False

    # [화면 1: 슬롯 선택]
    if not st.session_state.game_started:
        st.title("🏯 거상: 대륙의 시작")
        for i, p in enumerate(player_slots):
            slot_id = i + 1
            with st.container():
                st.markdown(f"""<div class="slot-container"><b>💾 슬롯 {slot_id}</b><br>
                📍 위치: {p.get('pos','한양')} | 💰 소지금: {int(p.get('money',0)):,}냥<br>
                🕒 마지막 저장: {p.get('last_save','기록 없음')}</div>""", unsafe_allow_html=True)
                if st.button(f"슬롯 {slot_id} 접속", key=f"slot_{slot_id}"):
                    st.session_state.player = {'money': int(p['money']), 'pos': p['pos'], 
                                               'inventory': json.loads(p['inventory']), 'mercs': json.loads(p['mercs'])}
                    st.session_state.slot_num = slot_id
                    st.session_state.game_started = True
                    st.rerun()

    # [화면 2: 인게임]
    else:
        player = st.session_state.player
        st.header(f"📍 {player['pos']}")
        st.subheader(f"💰 {player['money']:,}냥")

        tab_market, tab_move, tab_info = st.tabs(["🛒 저잣거리", "🚩 이동", "👤 정보"])

        with tab_market:
            # 현재 마을의 재고 찾기
            village_data = None
            for r_data in regions.values():
                for v in r_data:
                    if v['village_name'] == player['pos']:
                        village_data = v
                        break
            
            if village_data:
                for item_name in items_info.keys():
                    stock = village_data.get(item_name, 0)
                    price = get_price(item_name, stock, item_max_stocks, items_info, settings)
                    
                    col1, col2, col3 = st.columns([2, 1, 1])
                    col1.write(f"**{item_name}** ({stock}개)")
                    col2.write(f"{price:,}냥")
                    if col3.button("거래", key=f"tr_{item_name}"):
                        st.session_state.active_item = {'name': item_name, 'price': price}
                
                if 'active_item' in st.session_state:
                    st.divider()
                    it = st.session_state.active_item
                    amt = st.number_input(f"{it['name']} 거래 수량", 1, 1000, 1)
                    c1, c2 = st.columns(2)
                    if c1.button("매수"):
                        if player['money'] >= it['price'] * amt:
                            player['money'] -= it['price'] * amt
                            player['inventory'][it['name']] = player['inventory'].get(it['name'], 0) + amt
                            st.rerun()
                    if c2.button("매도"):
                        if player['inventory'].get(it['name'], 0) >= amt:
                            player['money'] += it['price'] * amt
                            player['inventory'][it['name']] -= amt
                            st.rerun()

        with tab_move: # 국가별 탭 스크롤 이동 시스템
            country_list = list(regions.keys())
            selected_tabs = st.tabs(country_list)
            for i, country in enumerate(country_list):
                with selected_tabs[i]:
                    with st.container(height=300):
                        for v in regions[country]:
                            if v['village_name'] == player['pos']: continue
                            if st.button(f"🏯 {v['village_name']} 이동", key=f"mv_{v['village_name']}"):
                                player['pos'] = v['village_name']
                                st.rerun()

        with tab_info:
            if st.button("💾 저장"):
                ws = doc.worksheet("Player_Data")
                row = st.session_state.slot_num + 1
                save_data = [st.session_state.slot_num, player['money'], player['pos'], 
                             json.dumps(player['mercs'], ensure_ascii=False), 
                             json.dumps(player['inventory'], ensure_ascii=False), 
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{row}:F{row}", [save_data])
                st.success("저장 완료!")
