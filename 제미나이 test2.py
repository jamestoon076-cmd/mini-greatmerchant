import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 페이지 설정 및 세션 초기화 (AttributeError 방지) ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

if 'game_started' not in st.session_state:
    st.session_state.game_started = False

# --- 2. 데이터 로드 함수 ---
@st.cache_resource
def load_game_data():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        doc = gspread.authorize(creds).open("조선거상_DB")
        
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
        items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        mercs_info = {r['name']: {'price': int(r['price']), 'weight_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
        
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
        return doc, settings, items_info, mercs_info, regions, item_max_stocks, player_slots
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}"); return None

# --- 3. 가격 및 시간 유틸리티 ---
def get_dynamic_price(item_name, stock, item_max_stocks, items_info, settings):
    base = items_info[item_name]['base']
    max_s = item_max_stocks.get(item_name, 100)
    vol = settings.get('volatility', 5000) / 1000
    try:
        curr_s = int(stock)
        if curr_s <= 0: return base * 5
        factor = math.pow(max_s / curr_s, (vol / 4))
        return int(base * max(0.5, min(20.0, factor)))
    except: return base

def get_real_time(start_time):
    elapsed = int(time.time() - start_time)
    months = elapsed // 30
    seconds_left = 30 - (elapsed % 30)
    year = 1592 + (months // 12)
    month = (months % 12) + 1
    return f"{year}년 {month}월 ({seconds_left}초 후 다음 달)"

# --- 4. 메인 실행 ---
data = load_game_data()
if data:
    doc, settings, items_info, mercs_info, regions, item_max_stocks, player_slots = data

    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        for i, p in enumerate(player_slots):
            with st.container(border=True):
                st.write(f"💾 **슬롯 {i+1}** | 📍 {p.get('pos','한양')} | 💰 {int(p.get('money',0)):,}냥")
                if st.button(f"슬롯 {i+1} 시작", key=f"btn_{i}"):
                    st.session_state.player = {
                        'money': int(p.get('money', 10000)),
                        'pos': p.get('pos', '한양'),
                        'inventory': json.loads(p['inventory']) if p.get('inventory') else {},
                        'mercs': json.loads(p['mercs']) if p.get('mercs') else [],
                        'start_time': time.time()
                    }
                    st.session_state.slot_num = i + 1
                    st.session_state.game_started = True; st.rerun()
    else:
        player = st.session_state.player
        # 무게 계산
        max_w = 200 + sum([mercs_info.get(m, {}).get('weight_bonus', 0) for m in player['mercs']])
        curr_w = sum([items_info.get(it, {}).get('w', 0) * qty for it, qty in player['inventory'].items() if it in items_info])

        # 상단 UI
        st.info(f"📍 **{player['pos']}** | 💰 **{player['money']:,}냥** | 📦 **{curr_w}/{max_w}근** | ⏰ **{get_real_time(player['start_time'])}**")

        tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🛡️ 용병 관리", "🚩 이동", "👤 상단 정보"])

        with tab1: # 장터 (재고 기반 시세 적용)
            v_data = next((v for r in regions.values() for v in r if v['village_name'] == player['pos']), None)
            if v_data:
                for item_name, info in items_info.items():
                    stock = v_data.get(item_name, 0)
                    if stock == "": continue
                    price = get_dynamic_price(item_name, stock, item_max_stocks, items_info, settings)
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"**{item_name}** ({stock}개)")
                    c2.write(f"{price:,}냥")
                    if c3.button("거래", key=f"t_{item_name}"):
                        st.session_state.active_trade = {'name': item_name, 'price': price, 'weight': info['w']}
                
                if 'active_trade' in st.session_state:
                    at = st.session_state.active_trade
                    st.divider()
                    amt = st.number_input(f"{at['name']} 수량", 1, 100000, 1)
                    col_b, col_s = st.columns(2)
                    if col_b.button("매수"):
                        if player['money'] >= at['price'] * amt and curr_w + (at['weight'] * amt) <= max_w:
                            player['money'] -= at['price'] * amt
                            player['inventory'][at['name']] = player['inventory'].get(at['name'], 0) + amt
                            st.rerun()
                        else: st.error("❌ 자금 부족 또는 무게 초과!")
                    if col_s.button("매도"):
                        if player['inventory'].get(at['name'], 0) >= amt:
                            player['money'] += at['price'] * amt
                            player['inventory'][at['name']] -= amt
                            st.rerun()

        with tab2: # 용병 고용 및 해고
            st.write("### 🛡️ 현재 보유 용병")
            if player['mercs']:
                for idx, m_name in enumerate(player['mercs']):
                    col_m, col_h = st.columns([3, 1])
                    col_m.write(f"{idx+1}. **{m_name}** (+{mercs_info[m_name]['weight_bonus']}근)")
                    if col_h.button("해고", key=f"fire_{idx}"):
                        refund = mercs_info[m_name]['price'] // 2
                        player['money'] += refund
                        player['mercs'].pop(idx)
                        st.warning(f"{m_name}을(를) 해고했습니다. (반환금: {refund:,}냥)")
                        st.rerun()
            else: st.write("보유한 용병이 없습니다.")

            st.divider()
            if player['pos'] == "용병 고용소":
                st.write("### 🆕 새 용병 고용")
                for m_name, m_info in mercs_info.items():
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"**{m_name}** (+{m_info['weight_bonus']}근)")
                    c2.write(f"{m_info['price']:,}냥")
                    if c3.button("고용", key=f"hire_{m_name}"):
                        if len(player['mercs']) < 5 and player['money'] >= m_info['price']:
                            player['money'] -= m_info['price']
                            player['mercs'].append(m_name)
                            st.success(f"{m_name} 고용 완료!")
                            st.rerun()
                        else: st.error("❌ 정원 초과 또는 자금 부족")
            else: st.info("용병 고용은 '용병 고용소' 마을에서만 가능합니다.")

        with tab3: # 이동
            country_tabs = st.tabs(list(regions.keys()))
            for i, country in enumerate(regions.keys()):
                with country_tabs[i]:
                    with st.container(height=300):
                        for v in regions[country]:
                            if v['village_name'] == player['pos']: continue
                            cv, cb = st.columns([3, 1])
                            cv.write(f"**{v['village_name']}**")
                            if cb.button("이동", key=f"mv_{country}_{v['village_name']}"):
                                player['pos'] = v['village_name']; st.rerun()

        with tab4: # 정보 및 저장
            st.write("### 🎒 보유 물품")
            items_found = False
            for it, qty in player['inventory'].items():
                if qty > 0:
                    st.write(f"- {it}: {qty}개")
                    items_found = True
            if not items_found: st.write("물품 없음")
            
            if st.button("💾 데이터 저장", use_container_width=True):
                ws = doc.worksheet("Player_Data")
                r = st.session_state.slot_num + 1
                save_row = [st.session_state.slot_num, player['money'], player['pos'], 
                            json.dumps(player['mercs'], ensure_ascii=False), 
                            json.dumps(player['inventory'], ensure_ascii=False), 
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{r}:F{r}", [save_row])
                st.success("✅ 저장 성공!")
