import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. 페이지 설정 및 자동 갱신 (1초마다) ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="wide")
st_autorefresh(interval=1000, key="gametimer") # 1초마다 화면 갱신

# --- 2. 데이터 연동 (캐싱) ---
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

# --- 3. 실시간 시간 및 재고 초기화 엔진 ---
def sync_engine(doc):
    if 'start_time' not in st.session_state:
        st.session_state.start_time = time.time()
    
    elapsed = int(time.time() - st.session_state.start_time)
    current_total_months = elapsed // 180 # 180초 = 1달
    
    if 'last_reset_month' not in st.session_state:
        st.session_state.last_reset_month = 0
    
    # 달이 바뀌면 재고 강제 초기화
    if current_total_months > st.session_state.last_reset_month:
        try:
            st.session_state.villages = doc.worksheet("Village_Data").get_all_records()
            st.session_state.last_reset_month = current_total_months
            st.toast("🌙 달이 바뀌어 전국의 시장 재고가 채워졌습니다!", icon="♻️")
        except: pass

    year = (current_total_months // 12) + 1
    month = (current_total_months % 12) + 1
    week = ((elapsed % 180) // 45) + 1 # 45초 = 1주
    remains = 45 - (elapsed % 45)
    
    return year, month, week, remains, elapsed

# --- 4. 가격 계산 (에러 방지 강화) ---
def calculate_price(item_name, stock, items_info, settings):
    base = items_info.get(item_name, {}).get('base', 100)
    vol = settings.get('volatility', 5000) / 1000
    try:
        # 공백이나 None 방지
        curr_s = int(stock) if (stock and str(stock).isdigit()) else 5000
    except: curr_s = 5000
    
    ratio = 5000 / max(1, curr_s) 
    return int(base * max(0.5, min(20.0, math.pow(ratio, (vol / 4)))))

def get_status(player, items_info, mercs_info):
    curr_w = sum(count * items_info.get(item, {}).get('w', 0) for item, count in player['inventory'].items())
    max_w = 1000 + sum(mercs_info.get(m, {}).get('w_bonus', 0) for m in player['mercs'])
    return curr_w, max_w

# --- 5. 메인 게임 로직 ---
static_data = load_static_db()
if static_data:
    settings, items_info, mercs_info = static_data
    doc = get_gsheet_client()
    year, month, week, remains, total_sec = sync_engine(doc)

    if 'game_started' not in st.session_state or not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        # 초기 접속 로직 (Player_Data 로드)
        slots = doc.worksheet("Player_Data").get_all_records()
        for i, p in enumerate(slots):
            if st.button(f"슬롯 {i+1} 접속 ({p['pos']})"):
                st.session_state.player = {
                    'money': int(p['money']), 'pos': p['pos'],
                    'inventory': json.loads(p['inventory']) if p['inventory'] else {},
                    'mercs': json.loads(p['mercs']) if p['mercs'] else []
                }
                st.session_state.slot_num = i + 1
                st.session_state.game_started = True
                st.rerun()
    else:
        player = st.session_state.player
        curr_w, max_w = get_status(player, items_info, mercs_info)

        # [상단 UI: 실시간 초시계 및 상태창]
        st.markdown(f"""
        <div style="background:#1e1e1e; color:#00ff00; padding:15px; border-radius:10px; border:2px solid #444; margin-bottom:20px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <h2 style="margin:0; color:white;">📅 {year}년 {month}월 {week}주차</h2>
                <h3 style="margin:0; color:#ffcc00;">⏱️ 다음 주까지: {remains}초</h3>
            </div>
            <p style="margin:10px 0 0 0; font-size:1.1em;">
                📍 <b>{player['pos']}</b> | 💰 <b>{player['money']:,}냥</b> | ⚖️ <b>{curr_w:,} / {max_w:,} 斤</b>
            </p>
        </div>
        """, unsafe_allow_html=True)

        tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🚩 이동", "🎒 정보", "⚔️ 주막"])

        with tab1: # 저잣거리 (매수/매도)
            if 'villages' not in st.session_state:
                st.session_state.villages = doc.worksheet("Village_Data").get_all_records()
            
            v_idx = next(i for i, v in enumerate(st.session_state.villages) if v['village_name'] == player['pos'])
            v_data = st.session_state.villages[v_idx]

            for item in items_info.keys():
                stock_val = v_data.get(item, 0)
                stock = int(stock_val) if (stock_val and str(stock_val).isdigit()) else 0
                price = calculate_price(item, stock, items_info, settings)
                my_stock = player['inventory'].get(item, 0)
                
                c1, c2, c3 = st.columns([2, 1, 1])
                c1.write(f"**{item}** (시장:{stock:,} | 보유:{my_stock:,})")
                c2.write(f"**{price:,}냥**")
                if c3.button("거래 선택", key=f"sel_{item}"):
                    st.session_state.active_trade = item
            
            if 'active_trade' in st.session_state:
                at = st.session_state.active_trade
                st.markdown(f"--- ### 📦 {at} 매매 실행")
                amt = st.number_input("수량 설정", 1, 100000, 100)
                
                b_col, s_col = st.columns(2)
                log_box = st.empty()

                if b_col.button("일괄 매수"):
                    done = 0
                    while done < amt:
                        cur_s = int(v_data[at])
                        p_now = calculate_price(at, cur_s, items_info, settings)
                        batch = min(100, amt - done)
                        # 조건 체크
                        if (get_status(player, items_info, mercs_info)[0] + (batch * items_info[at]['w'])) > max_w:
                            batch = max(0, int((max_w - get_status(player, items_info, mercs_info)[0]) // items_info[at]['w']))
                            if batch <= 0: break
                        if cur_s < batch: batch = cur_s
                        if player['money'] < (p_now * batch) or batch <= 0: break
                        # 실행
                        player['money'] -= (p_now * batch)
                        player['inventory'][at] = player['inventory'].get(at, 0) + batch
                        v_data[at] = int(v_data[at]) - batch
                        done += batch
                        log_box.code(f"매수 진행 중: {done}/{amt} 완료")
                        time.sleep(0.01)
                    doc.worksheet("Village_Data").update_cell(v_idx+2, list(v_data.keys()).index(at)+1, v_data[at])
                    st.rerun()

                if s_col.button("일괄 매도"):
                    done = 0
                    target = min(amt, player['inventory'].get(at, 0))
                    while done < target:
                        cur_s = int(v_data[at])
                        p_now = calculate_price(at, cur_s, items_info, settings)
                        batch = min(100, target - done)
                        # 실행
                        player['money'] += (p_now * batch)
                        player['inventory'][at] -= batch
                        v_data[at] = int(v_data[at]) + batch
                        done += batch
                        log_box.code(f"매도 진행 중: {done}/{target} 완료")
                        time.sleep(0.01)
                    doc.worksheet("Village_Data").update_cell(v_idx+2, list(v_data.keys()).index(at)+1, v_data[at])
                    st.rerun()

        with tab2: # 이동
            for v in st.session_state.villages:
                if v['village_name'] == player['pos'] or v['village_name'] == "용병 고용소": continue
                if st.button(f"{v['village_name']} 이동", key=f"mv_{v['village_name']}"):
                    player['pos'] = v['village_name']
                    st.rerun()

        with tab4: # 주막 (중복 고용)
            for m_name, m_info in mercs_info.items():
                mc1, mc2, mc3 = st.columns([2, 1, 1])
                mc1.write(f"**{m_name}** (+{m_info['w_bonus']} 무게)")
                mc2.write(f"{m_info['price']:,}냥")
                if mc3.button("고용", key=f"buy_{m_name}"):
                    if player['money'] >= m_info['price']:
                        player['money'] -= m_info['price']
                        player['mercs'].append(m_name)
                        st.rerun()
