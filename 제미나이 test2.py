import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 페이지 설정 및 초기화 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

# [핵심 수정] 세션 상태 초기화 (AttributeError 방지)
if 'game_started' not in st.session_state:
    st.session_state.game_started = False

# --- 2. 데이터 연동 (사용자 원본 구조 유지) ---
@st.cache_resource
def load_all_data():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        doc = gspread.authorize(creds).open("조선거상_DB")
        
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
        items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        mercs_data = {r['name']: {'price': int(r['price']), 'weight_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
        
        # 국가별 마을 데이터 로드 및 전 세계 최대 재고량 파악
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
        st.error(f"데이터 로딩 실패: {e}"); return None

# --- 3. 가격 변동 핵심 수식 (volatility 적용) ---
def get_dynamic_price(item_name, stock, item_max_stocks, items_info, settings):
    base_price = items_info[item_name]['base']
    max_s = item_max_stocks.get(item_name, 100)
    vol = settings.get('volatility', 5000) / 1000
    
    try:
        curr_s = int(stock)
        if curr_s <= 0: return base_price * 5 # 재고 없으면 5배 폭등
    except: return base_price
    
    # [수식] (최대재고 / 현재재고) ^ (변동성/4)
    ratio = max_s / curr_s
    factor = math.pow(ratio, (vol / 4))
    
    # 최소 0.5배에서 최대 20배까지 제한
    return int(base_price * max(0.5, min(20.0, factor)))

# --- 4. 시간 표시 로직 ---
def get_time_display(player_start_time):
    elapsed = int(time.time() - player_start_time)
    months = elapsed // 30
    year = 1592 + (months // 12)
    month = (months % 12) + 1
    return f"{year}년 {month}월 ({30 - (elapsed % 30)}초 후 다음 달)"

# --- 5. 메인 실행부 ---
res = load_all_data()
if res:
    doc, settings, items_info, mercs_data, regions, item_max_stocks, player_slots = res

    # [초기 화면: 슬롯 선택]
    if not st.session_state.game_started:
        st.title("🏯 거상: 대륙의 시작")
        st.subheader("슬롯을 선택하세요")
        for i, p in enumerate(player_slots):
            with st.container(border=True):
                # 슬롯 정보 출력 (Money, Pos, Time)
                st.write(f"💾 **슬롯 {i+1}** | 📍 {p.get('pos','한양')} | 💰 {int(p.get('money',0)):,}냥")
                st.caption(f"최근 저장: {p.get('last_save','없음')}")
                if st.button(f"슬롯 {i+1} 접속", key=f"slot_{i}"):
                    st.session_state.player = {
                        'money': int(p.get('money', 10000)),
                        'pos': p.get('pos', '한양'),
                        'inventory': json.loads(p['inventory']) if p.get('inventory') else {},
                        'mercs': json.loads(p['mercs']) if p.get('mercs') else [],
                        'start_time': time.time()
                    }
                    st.session_state.slot_num = i + 1
                    st.session_state.game_started = True
                    st.rerun()

    # [게임 플레이 화면]
    else:
        player = st.session_state.player
        
        # 무게 계산 (보유 용병 보너스 합산)
        max_w = 200 + sum([mercs_data.get(m, {}).get('weight_bonus', 0) for m in player['mercs']])
        curr_w = sum([items_info.get(it, {}).get('base', 0) * 0 + items_info.get(it, {}).get('w', 0) * qty 
                      for it, qty in player['inventory'].items() if it in items_info])

        # 상단 정보 바
        st.info(f"📍 **{player['pos']}** | 💰 **{player['money']:,}냥** | 📦 **{curr_w}/{max_w}근** | ⏰ **{get_time_display(player['start_time'])}**")

        tab_mkt, tab_merc, tab_move, tab_info = st.tabs(["🛒 저잣거리", "🛡️ 용병 고용", "🚩 이동", "👤 상단 정보"])

        with tab_mkt:
            # 현재 마을의 재고 데이터 찾기
            v_data = next((v for r in regions.values() for v in r if v['village_name'] == player['pos']), None)
            if v_data:
                for item_name, info in items_info.items():
                    stock = v_data.get(item_name, 0)
                    if stock == "": continue
                    
                    # [핵심] 동적 시세 적용
                    price = get_dynamic_price(item_name, stock, item_max_stocks, items_info, settings)
                    
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"**{item_name}** ({stock}개)")
                    c2.write(f"{price:,}냥")
                    if c3.button("거래", key=f"tr_{item_name}"):
                        st.session_state.active_trade = {'name': item_name, 'price': price, 'weight': info['w']}

                if 'active_trade' in st.session_state:
                    at = st.session_state.active_trade
                    st.divider()
                    amt = st.number_input(f"{at['name']} 수량 (무게: {at['weight']}근)", 1, 100000, 1)
                    b1, b2 = st.columns(2)
                    if b1.button("매수"):
                        if player['money'] >= at['price'] * amt and curr_w + (at['weight'] * amt) <= max_w:
                            player['money'] -= at['price'] * amt
                            player['inventory'][at['name']] = player['inventory'].get(at['name'], 0) + amt
                            st.rerun()
                        else: st.error("돈 부족 또는 무게 초과!")
                    if b2.button("매도"):
                        if player['inventory'].get(at['name'], 0) >= amt:
                            player['money'] += at['price'] * amt
                            player['inventory'][at['name']] -= amt
                            st.rerun()

        with tab_merc:
            if player['pos'] == "용병 고용소":
                for m_name, m_info in mercs_data.items():
                    col1, col2, col3 = st.columns([2, 1, 1])
                    col1.write(f"**{m_name}** (+{m_info['weight_bonus']}근)")
                    col2.write(f"{m_info['price']:,}냥")
                    if col3.button("고용", key=f"hire_{m_name}"):
                        if len(player['mercs']) < settings.get('max_mercenaries', 5) and player['money'] >= m_info['price']:
                            player['money'] -= m_info['price']
                            player['mercs'].append(m_name)
                            st.success(f"{m_name} 고용 완료!"); st.rerun()
            else: st.warning("'용병 고용소' 마을로 이동하세요.")

        with tab_move:
            country_tabs = st.tabs(list(regions.keys()))
            for i, country in enumerate(regions.keys()):
                with country_tabs[i]:
                    with st.container(height=300):
                        for v in regions[country]:
                            if v['village_name'] == player['pos']: continue
                            c_v, c_b = st.columns([3, 1])
                            c_v.write(f"**{v['village_name']}**")
                            if c_b.button("이동", key=f"mv_{country}_{v['village_name']}"):
                                player['pos'] = v['village_name']; st.rerun()

        with tab_info:
            st.write(f"### 🎒 인벤토리")
            for item, qty in player['inventory'].items():
                if qty > 0: st.write(f"- {item}: {qty}개")
            st.write(f"### 🛡️ 보유 용병: {', '.join(player['mercs']) if player['mercs'] else '없음'}")
            
            if st.button("💾 저장"):
                ws = doc.worksheet("Player_Data")
                r = st.session_state.slot_num + 1
                save_data = [st.session_state.slot_num, player['money'], player['pos'], 
                             json.dumps(player['mercs'], ensure_ascii=False), 
                             json.dumps(player['inventory'], ensure_ascii=False), 
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{r}:F{r}", [save_data])
                st.success("저장 완료!")
