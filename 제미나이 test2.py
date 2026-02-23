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
    .stButton button { width: 100%; margin: 2px 0; padding: 12px; font-size: 16px; }
    .slot-card { background-color: #f8f9fa; padding: 15px; border-radius: 10px; border: 1px solid #dee2e6; margin-bottom: 10px; }
    .info-box { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e1e4e8; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
</style>
""", unsafe_allow_html=True)

# --- 2. 데이터 연동 (캐싱) ---
@st.cache_resource
def connect_gsheet():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("조선거상_DB")
    except: return None

def load_game_data():
    doc = connect_gsheet()
    if not doc: return None
    try:
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
        items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        mercs_data = {r['name']: {'price': int(r['price']), 'weight_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
        
        # 국가별 마을 데이터 자동 로드 및 최대 재고 파악
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
        
        player_recs = doc.worksheet("Player_Data").get_all_records()
        return doc, settings, items_info, mercs_data, regions, item_max_stocks, player_recs
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}"); return None

# --- 3. 핵심 유틸리티 (시간, 시세) ---
def get_time_display(start_time):
    elapsed = time.time() - start_time
    months_passed = int(elapsed // 30) # 30초 = 1달
    year = 1592 + (months_passed // 12)
    month = (months_passed % 12) + 1
    return f"{year}년 {month}월"

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

# --- 4. 메인 엔진 ---
res = load_game_data()
if res:
    doc, settings, items_info, mercs_data, regions, item_max_stocks, player_recs = res

    if 'game_started' not in st.session_state: st.session_state.game_started = False

    # [초기 화면: 슬롯 정보]
    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        for i, p in enumerate(player_recs):
            slot_id = i + 1
            with st.container():
                st.markdown(f"""<div class='slot-card'><b>💾 슬롯 {slot_id}</b><br>
                📍 위치: {p.get('pos','정보없음')} | 💰 소지금: {int(p.get('money',0)):,}냥<br>
                🕒 저장: {p.get('last_save','-')}</div>""", unsafe_allow_html=True)
                if st.button(f"슬롯 {slot_id} 시작", key=f"slot_{slot_id}"):
                    st.session_state.player = {
                        'money': int(p['money']), 'pos': p['pos'], 'start_time': time.time(),
                        'inventory': json.loads(p['inventory']) if p.get('inventory') else {},
                        'mercs': json.loads(p['mercs']) if p.get('mercs') else []
                    }
                    st.session_state.slot_num = slot_id
                    st.session_state.game_started = True; st.rerun()

    # [게임 화면]
    else:
        player = st.session_state.player
        
        # 상단 정보바 계산
        max_w = 200 + sum([mercs_data.get(m, {}).get('weight_bonus', 0) for m in player['mercs']])
        curr_w = sum([items_info.get(it, {}).get('weight', 0) * qty for it, qty in player['inventory'].items()])
        
        # 상단 UI
        st.markdown(f"""<div class='info-box'>
            <span style='font-size:20px;'>📍 <b>{player['pos']}</b></span> | 💰 <b>{player['money']:,}냥</b><br>
            📦 무게: {curr_w}/{max_w}근 | ⏰ {get_time_display(player['start_time'])}
        </div>""", unsafe_allow_html=True)

        tab1, tab2, tab3 = st.tabs(["🛒 저잣거리", "🚩 이동", "👤 상단 설정"])

        with tab1:
            # 현재 마을 데이터 찾기
            v_data = next((v for r in regions.values() for v in r if v['village_name'] == player['pos']), None)
            if v_data:
                for item_name, base_val in items_info.items():
                    stock = v_data.get(item_name, 0)
                    price = calculate_price(item_name, stock, item_max_stocks, items_info, settings)
                    
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"**{item_name}** ({stock}개)")
                    c2.write(f"{price:,}냥")
                    if c3.button("선택", key=f"tr_{item_name}"):
                        st.session_state.active_trade = {'name': item_name, 'price': price, 'weight': base_val['weight']}
                
                if 'active_trade' in st.session_state:
                    at = st.session_state.active_trade
                    st.divider()
                    st.write(f"**{at['name']} 거래 중** (무게: {at['weight']}근)")
                    amt = st.number_input("수량 입력 (99999 등)", 1, 100000, 1)
                    
                    col_b, col_s = st.columns(2)
                    if col_b.button("매수"):
                        total_price = at['price'] * amt
                        total_weight = at['weight'] * amt
                        # 검증
                        if player['money'] < total_price: st.error("❌ 자금이 부족합니다.")
                        elif curr_w + total_weight > max_w: st.error(f"❌ 무게가 초과되었습니다. (여유: {max_w - curr_w}근)")
                        elif int(v_data.get(at['name'], 0)) < amt: st.error("❌ 마을 재고가 부족합니다.")
                        else:
                            player['money'] -= total_price
                            player['inventory'][at['name']] = player['inventory'].get(at['name'], 0) + amt
                            st.success(f"✅ {at['name']} {amt}개 매수 완료!"); st.rerun()
                    
                    if col_s.button("매도"):
                        if player['inventory'].get(at['name'], 0) >= amt:
                            player['money'] += at['price'] * amt
                            player['inventory'][at['name']] -= amt
                            st.success(f"✅ {at['name']} {amt}개 매도 완료!"); st.rerun()
                        else: st.error("❌ 소지품이 부족합니다.")

        with tab2:
            st.write("### 🌏 국가별 이동 (스크롤)")
            country_tabs = st.tabs(list(regions.keys()))
            for i, country in enumerate(regions.keys()):
                with country_tabs[i]:
                    with st.container(height=350):
                        for v in regions[country]:
                            if v['village_name'] == player['pos']: continue
                            col_n, col_m = st.columns([3, 1])
                            col_n.write(f"**{v['village_name']}**")
                            if col_m.button("이동", key=f"mv_{country}_{v['village_name']}"):
                                player['pos'] = v['village_name']; st.rerun()

        with tab3:
            if st.button("💾 데이터 저장"):
                ws = doc.worksheet("Player_Data")
                r = st.session_state.slot_num + 1
                save_data = [st.session_state.slot_num, player['money'], player['pos'], 
                             json.dumps(player['mercs'], ensure_ascii=False), 
                             json.dumps(player['inventory'], ensure_ascii=False), 
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{r}:F{r}", [save_data])
                st.success("✅ 저장 완료!")
