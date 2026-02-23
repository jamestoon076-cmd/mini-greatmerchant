import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 페이지 설정 및 디자인 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

st.markdown("""
<style>
    .info-box { background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #4b7bff; margin-bottom: 20px; }
    .stButton button { width: 100%; margin: 3px 0; font-weight: bold; }
    .slot-card { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e1e4e8; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# --- 2. 데이터 연동 (캐싱 및 안정화) ---
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
        
        # 국가별 마을 자동 로드 및 전세계 최대 재고량 파악
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
                            try: val = int(stock); item_max_stocks[item] = max(item_max_stocks[item], val)
                            except: pass
        
        player_slots = doc.worksheet("Player_Data").get_all_records()
        return doc, settings, items_info, mercs_data, regions, item_max_stocks, player_slots
    except Exception as e:
        st.error(f"데이터 연동 실패: {e}"); return None

# --- 3. 가격 및 시간 로직 ---
def calculate_price(item_name, stock, item_max_stocks, items_info, settings):
    base = items_info[item_name]['base']
    max_s = item_max_stocks.get(item_name, 100)
    vol = settings.get('volatility', 5000) / 1000
    try:
        curr_s = int(stock)
        if curr_s <= 0: return base * 5
        ratio = max_s / curr_s
        factor = math.pow(ratio, (vol / 4))
        return int(base * max(0.5, min(25.0, factor)))
    except: return base

def get_game_time(start_time):
    # 30초 = 1달 (사용자 기획 반영)
    elapsed = time.time() - start_time
    months_passed = int(elapsed // 30)
    year = 1592 + (months_passed // 12)
    month = (months_passed % 12) + 1
    return f"{year}년 {month}월"

# --- 4. 메인 게임 실행 ---
res = load_game_data()
if res:
    doc, settings, items_info, mercs_data, regions, item_max_stocks, player_slots = res

    if 'game_started' not in st.session_state: st.session_state.game_started = False

    # [화면 1: 슬롯 선택]
    if not st.session_state.game_started:
        st.title("🏯 거상: 대륙의 시작")
        for i, p in enumerate(player_slots):
            slot_id = i + 1
            with st.container():
                st.markdown(f"""<div class="slot-card"><b>💾 슬롯 {slot_id}</b><br>
                📍 위치: {p.get('pos','한양')} | 💰 소지금: {int(p.get('money',0)):,}냥<br>
                🕒 마지막 저장: {p.get('last_save','없음')}</div>""", unsafe_allow_html=True)
                if st.button(f"슬롯 {slot_id} 접속", key=f"btn_{slot_id}"):
                    # 안전한 JSON 로드 (KeyError 방지)
                    try: inv = json.loads(p['inventory']) if p.get('inventory') else {}
                    except: inv = {}
                    try: mrc = json.loads(p['mercs']) if p.get('mercs') else []
                    except: mrc = []
                    
                    st.session_state.player = {
                        'money': int(p.get('money', 10000)), 'pos': p.get('pos', '한양'),
                        'inventory': inv, 'mercs': mrc, 'start_time': time.time()
                    }
                    st.session_state.slot_num = slot_id
                    st.session_state.game_started = True; st.rerun()

    # [화면 2: 게임 플레이]
    else:
        player = st.session_state.player
        
        # 상단 정보 계산 (무게 등)
        max_w = 200 + sum([mercs_data.get(m, {}).get('weight_bonus', 0) for m in player['mercs']])
        curr_w = sum([items_info.get(it, {}).get('w', 0) * qty for it, qty in player['inventory'].items()])

        # 상단 UI (소지금, 무게, 시간 통합)
        st.markdown(f"""
        <div class="info-box">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>📍 <b>{player['pos']}</b> | 💰 <b>{player['money']:,}냥</b></div>
                <div style="text-align: right;">📦 {curr_w}/{max_w}근<br>⏰ {get_game_time(player['start_time'])}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        tab1, tab2, tab3 = st.tabs(["🛒 저잣거리", "🚩 팔도 이동", "💾 저장/종료"])

        with tab1: # 장터 (volatility 시세 반영)
            v_data = next((v for r in regions.values() for v in r if v['village_name'] == player['pos']), None)
            if v_data:
                for item_name, info in items_info.items():
                    stock = v_data.get(item_name, 0)
                    price = calculate_price(item_name, stock, item_max_stocks, items_info, settings)
                    
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"**{item_name}** ({stock}개)")
                    c2.write(f"{price:,}냥")
                    if c3.button("거래", key=f"tr_{item_name}"):
                        st.session_state.active_item = {'name': item_name, 'price': price, 'weight': info['w']}
                
                if 'active_item' in st.session_state:
                    at = st.session_state.active_item
                    st.divider()
                    amt = st.number_input(f"{at['name']} 거래 수량", 1, 100000, 1)
                    
                    col_b, col_s = st.columns(2)
                    if col_b.button("매수"):
                        cost, wght = at['price'] * amt, at['weight'] * amt
                        if player['money'] >= cost and curr_w + wght <= max_w:
                            player['money'] -= cost
                            player['inventory'][at['name']] = player['inventory'].get(at['name'], 0) + amt
                            st.rerun()
                        else: st.error("자금 부족 또는 무게 초과!")
                    if col_s.button("매도"):
                        if player['inventory'].get(at['name'], 0) >= amt:
                            player['money'] += at['price'] * amt
                            player['inventory'][at['name']] -= amt
                            st.rerun()
                        else: st.error("보유 수량 부족!")

        with tab2: # 이동 (국가별 탭 자동 생성)
            country_tabs = st.tabs(list(regions.keys()))
            for i, country in enumerate(regions.keys()):
                with country_tabs[i]:
                    with st.container(height=350):
                        for v in regions[country]:
                            if v['village_name'] == player['pos']: continue
                            col_v, col_m = st.columns([3, 1])
                            col_v.write(f"**{v['village_name']}**")
                            if col_m.button("이동", key=f"mv_{country}_{v['village_name']}"):
                                player['pos'] = v['village_name']; st.rerun()

        with tab3: # 저장 및 메인으로
            if st.button("💾 게임 저장"):
                ws = doc.worksheet("Player_Data")
                r_idx = st.session_state.slot_num + 1
                save_row = [st.session_state.slot_num, player['money'], player['pos'], 
                            json.dumps(player['mercs'], ensure_ascii=False), 
                            json.dumps(player['inventory'], ensure_ascii=False), 
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{r_idx}:F{r_idx}", [save_row])
                st.success("저장 완료!")
            if st.button("🚪 메인 화면으로"):
                st.session_state.game_started = False; st.rerun()
