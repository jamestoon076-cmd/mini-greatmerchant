import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 페이지 설정 및 캐시 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="wide")

@st.cache_resource
def get_gsheet_client():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("조선거상_DB")
    except: return None

# 정적 데이터 캐싱 (API 호출 절약의 핵심: 10분 유지)
@st.cache_data(ttl=600)
def load_static_db():
    doc = get_gsheet_client()
    if not doc: return None
    try:
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records()}
        items = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        mercs = {r['name']: {'price': int(r['price']), 'w_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
        return settings, items, mercs
    except: return None

# --- 2. 헬퍼 함수 ---
def get_current_status(player, items_info, mercs_info):
    curr_w = sum(count * items_info.get(item, {}).get('w', 0) for item, count in player['inventory'].items())
    # 중복 고용된 용병들의 보너스를 모두 합산
    max_w = 1000 + sum(mercs_info.get(m, {}).get('w_bonus', 0) for m in player['mercs'])
    return curr_w, max_w

def calculate_price(item_name, stock, items_info, settings):
    base = items_info[item_name]['base']
    vol = settings.get('volatility', 5000) / 1000
    # 기준 최대 재고 (5000개 고정 혹은 DB 기반 설정 가능)
    ratio = 5000 / max(1, int(stock))
    return int(base * max(0.5, min(20.0, math.pow(ratio, (vol / 4)))))

# --- 3. 메인 로직 ---
static_data = load_static_db()
if static_data:
    settings, items_info, mercs_info = static_data
    doc = get_gsheet_client()

    # 최초 접속 시 데이터 로드 (세션당 1회)
    if 'player' not in st.session_state:
        slots = doc.worksheet("Player_Data").get_all_records()
        st.session_state.slots = slots
        st.session_state.game_started = False

    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        for i, p in enumerate(st.session_state.slots):
            if st.button(f"슬롯 {i+1} 접속 ({p['pos']} | {int(p['money']):,}냥)"):
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
        curr_w, max_w = get_current_status(player, items_info, mercs_info)

        # 상단 UI
        st.info(f"📍 {player['pos']} | 💰 {player['money']:,}냥 | ⚖️ {curr_w:,} / {max_w:,}")

        tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🚩 이동", "🎒 정보", "⚔️ 주막"])

        with tab1: # 저잣거리
            # 마을 데이터 로드 (이동 시에만 갱신되도록 최적화 가능)
            v_ws = doc.worksheet("Village_Data")
            v_list = v_ws.get_all_records()
            v_idx = next(i for i, v in enumerate(v_list) if v['village_name'] == player['pos'])
            v_data = v_list[v_idx]

            for item in items_info.keys():
                stock = int(v_data.get(item, 0))
                price = calculate_price(item, stock, items_info, settings)
                c1, c2, c3 = st.columns([2, 1, 1])
                c1.write(f"**{item}** ({stock:,}개)")
                c2.write(f"{price:,}냥")
                if c3.button("거래", key=f"t_{item}"): st.session_state.active_item = item

            if 'active_item' in st.session_state:
                at = st.session_state.active_item
                st.divider()
                t_amt = st.number_input(f"{at} 수량", 1, 100000, 100)
                log_placeholder = st.empty()
                
                if st.button("일괄 매수 시작"):
                    logs = []
                    current_got = 0
                    while current_got < t_amt:
                        # 실시간 데이터 참조
                        cur_stock = int(v_data[at])
                        p_now = calculate_price(at, cur_stock, items_info, settings)
                        batch = min(100, t_amt - current_got)
                        
                        # 무게 체크
                        if (get_current_status(player, items_info, mercs_info)[0] + (batch * items_info[at]['w'])) > max_w:
                            batch = max(0, int((max_w - get_current_status(player, items_info, mercs_info)[0]) // items_info[at]['w']))
                            if batch <= 0: logs.append("⚠️ 무게 초과!"); break
                        
                        if cur_stock < batch: batch = cur_stock
                        if batch <= 0: logs.append("❌ 재고 부족"); break
                        if player['money'] < (p_now * batch): logs.append("❌ 자금 부족"); break

                        # 체결
                        player['money'] -= (p_now * batch)
                        player['inventory'][at] = player['inventory'].get(at, 0) + batch
                        v_data[at] = int(v_data[at]) - batch
                        current_got += batch
                        
                        logs.append(f"➤ {current_got}/{t_amt} 구매 중... (가: {p_now}냥)")
                        log_placeholder.code("\n".join(logs[-5:]))
                        time.sleep(0.2)
                    
                    # [최적화] 루프가 끝나면 DB에 딱 1번만 업데이트 (API 절약)
                    col_char = chr(65 + list(v_data.keys()).index(at)) # 컬럼 알파벳 계산
                    v_ws.update_cell(v_idx + 2, list(v_data.keys()).index(at) + 1, v_data[at])
                    st.success("거래 완료 및 DB 저장 성공!")
                    time.sleep(1)
                    st.rerun()

        with tab2: # 이동
            st.write("🚩 이동할 마을을 선택하세요.")
            for v in v_list:
                if v['village_name'] == player['pos']: continue
                if st.button(f"{v['village_name']}으로 이동"):
                    player['pos'] = v['village_name']
                    st.rerun()

        with tab4: # 주막 (중복 고용 가능)
            st.subheader("⚔️ 용병 고용 (중복 가능)")
            for m_name, m_info in mercs_info.items():
                mc1, mc2, mc3 = st.columns([2, 1, 1])
                mc1.write(f"**{m_name}** (+{m_info['w_bonus']})")
                mc2.write(f"{m_info['price']:,}냥")
                if mc3.button("고용", key=f"buy_{m_name}"):
                    if player['money'] >= m_info['price']:
                        player['money'] -= m_info['price']
                        player['mercs'].append(m_name) # 중복 체크 없이 추가
                        st.rerun()
            
            st.divider()
            st.write("📋 보유 용병")
            for idx, m in enumerate(player['mercs']):
                c1, c2 = st.columns([3, 1])
                c1.write(f"{idx+1}. {m}")
                if c2.button("해고", key=f"fire_{idx}"):
                    player['mercs'].pop(idx)
                    st.rerun()
