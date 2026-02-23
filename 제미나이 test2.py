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

# 정적 데이터 캐싱 (API 호출 절약: 10분 유지)
@st.cache_data(ttl=600)
def load_static_db():
    doc = get_gsheet_client()
    if not doc: return None
    try:
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
        items = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        mercs = {r['name']: {'price': int(r['price']), 'w_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
        return settings, items, mercs
    except: return None

# --- 2. 핵심 함수 ---
def get_status(player, items_info, mercs_info):
    curr_w = sum(count * items_info.get(item, {}).get('w', 0) for item, count in player['inventory'].items())
    # [핵심] 리스트 내 모든 용병 보너스 합산 (중복 고용 지원)
    max_w = 1000 + sum(mercs_info.get(m, {}).get('w_bonus', 0) for m in player['mercs'])
    return curr_w, max_w

def calculate_price(item_name, stock, items_info, settings):
    base = items_info[item_name]['base']
    vol = settings.get('volatility', 5000) / 1000
    # 기준 재고 5000 대비 현재 재고 비율로 가격 산출
    curr_s = max(1, int(stock))
    ratio = 5000 / curr_s
    factor = math.pow(ratio, (vol / 4))
    return int(base * max(0.5, min(20.0, factor)))

# --- 3. 메인 엔진 ---
static_data = load_static_db()
if static_data:
    settings, items_info, mercs_info = static_data
    doc = get_gsheet_client()

    # 초기 데이터 로드 (세션 관리)
    if 'game_started' not in st.session_state:
        st.session_state.game_started = False
        # 마을 정보는 세션에 담아 API 호출 최소화
        st.session_state.villages = doc.worksheet("Village_Data").get_all_records()

    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        player_slots = doc.worksheet("Player_Data").get_all_records()
        cols = st.columns(len(player_slots))
        for i, p in enumerate(player_slots):
            with cols[i]:
                st.markdown(f'<div style="border:1px solid #ddd; padding:15px; border-radius:10px;"><b>💾 슬롯 {i+1}</b><br>💰 {int(p["money"]):,}냥<br>📍 {p["pos"]}</div>', unsafe_allow_html=True)
                if st.button(f"슬롯 {i+1} 시작", key=f"s_{i}"):
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

        # 상태바 UI
        st.info(f"📍 {player['pos']} 상단 | 💰 {player['money']:,}냥 | ⚖️ 무게: {curr_w:,} / {max_w:,}")

        tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🚩 이동", "🎒 인벤토리", "⚔️ 주막"])

        with tab1: # 저잣거리
            villages = st.session_state.villages
            v_idx = next(i for i, v in enumerate(villages) if v['village_name'] == player['pos'])
            v_data = villages[v_idx]

            for item in items_info.keys():
                raw_stock = v_data.get(item, 0)
                stock = int(raw_stock) if str(raw_stock).isdigit() else 0
                price = calculate_price(item, stock, items_info, settings)
                
                c1, c2, c3 = st.columns([2, 1, 1])
                c1.write(f"**{item}** ({stock:,}개)")
                c2.write(f"{price:,}냥")
                if c3.button("거래 선택", key=f"t_{item}"): st.session_state.active_trade = item
            
            if 'active_trade' in st.session_state:
                at = st.session_state.active_trade
                st.divider()
                t_amt = st.number_input(f"{at} 수량", 1, 100000, 100)
                log_placeholder = st.empty()

                if st.button("일괄 매수 시작"):
                    logs = [f"구매 수량 >> {t_amt}"]
                    current_got = 0
                    while current_got < t_amt:
                        cur_s = int(v_data[at])
                        p_now = calculate_price(at, cur_s, items_info, settings)
                        batch = min(100, t_amt - current_got)
                        
                        # 실시간 무게 체크
                        if (get_status(player, items_info, mercs_info)[0] + (batch * items_info[at]['w'])) > max_w:
                            batch = max(0, int((max_w - get_status(player, items_info, mercs_info)[0]) // items_info[at]['w']))
                            if batch <= 0: logs.append("⚠️ 무게 초과!"); break
                        
                        if cur_s < batch: batch = cur_s
                        if batch <= 0: logs.append("❌ 재고 부족"); break
                        if player['money'] < (p_now * batch): logs.append("❌ 자금 부족"); break

                        # 로컬 체결
                        player['money'] -= (p_now * batch)
                        player['inventory'][at] = player['inventory'].get(at, 0) + batch
                        v_data[at] = int(v_data[at]) - batch
                        current_got += batch
                        
                        logs.append(f"➤ {current_got}/{t_amt} 구매 중... (가: {p_now:,}냥)")
                        log_placeholder.code("\n".join(logs[-5:]))
                        time.sleep(0.3)
                    
                    # [API 최적화] 거래 종료 후 단 1회만 DB 업데이트
                    try:
                        v_ws = doc.worksheet("Village_Data")
                        col_idx = list(v_data.keys()).index(at) + 1
                        v_ws.update_cell(v_idx + 2, col_idx, v_data[at])
                        st.success("💾 DB 저장 완료!")
                        time.sleep(1)
                        st.rerun() # 탭 활성화를 위한 리런
                    except:
                        st.warning("⚠️ API 지연 발생 (잠시 후 이동 탭을 눌러주세요)")

        with tab2: # 이동 탭 (정상 작동 보장)
            st.subheader("🚩 행선지 선택")
            for v in st.session_state.villages:
                if v['village_name'] == player['pos'] or v['village_name'] == "용병 고용소": continue
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{v['village_name']}**")
                if c2.button("이동", key=f"mv_{v['village_name']}"):
                    player['pos'] = v['village_name']
                    st.rerun()

        with tab4: # 주막 (중복 고용 해결)
            st.subheader("⚔️ 용병 주막")
            st.caption("동일한 용병을 여러 명 고용하여 무게 제한을 누적할 수 있습니다.")
            for m_name, m_info in mercs_info.items():
                mc1, mc2, mc3 = st.columns([2, 1, 1])
                mc1.write(f"**{m_name}** (+{m_info['w_bonus']} 무게)")
                mc2.write(f"{m_info['price']:,}냥")
                if mc3.button("고용", key=f"buy_{m_name}"):
                    if player['money'] >= m_info['price']:
                        player['money'] -= m_info['price']
                        player['mercs'].append(m_name)
                        st.rerun()
            
            st.divider()
            st.write("📋 보유 용병")
            for idx, m in enumerate(player['mercs']):
                c1, c2 = st.columns([3, 1])
                c1.write(f"{idx+1}. {m} (무게 보너스 반영됨)")
                if c2.button("해고", key=f"fire_{idx}"):
                    player['mercs'].pop(idx)
                    st.rerun()
