import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

st.markdown("""
<style>
    .slot-container { background-color: #ffffff; padding: 20px; border-radius: 15px; border: 1px solid #e1e4e8; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .stButton button { width: 100%; font-weight: bold; }
    .log-box { background-color: #1e1e1e; color: #00ff00; padding: 15px; border-radius: 5px; font-family: 'Courier New', Courier, monospace; font-size: 0.9em; line-height: 1.5; }
    .inventory-card { background-color: #f1f3f5; padding: 10px; border-radius: 8px; border-left: 5px solid #495057; margin-bottom: 5px; }
</style>
""", unsafe_allow_html=True)

# --- 2. 데이터 연동 (캐싱) ---
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
                            try: val = int(stock)
                            except: val = 0
                            item_max_stocks[item] = max(item_max_stocks[item], val)
        
        player_slots = doc.worksheet("Player_Data").get_all_records()
        return doc, settings, items_info, mercs_data, regions, item_max_stocks, player_slots
    except Exception as e:
        st.error(f"데이터 로딩 오류: {e}")
        return None

# --- 3. 핵심 로직 ---
def calculate_price(item_name, stock, item_max_stocks, items_info, settings):
    base = items_info[item_name]['base']
    max_s = item_max_stocks.get(item_name, 100)
    vol = settings.get('volatility', 5000) / 1000
    curr_s = int(stock) if str(stock).isdigit() and int(stock) > 0 else 1
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
                        'inventory': json.loads(p['inventory']) if p.get('inventory') and p['inventory'] != "{}" else {},
                        'mercs': json.loads(p['mercs']) if p.get('mercs') and p['mercs'] != "[]" else []
                    }
                    st.session_state.slot_num = slot_id
                    st.session_state.game_started = True
                    st.rerun()

    # [화면 2: 인게임]
    else:
        player = st.session_state.player
        st.header(f"📍 {player['pos']}")
        st.subheader(f"💰 소지금: {player['money']:,}냥")

        tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🚩 이동", "👤 상단 정보", "⚔️ 주막(용병)"])

        with tab1: # 장터 및 실시간 체결
            v_data = next((v for r in regions.values() for v in r if v['village_name'] == player['pos']), None)
            
            if v_data:
                for item_name in items_info.keys():
                    stock = v_data.get(item_name, 0)
                    price = calculate_price(item_name, stock, item_max_stocks, items_info, settings)
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"**{item_name}** ({stock}개)")
                    c2.write(f"{price:,}냥")
                    if c3.button("선택", key=f"sel_{item_name}"):
                        st.session_state.active_trade = {'name': item_name, 'price': price}
                
                if 'active_trade' in st.session_state:
                    at = st.session_state.active_trade
                    st.divider()
                    st.markdown(f"### 📦 {at['name']} 거래 중")
                    target_amt = st.number_input("거래 희망 수량", 1, 100000, 100)
                    
                    b_col, s_col = st.columns(2)
                    log_placeholder = st.empty() 

                    # --- [매수 로직] ---
                    if b_col.button("일괄 매수 시작"):
                        total_cost, current_got = 0, 0
                        logs = [f"구매 수량 >> {target_amt}"]
                        
                        while current_got < target_amt:
                            # 실시간 가격 & 재고 확인
                            curr_stock = v_data.get(at['name'], 0)
                            dynamic_price = calculate_price(at['name'], curr_stock, item_max_stocks, items_info, settings)
                            
                            batch = min(100, target_amt - current_got)
                            if curr_stock < batch: # 재고 부족 시 남은 만큼만 매수
                                batch = curr_stock
                                if batch <= 0: logs.append("❌ 마을 재고가 없습니다."); break

                            step_cost = dynamic_price * batch
                            if player['money'] < step_cost: logs.append("❌ 잔액 부족!"); break
                            
                            # 데이터 처리
                            player['money'] -= step_cost
                            player['inventory'][at['name']] = player['inventory'].get(at['name'], 0) + batch
                            v_data[at['name']] -= batch # 재고 감소 -> 가격 상승 유도
                            
                            current_got += batch
                            total_cost += step_cost
                            avg_price = total_cost / current_got
                            
                            logs.append(f"➤ {current_got}/{target_amt} 매수 중... (가: {dynamic_price:,}냥 / 평단: {int(avg_price):,}냥)")
                            log_placeholder.markdown(f'<div class="log-box">{"<br>".join(logs[-5:])}</div>', unsafe_allow_html=True)
                            time.sleep(0.3)
                        
                        logs.append(f"✅ 총 {current_got}개 매수 완료!")
                        log_placeholder.markdown(f'<div class="log-box">{"<br>".join(logs[-6:])}</div>', unsafe_allow_html=True)

                    # --- [매도 로직] ---
                    if s_col.button("일괄 매도 시작"):
                        total_rev, current_sold = 0, 0
                        my_stock = player['inventory'].get(at['name'], 0)
                        actual_target = min(target_amt, my_stock)
                        logs = [f"판매 수량 >> {actual_target}"]

                        while current_sold < actual_target:
                            # 실시간 가격 & 재고 확인
                            curr_stock = v_data.get(at['name'], 0)
                            dynamic_price = calculate_price(at['name'], curr_stock, item_max_stocks, items_info, settings)
                            
                            batch = min(100, actual_target - current_sold)
                            step_rev = dynamic_price * batch
                            
                            # 데이터 처리
                            player['money'] += step_rev
                            player['inventory'][at['name']] -= batch
                            v_data[at['name']] += batch # 재고 증가 -> 가격 하락 유도
                            
                            current_sold += batch
                            total_rev += step_rev
                            
                            logs.append(f"➤ {current_sold}/{actual_target} 매도 중... (체결가: {dynamic_price:,}냥)")
                            log_placeholder.markdown(f'<div class="log-box">{"<br>".join(logs[-5:])}</div>', unsafe_allow_html=True)
                            time.sleep(0.3)
                        
                        logs.append(f"✅ 총 {current_sold}개 매도 완료!")
                        log_placeholder.markdown(f'<div class="log-box">{"<br>".join(logs[-6:])}</div>', unsafe_allow_html=True)

        with tab2: # 이동
            countries = list(regions.keys())
            selected_tabs = st.tabs(countries)
            for idx, country in enumerate(countries):
                with selected_tabs[idx]:
                    for v in regions[country]:
                        if v['village_name'] == player['pos']: continue
                        col_v, col_b = st.columns([3, 1])
                        col_v.write(f"**{v['village_name']}**")
                        if col_b.button("이동", key=f"mv_{v['village_name']}"):
                            player['pos'] = v['village_name']
                            st.rerun()

        with tab3: # 상단 정보 (인벤토리 UI)
            st.subheader("🎒 상단 인벤토리")
            if not player['inventory'] or sum(player['inventory'].values()) == 0:
                st.info("인벤토리가 비어 있습니다.")
            else:
                for item, count in player['inventory'].items():
                    if count > 0:
                        weight = items_info.get(item, {}).get('w', 0) * count
                        st.markdown(f"""<div class="inventory-card">
                        <b>{item}</b> : {count:,}개 <small>(무게: {weight:,})</small>
                        </div>""", unsafe_allow_html=True)
            
            st.divider()
            if st.button("💾 현재 진행상황 저장"):
                ws = doc.worksheet("Player_Data")
                r_idx = st.session_state.slot_num + 1
                save_data = [st.session_state.slot_num, player['money'], player['pos'], 
                             json.dumps(player['mercs'], ensure_ascii=False), 
                             json.dumps(player['inventory'], ensure_ascii=False), 
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{r_idx}:F{r_idx}", [save_data])
                st.success("데이터베이스에 저장되었습니다!")

        with tab4: # 주막 (용병)
            st.subheader("⚔️ 용병 고용 및 관리")
            
            # 보유 용병
            st.write("📋 보유 중인 용병")
            if not player['mercs']:
                st.caption("보유한 용병이 없습니다.")
            else:
                for i, m_name in enumerate(player['mercs']):
                    mc1, mc2 = st.columns([3, 1])
                    mc1.write(f"{i+1}. **{m_name}**")
                    if mc2.button("해고", key=f"fire_{i}"):
                        player['mercs'].pop(i)
                        st.rerun()

            st.divider()
            st.write("🤝 신규 고용")
            for m_name, m_info in mercs_data.items():
                mc1, mc2, mc3 = st.columns([2, 1, 1])
                mc1.write(f"**{m_name}**")
                mc2.write(f"{m_info['price']:,}냥")
                if mc3.button("고용", key=f"buy_m_{m_name}"):
                    if player['money'] >= m_info['price']:
                        if len(player['mercs']) < 10: # 최대 10명 제한 예시
                            player['money'] -= m_info['price']
                            player['mercs'].append(m_name)
                            st.success(f"{m_name}을(를) 고용했습니다!")
                            st.rerun()
                        else: st.error("용병단이 가득 찼습니다.")
                    else: st.error("자금이 부족합니다.")




