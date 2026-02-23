import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
from datetime import datetime

# --- 1. 페이지 설정 및 디자인 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

st.markdown("""
<style>
    .slot-container { background-color: #ffffff; padding: 20px; border-radius: 15px; border: 1px solid #e1e4e8; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .stButton button { width: 100%; font-weight: bold; }
    .trade-container { background-color: #f8f9fa; padding: 15px; border-radius: 10px; margin-top: 10px; border: 1px solid #dee2e6; }
</style>
""", unsafe_allow_html=True)

# --- 2. 데이터 연동 ---
@st.cache_resource
def get_gsheet_client():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("조선거상_DB")
    except: return None

def load_all_data():
    doc = get_gsheet_client()
    if not doc: return None
    try:
        # 설정, 아이템, 용병 로드
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
        items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        mercs_data = {r['name']: {'price': int(r['price']), 'weight_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
        
        # 국가별 마을 동적 로드 (시트가 없어도 에러 안 남)
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
                            # 숫자 변환 에러 방지
                            try: val = int(stock)
                            except: val = 0
                            item_max_stocks[item] = max(item_max_stocks[item], val)
        
        player_slots = doc.worksheet("Player_Data").get_all_records()
        return doc, settings, items_info, mercs_data, regions, item_max_stocks, player_slots
    except Exception as e:
        st.error(f"데이터 로딩 오류: {e}")
        return None

# --- 3. 가격 계산 함수 ---
def calculate_price(item_name, stock, item_max_stocks, items_info, settings):
    base = items_info[item_name]['base']
    max_s = item_max_stocks.get(item_name, 100)
    vol = settings.get('volatility', 5000) / 1000
    curr_s = int(stock) if str(stock).isdigit() and int(stock) > 0 else 0
    
    if curr_s <= 0: return base * 5
    ratio = max_s / curr_s
    factor = math.pow(ratio, (vol / 4))
    return int(base * max(0.5, min(20.0, factor)))

# --- 4. 메인 실행 ---
data = load_all_data()
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
                📍 현재 위치: {p.get('pos','한양')} | 💰 소지금: {int(p.get('money',0)):,}냥<br>
                🕒 마지막 저장: {p.get('last_save','기록 없음')}</div>""", unsafe_allow_html=True)
                if st.button(f"슬롯 {slot_id} 접속", key=f"slot_{slot_id}"):
                    st.session_state.player = {
                        'money': int(p.get('money', 10000)),
                        'pos': p.get('pos', '한양'),
                        'inventory': json.loads(p['inventory']) if p.get('inventory') else {},
                        'mercs': json.loads(p['mercs']) if p.get('mercs') else []
                    }
                    st.session_state.slot_num = slot_id
                    st.session_state.game_started = True
                    st.rerun()

    # [화면 2: 인게임]
    else:
        player = st.session_state.player
        st.header(f"📍 현재 위치: {player['pos']}")
        st.subheader(f"💰 소지금: {player['money']:,}냥")

        tab1, tab2, tab3 = st.tabs(["🛒 저잣거리", "🚩 이동", "👤 상단 정보"])

        with tab1: # 장터
            # 현재 마을 데이터 찾기
            v_data = None
            for r_rows in regions.values():
                for v in r_rows:
                    if v['village_name'] == player['pos']:
                        v_data = v; break
            
            if v_data:
                for item_name in items_info.keys():
                    stock = v_data.get(item_name, 0)
                    price = calculate_price(item_name, stock, item_max_stocks, items_info, settings)
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"**{item_name}** ({stock}개)")
                    c2.write(f"{price:,}냥")
                    if c3.button("거래", key=f"trade_{item_name}"):
                        st.session_state.active_trade = {'name': item_name, 'price': price}
                
                if 'active_trade' in st.session_state:
                    with st.container(border=True):
                        at = st.session_state.active_trade
                        st.write(f"### {at['name']} 거래")
                        amt = st.number_input("수량", 1, 10000, 1)
                        b_col, s_col = st.columns(2)
                        if b_col.button("매수"):
                            if player['money'] >= at['price'] * amt:
                                player['money'] -= at['price'] * amt
                                player['inventory'][at['name']] = player['inventory'].get(at['name'], 0) + amt
                                st.rerun()
                        if s_col.button("매도"):
                            if player['inventory'].get(at['name'], 0) >= amt:
                                player['money'] += at['price'] * amt
                                player['inventory'][at['name']] -= amt
                                st.rerun()

        with tab2: # 이동
            # 국가별 탭 자동 생성
            countries = list(regions.keys())
            if countries:
                selected_tabs = st.tabs(countries)
                for idx, country in enumerate(countries):
                    with selected_tabs[idx]:
                        with st.container(height=350):
                            for v in regions[country]:
                                if v['village_name'] == player['pos']: continue
                                col_v, col_b = st.columns([3, 1])
                                col_v.write(f"**{v['village_name']}**")
                                if col_b.button("이동", key=f"mv_{country}_{v['village_name']}"):
                                    player['pos'] = v['village_name']
                                    st.rerun()

        with tab3: # 정보 및 저장
            st.write(f"🎒 인벤토리: {player['inventory']}")
            if st.button("💾 데이터 저장"):
                ws = doc.worksheet("Player_Data")
                r_idx = st.session_state.slot_num + 1
                save_data = [st.session_state.slot_num, player['money'], player['pos'], 
                             json.dumps(player['mercs'], ensure_ascii=False), 
                             json.dumps(player['inventory'], ensure_ascii=False), 
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{r_idx}:F{r_idx}", [save_data])
                st.success("저장되었습니다!")
