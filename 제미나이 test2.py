import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 페이지 설정 및 스타일 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="wide")

st.markdown("""
<style>
    .stButton button { width: 100%; height: 3em; font-weight: bold; }
    .log-box { background-color: #1e1e1e; color: #00ff00; padding: 15px; border-radius: 5px; font-family: 'Courier New'; font-size: 0.9em; min-height: 200px; }
    .stat-header { background: #2c3e50; color: white; padding: 15px; border-radius: 10px; margin-bottom: 20px; }
</style>
""", unsafe_allow_html=True)

# --- 2. 데이터베이스 연동 (API 호출 최소화 전략) ---
@st.cache_resource
def get_gsheet_client():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("조선거상_DB")
    except: return None

# TTL(유지시간)을 설정하여 1분 동안은 API를 다시 호출하지 않고 메모리에서 가져옵니다.
@st.cache_data(ttl=60)
def fetch_static_data():
    doc = get_gsheet_client()
    if not doc: return None
    try:
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records()}
        items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        mercs_info = {r['name']: {'price': int(r['price']), 'w_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
        player_slots = doc.worksheet("Player_Data").get_all_records()
        return settings, items_info, mercs_info, player_slots
    except: return None

# 마을 데이터는 거래 시 실시간성이 중요하므로 별도로 관리하되, 로컬 세션 상태를 우선 활용합니다.
def fetch_village_data():
    if 'villages' not in st.session_state:
        doc = get_gsheet_client()
        st.session_state.villages = doc.worksheet("Village_Data").get_all_records()
    return st.session_state.villages

# --- 3. 핵심 엔진 ---
def calculate_price(item_name, stock, items_info, settings):
    # 각 아이템별 최대 재고량을 계산 (가격 기준점)
    max_s = 5000 # 기준 최대 재고 (DB에서 동적으로 가져오도록 수정 가능)
    base = items_info[item_name]['base']
    vol = settings.get('volatility', 5000) / 1000
    curr_s = max(1, int(stock))
    ratio = max_s / curr_s
    factor = math.pow(ratio, (vol / 4))
    return int(base * max(0.5, min(20.0, factor)))

def get_status(player, items_info, mercs_info):
    curr_w = sum(count * items_info.get(item, {}).get('w', 0) for item, count in player['inventory'].items())
    # [중요] 용병 리스트를 순회하며 중복된 용병의 보너스도 모두 합산합니다.
    max_w = 1000 + sum(mercs_info.get(m, {}).get('w_bonus', 0) for m in player['mercs'])
    return curr_w, max_w

# --- 4. 메인 프로그램 ---
static_data = fetch_static_data()
villages = fetch_village_data()

if static_data:
    settings, items_info, mercs_info, player_slots = static_data

    if 'game_started' not in st.session_state: st.session_state.game_started = False

    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        cols = st.columns(len(player_slots))
        for i, p in enumerate(player_slots):
            with cols[i]:
                st.markdown(f'<div style="border:1px solid #ddd; padding:10px; border-radius:10px;"><b>💾 슬롯 {i+1}</b><br>💰 {int(p["money"]):,}냥<br>📍 {p["pos"]}</div>', unsafe_allow_html=True)
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
            <h2 style='margin:0;'>📍 {player['pos']} 상단</h2>
            <b>소지금:</b> {player['money']:,}냥 | <b>무게:</b> {curr_w:,} / {max_w:,}
        </div>""", unsafe_allow_html=True)

        tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🚩 이동", "🎒 인벤토리", "⚔️ 주막(용병)"])

        with tab1: # 저잣거리 (실시간 매매)
            v_data = next((v for v in villages if v['village_name'] == player['pos']), None)
            if v_data:
                for item in items_info.keys():
                    stock = int(v_data.get(item, 0)) if str(v_data.get(item)).isdigit() else 0
                    price = calculate_price(item, stock, items_info, settings)
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"**{item}** ({stock:,}개)")
                    c2.write(f"{price:,}냥")
                    if c3.button("거래", key=f"t_{item}"): st.session_state.active_trade = item
                
                if 'active_trade' in st.session_state:
                    at = st.session_state.active_trade
                    st.divider()
                    t_amt = st.number_input(f"{at} 거래 수량", 1, 100000, 100)
                    b_col, s_col = st.columns(2)
                    log_placeholder = st.empty()

                    if b_col.button("일괄 매수 시작"):
                        total_cost, current_got = 0, 0
                        logs = [f"구매 수량 >> {t_amt}"]
                        while current_got < t_amt:
                            cur_s = int(v_data.get(at, 0))
                            p_now = calculate_price(at, cur_s, items_info, settings)
                            batch = min(100, t_amt - current_got)
                            
                            if (get_status(player, items_info, mercs_info)[0] + (batch * items_info[at]['w'])) > max_w:
                                batch = max(0, int((max_w - get_status(player, items_info, mercs_info)[0]) // items_info[at]['w']))
                                if batch <= 0: logs.append("⚠️ 무게 초과!"); break
                            
                            if cur_s < batch: batch = cur_s
                            if batch <= 0: logs.append("❌ 재고 부족"); break
                            
                            cost = p_now * batch
                            if player['money'] < cost: logs.append("❌ 자금 부족"); break

                            player['money'] -= cost
                            player['inventory'][at] = player['inventory'].get(at, 0) + batch
                            v_data[at] = int(v_data[at]) - batch
                            current_got += batch
                            total_cost += cost
                            
                            logs.append(f"➤ {current_got}/{t_amt} 구매 중... (가: {p_now:,}냥)")
                            log_placeholder.markdown(f'<div class="log-box">{"<br>".join(logs[-5:])}</div>', unsafe_allow_html=True)
                            time.sleep(0.3)
                        
                        # DB 반영 (Quota 보호를 위해 거래 종료 후 1회 업데이트)
                        try:
                            doc = get_gsheet_client()
                            village_ws = doc.worksheet("Village_Data")
                            # 마을 행 찾기
                            all_v = village_ws.get_all_records()
                            row_idx = next(i for i, v in enumerate(all_v) if v['village_name'] == player['pos']) + 2
                            col_idx = list(all_v[0].keys()).index(at) + 1
                            village_ws.update_cell(row_idx, col_idx, v_data[at])
                            logs.append("✅ DB 저장 완료")
                        except: logs.append("⚠️ DB 연결 지연")
                        log_placeholder.markdown(f'<div class="log-box">{"<br>".join(logs[-6:])}</div>', unsafe_allow_html=True)

        with tab4: # 주막 (용병 중복 고용 해결)
            st.subheader("⚔️ 용병 고용소")
            st.info("같은 종류의 용병을 여러 명 고용하여 무게 제한을 누적시킬 수 있습니다.")
            
            for m_name, m_val in mercs_info.items():
                mc1, mc2, mc3 = st.columns([2, 1, 1])
                mc1.write(f"**{m_name}** (무게 +{m_val['w_bonus']})")
                mc2.write(f"{m_val['price']:,}냥")
                if mc3.button("고용하기", key=f"buy_{m_name}"):
                    if player['money'] >= m_val['price']:
                        player['money'] -= m_val['price']
                        # 리스트에 단순히 추가함으로서 중복 고용 허용
                        player['mercs'].append(m_name)
                        st.success(f"{m_name} 고용 완료!")
                        time.sleep(0.5)
                        st.rerun() # 무게 수치 즉시 반영을 위해 리런
                    else:
                        st.error("자금이 부족합니다.")

            st.divider()
            st.write("📋 보유 중인 용병 (클릭 시 해고)")
            if not player['mercs']:
                st.caption("고용된 용병이 없습니다.")
            else:
                for idx, m in enumerate(player['mercs']):
                    c1, c2 = st.columns([3, 1])
                    c1.write(f"{idx+1}. {m} (보너스: +{mercs_info[m]['w_bonus']})")
                    if c2.button("해고", key=f"fire_{idx}"):
                        player['mercs'].pop(idx)
                        st.rerun()
