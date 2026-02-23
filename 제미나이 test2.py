import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 페이지 설정 및 초기화 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="wide")

if 'trade_logs' not in st.session_state:
    st.session_state.trade_logs = []

# --- 2. 데이터 연동 (캐시) ---
@st.cache_resource
def get_gsheet_client():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("조선거상_DB")
    except: return None

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

# --- 3. 핵심 엔진 함수 ---
def get_status(player, items_info, mercs_info):
    curr_w = sum(int(count) * items_info.get(item, {}).get('w', 0) for item, count in player['inventory'].items())
    max_w = 1000 + sum(mercs_info.get(m, {}).get('w_bonus', 0) for m in player['mercs'])
    return curr_w, max_w

def calculate_price(item_name, stock, items_info, settings):
    base = items_info.get(item_name, {}).get('base', 100)
    vol = settings.get('volatility', 5000) / 1000
    try:
        curr_s = int(str(stock).replace(',','')) if stock else 5000
    except: curr_s = 5000
    ratio = 5000 / max(1, curr_s) 
    return int(base * max(0.5, min(20.0, math.pow(ratio, (vol / 4)))))

def sync_engine(doc):
    if 'start_time' not in st.session_state: st.session_state.start_time = time.time()
    elapsed = int(time.time() - st.session_state.start_time)
    c_month = elapsed // 180
    if 'last_reset_month' not in st.session_state: st.session_state.last_reset_month = 0
    if c_month > st.session_state.last_reset_month:
        try:
            st.session_state.villages = doc.worksheet("Village_Data").get_all_records()
            st.session_state.last_reset_month = c_month
        except: pass
    return (c_month // 12)+1, (c_month % 12)+1, ((elapsed % 180) // 45)+1, 45-(elapsed % 45)

# --- 4. 메인 게임 로직 ---
static_data = load_static_db()
if static_data:
    settings, items_info, mercs_info = static_data
    doc = get_gsheet_client()
    year, month, week, remains = sync_engine(doc)

    if 'game_started' not in st.session_state or not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        slots = doc.worksheet("Player_Data").get_all_records()
        for i, p in enumerate(slots):
            if st.button(f"슬롯 {i+1} 접속 ({p['pos']})"):
                st.session_state.player = {
                    'money': int(p['money']), 'pos': p['pos'],
                    'inventory': json.loads(p['inventory']) if p['inventory'] else {},
                    'mercs': json.loads(p['mercs']) if p['mercs'] else []
                }
                st.session_state.slot_num = i+1
                st.session_state.game_started = True
                st.rerun()
    else:
        player = st.session_state.player
        c_w, m_w = get_status(player, items_info, mercs_info)

        # 상단 실시간 UI (잊지 말라고 하신 초시간 표시)
        st.markdown(f"""
        <div style="background:#1a1a1a; color:#0f0; padding:15px; border-radius:10px; border:2px solid #444;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <h2 style="margin:0; color:white;">📅 {year}년 {month}월 {week}주차</h2>
                <h3 style="margin:0; color:#ff0;">⏱️ {remains}초 남음</h3>
            </div>
            <p style="margin:10px 0 0 0;">📍 <b>{player['pos']}</b> | 💰 <b>{player['money']:,}냥</b> | ⚖️ <b>{c_w:,} / {m_w:,} 斤</b></p>
        </div>""", unsafe_allow_html=True)

        tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🚩 이동", "⚔️ 용병 주막", "🎒 정보/저장"])

        with tab1: # 저잣거리
            if 'villages' not in st.session_state: st.session_state.villages = doc.worksheet("Village_Data").get_all_records()
            v_idx = next(i for i, v in enumerate(st.session_state.villages) if v['village_name'] == player['pos'])
            v_data = st.session_state.villages[v_idx]

            for item in items_info.keys():
                s_val = int(v_data.get(item, 0)) if str(v_data.get(item,0)).isdigit() else 0
                price = calculate_price(item, s_val, items_info, settings)
                my_s = int(player['inventory'].get(item, 0))
                c1, c2, c3 = st.columns([2, 1, 1])
                c1.write(f"**{item}** (재고:{s_val:,} | 보유:{my_s:,})")
                c2.write(f"**{price:,}냥**")
                if c3.button("거래", key=f"t_{item}"): st.session_state.active_trade = item
            
            if 'active_trade' in st.session_state:
                at = st.session_state.active_trade
                st.divider()
                st.subheader(f"📦 {at} 매매 실행")
                amt = st.number_input("수량", 1, 100000, 100)
                b_col, s_col = st.columns(2)
                
                # 로그 출력 영역
                if st.session_state.trade_logs:
                    st.code("\n".join(st.session_state.trade_logs[-5:]))

                if b_col.button("일괄 매수 시작"):
                    done = 0
                    st.session_state.trade_logs = [] # 새 거래 시 로그 초기화
                    while done < amt:
                        curr_weight, max_weight = get_status(player, items_info, mercs_info)
                        cur_s = int(v_data[at])
                        p_now = calculate_price(at, cur_s, items_info, settings)
                        batch = min(100, amt - done)
                        
                        if curr_weight + (batch * items_info[at]['w']) > max_weight:
                            batch = max(0, int((max_weight - curr_weight) // items_info[at]['w']))
                            if batch <= 0: st.session_state.trade_logs.append("🛑 무게 초과!"); break
                        if cur_s < batch: batch = cur_s
                        if player['money'] < (p_now * batch) or batch <= 0: break

                        player['money'] -= (p_now * batch)
                        player['inventory'][at] = player['inventory'].get(at, 0) + batch
                        v_data[at] = int(v_data[at]) - batch
                        done += batch
                        st.session_state.trade_logs.append(f"✅ {done}/{amt}개 체결 완료 (단가: {p_now:,}냥)")
                        time.sleep(0.01)
                    doc.worksheet("Village_Data").update_cell(v_idx+2, list(v_data.keys()).index(at)+1, v_data[at])
                    st.rerun()

                if s_col.button("일괄 매도 시작"):
                    done = 0
                    st.session_state.trade_logs = []
                    target = min(amt, player['inventory'].get(at, 0))
                    while done < target:
                        cur_s = int(v_data[at])
                        p_now = calculate_price(at, cur_s, items_info, settings)
                        batch = min(100, target - done)
                        player['money'] += (p_now * batch)
                        player['inventory'][at] -= batch
                        v_data[at] = int(v_data[at]) + batch
                        done += batch
                        st.session_state.trade_logs.append(f"💰 {done}/{target}개 판매 완료 (단가: {p_now:,}냥)")
                        time.sleep(0.01)
                    doc.worksheet("Village_Data").update_cell(v_idx+2, list(v_data.keys()).index(at)+1, v_data[at])
                    st.rerun()

        with tab2: # 모든 도시 이동 복구
            st.subheader("🚩 팔도 강산 이동")
            cols = st.columns(3)
            for idx, v in enumerate(st.session_state.villages):
                if v['village_name'] == player['pos']: continue
                with cols[idx % 3]:
                    if st.button(f"🚩 {v['village_name']} 이동", use_container_width=True, key=f"mv_{v['village_name']}"):
                        player['pos'] = v['village_name']
                        st.rerun()

        with tab3: # 용병 관리 (고용/해고)
            st.subheader("⚔️ 용병 고용 및 관리")
            if player['pos'] != "용병 고용소": st.warning("용병은 '용병 고용소'에서 관리 가능합니다.")
            
            # 고용 영역
            for m_name, m_info in mercs_info.items():
                mc1, mc2, mc3 = st.columns([2, 1, 1])
                mc1.write(f"**{m_name}** (+{m_info['w_bonus']:,} 斤)")
                mc2.write(f"{m_info['price']:,}냥")
                if mc3.button("고용", key=f"buy_{m_name}"):
                    if player['money'] >= m_info['price']:
                        player['money'] -= m_info['price']
                        player['mercs'].append(m_name)
                        st.rerun()

            st.divider()
            st.markdown("#### 보유 용병 목록 (해고 시 50% 환불)")
            for idx, m_name in enumerate(player['mercs']):
                rc1, rc2 = st.columns([3, 1])
                rc1.write(f"{idx+1}. **{m_name}**")
                if rc2.button("해고", key=f"fire_{idx}"):
                    player['money'] += int(mercs_info[m_name]['price'] * 0.5)
                    player['mercs'].pop(idx)
                    st.rerun()

        with tab4: # 저장 탭
            if st.button("💾 데이터 서버 저장"):
                ws = doc.worksheet("Player_Data")
                r_idx = st.session_state.slot_num + 1
                save_data = [st.session_state.slot_num, player['money'], player['pos'], 
                             json.dumps(player['mercs'], ensure_ascii=False), 
                             json.dumps(player['inventory'], ensure_ascii=False), 
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{r_idx}:F{r_idx}", [save_data])
                st.success("저장 완료!")
