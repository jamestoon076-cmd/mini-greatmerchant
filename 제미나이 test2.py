import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="wide")

st.markdown("""
<style>
    .stButton button { width: 100%; height: 3em; font-weight: bold; }
    .log-box { background-color: #1e1e1e; color: #00ff00; padding: 15px; border-radius: 5px; font-family: 'Courier New'; font-size: 0.9em; min-height: 200px; }
    .inventory-card { background-color: #f1f3f5; padding: 10px; border-radius: 8px; border-left: 5px solid #2c3e50; margin-bottom: 5px; }
    .stat-header { background: #2c3e50; color: white; padding: 15px; border-radius: 10px; margin-bottom: 20px; }
</style>
""", unsafe_allow_html=True)

# --- 2. 데이터베이스 연동 ---
@st.cache_resource
def get_gsheet_client():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"DB 연결 실패: {e}")
        return None

def load_data():
    doc = get_gsheet_client()
    if not doc: return None
    try:
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records()}
        items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        mercs_info = {r['name']: {'price': int(r['price']), 'w_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
        villages = doc.worksheet("Village_Data").get_all_records()
        player_slots = doc.worksheet("Player_Data").get_all_records()
        
        # 아이템별 전체 마을 중 최대 재고량 (가격 계산의 기준점)
        item_max_stocks = {name: 0 for name in items_info.keys()}
        for v in villages:
            for item in items_info.keys():
                val = v.get(item)
                if val and str(val).isdigit():
                    item_max_stocks[item] = max(item_max_stocks[item], int(val))
        
        return doc, settings, items_info, mercs_info, villages, item_max_stocks, player_slots
    except Exception as e:
        st.error(f"데이터 로드 에러: {e}")
        return None

# --- 3. 핵심 엔진 ---
def calculate_price(item_name, current_stock, max_stock, items_info, settings):
    base = items_info[item_name]['base']
    vol = settings.get('volatility', 5000) / 1000
    # 재고가 적을수록 가격이 지수함수적으로 상승
    stock_val = max(1, int(current_stock))
    ratio = max_stock / stock_val
    factor = math.pow(ratio, (vol / 4))
    return int(base * max(0.5, min(20.0, factor)))

def get_status(player, items_info, mercs_info):
    curr_w = sum(count * items_info.get(item, {}).get('w', 0) for item, count in player['inventory'].items())
    max_w = 1000 + sum(mercs_info.get(m, {}).get('w_bonus', 0) for m in player['mercs'])
    return curr_w, max_w

# --- 4. 메인 프로그램 ---
data_bundle = load_data()
if data_bundle:
    doc, settings, items_info, mercs_info, villages, item_max_stocks, player_slots = data_bundle

    if 'game_started' not in st.session_state: st.session_state.game_started = False

    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        cols = st.columns(len(player_slots))
        for i, p in enumerate(player_slots):
            with cols[i]:
                st.markdown(f'<div class="slot-container"><b>💾 슬롯 {i+1}</b><br>💰 {int(p["money"]):,}냥<br>📍 {p["pos"]}</div>', unsafe_allow_html=True)
                if st.button(f"접속 {i+1}", key=f"s_{i}"):
                    st.session_state.player = {
                        'money': int(p['money']),
                        'pos': p['pos'],
                        'inventory': json.loads(p['inventory']) if p['inventory'] else {},
                        'mercs': json.loads(p['mercs']) if p['mercs'] else []
                    }
                    st.session_state.slot_num = i + 1
                    st.session_state.game_started = True
                    st.rerun()
    else:
        player = st.session_state.player
        curr_w, max_w = get_status(player, items_info, mercs_info)

        st.markdown(f"""<div class="stat-header">
            <h2 style='margin:0;'>📍 {player['pos']} (상단정보)</h2>
            <b>소지금:</b> {player['money']:,}냥 | <b>무게:</b> {curr_w:,} / {max_w:,}
        </div>""", unsafe_allow_html=True)

        tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🚩 이동", "🎒 인벤토리", "⚔️ 주막(용병)"])

        with tab1:
            v_data = next((v for v in villages if v['village_name'] == player['pos']), None)
            if v_data:
                for item in items_info.keys():
                    raw_stock = v_data.get(item, 0)
                    stock = int(raw_stock) if str(raw_stock).isdigit() else 0
                    if stock <= 0 and player['inventory'].get(item, 0) <= 0: continue # 재고도 없고 내 인벤에도 없으면 패스
                    
                    price = calculate_price(item, stock, item_max_stocks[item], items_info, settings)
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"**{item}** (마을재고: {stock:,})")
                    c2.write(f"시세: {price:,}냥")
                    if c3.button("거래하기", key=f"trade_{item}"):
                        st.session_state.active_trade = item
                
                if 'active_trade' in st.session_state:
                    at = st.session_state.active_trade
                    st.divider()
                    t_amt = st.number_input(f"{at} 수량 입력", 1, 100000, 100)
                    b_col, s_col = st.columns(2)
                    log_placeholder = st.empty()

                    # --- [1] 매수 (0.3초/100개 체결) ---
                    if b_col.button("일괄 매수 시작"):
                        total_cost, current_got = 0, 0
                        logs = [f"구매 수량 >> {t_amt}"]
                        while current_got < t_amt:
                            cur_s = int(v_data.get(at, 0))
                            p_now = calculate_price(at, cur_s, item_max_stocks[at], items_info, settings)
                            
                            batch = min(100, t_amt - current_got)
                            # 무게 체크
                            if (get_status(player, items_info, mercs_info)[0] + (batch * items_info[at]['w'])) > max_w:
                                batch = max(0, int((max_w - get_status(player, items_info, mercs_info)[0]) // items_info[at]['w']))
                                if batch <= 0: logs.append("⚠️ 무게 초과로 중단!"); break
                            
                            if cur_s < batch: batch = cur_s
                            if batch <= 0: logs.append("❌ 마을 재고 소진!"); break
                            if player['money'] < (p_now * batch): logs.append("❌ 자금 부족!"); break

                            player['money'] -= (p_now * batch)
                            player['inventory'][at] = player['inventory'].get(at, 0) + batch
                            v_data[at] = int(v_data[at]) - batch
                            current_got += batch
                            total_cost += (p_now * batch)
                            
                            logs.append(f"➤ {current_got}/{t_amt} 구매 중... (체결가: {p_now:,} / 평균가: {int(total_cost/current_got):,})")
                            log_placeholder.markdown(f'<div class="log-box">{"<br>".join(logs[-5:])}</div>', unsafe_allow_html=True)
                            time.sleep(0.3)
                        
                        # DB 즉시 반영
                        doc.worksheet("Village_Data").update_cell(villages.index(v_data)+2, list(v_data.keys()).index(at)+1, v_data[at])
                        logs.append("✅ 구매 및 DB 저장 완료!")
                        log_placeholder.markdown(f'<div class="log-box">{"<br>".join(logs[-6:])}</div>', unsafe_allow_html=True)

                    # --- [2] 매도 (0.3초/100개 체결) ---
                    if s_col.button("일괄 매도 시작"):
                        total_rev, current_sold = 0, 0
                        my_s = player['inventory'].get(at, 0)
                        act_t = min(t_amt, my_s)
                        logs = [f"판매 수량 >> {act_t}"]
                        while current_sold < act_t:
                            cur_s = int(v_data.get(at, 0))
                            p_now = calculate_price(at, cur_s, item_max_stocks[at], items_info, settings)
                            
                            batch = min(100, act_t - current_sold)
                            player['money'] += (p_now * batch)
                            player['inventory'][at] -= batch
                            v_data[at] = int(v_data[at]) + batch
                            current_sold += batch
                            
                            logs.append(f"➤ {current_sold}/{act_t} 판매 중... (체결가: {p_now:,})")
                            log_placeholder.markdown(f'<div class="log-box">{"<br>".join(logs[-5:])}</div>', unsafe_allow_html=True)
                            time.sleep(0.3)
                        
                        doc.worksheet("Village_Data").update_cell(villages.index(v_data)+2, list(v_data.keys()).index(at)+1, v_data[at])
                        logs.append("✅ 판매 및 DB 저장 완료!")
                        log_placeholder.markdown(f'<div class="log-box">{"<br>".join(logs[-6:])}</div>', unsafe_allow_html=True)

        with tab2: # 이동
            for v in villages:
                if v['village_name'] == player['pos'] or v['village_name'] == "용병 고용소": continue
                c1, c2 = st.columns([3, 1])
                c1.write(f"🚩 **{v['village_name']}**")
                if c2.button("이동", key=f"mv_{v['village_name']}"):
                    player['pos'] = v['village_name']
                    st.rerun()

        with tab3: # 인벤토리 (상단 정보)
            st.subheader("🎒 상단 보유 물품")
            for item, count in player['inventory'].items():
                if count > 0:
                    st.markdown(f'<div class="inventory-card"><b>{item}</b>: {count:,}개</div>', unsafe_allow_html=True)
            
            if st.button("💾 전체 세이브"):
                ws = doc.worksheet("Player_Data")
                save_row = [st.session_state.slot_num, player['money'], player['pos'], 
                            json.dumps(player['mercs'], ensure_ascii=False), 
                            json.dumps(player['inventory'], ensure_ascii=False), 
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{st.session_state.slot_num+1}:F{st.session_state.slot_num+1}", [save_row])
                st.success("상단 정보가 DB에 저장되었습니다.")

        with tab4: # 용병
            st.subheader("⚔️ 주막 (용병 고용)")
            for m_name, m_val in mercs_info.items():
                c1, c2, c3 = st.columns([2,1,1])
                c1.write(f"**{m_name}** (무게 +{m_val['w_bonus']})")
                c2.write(f"{m_val['price']:,}냥")
                if c3.button("고용", key=f"buy_{m_name}"):
                    if player['money'] >= m_val['price']:
                        player['money'] -= m_val['price']
                        player['mercs'].append(m_name)
                        st.rerun()
            st.divider()
            for idx, m in enumerate(player['mercs']):
                if st.button(f"[{idx+1}] {m} 해고", key=f"fire_{idx}"):
                    player['mercs'].pop(idx)
                    st.rerun()
