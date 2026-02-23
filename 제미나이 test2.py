import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 페이지 설정 및 디자인 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="wide")

# --- 2. 데이터 연동 및 캐싱 (API 429 방지) ---
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

# --- 3. 시간 및 재고 초기화 시스템 ---
def update_game_time_and_sync():
    if 'start_time' not in st.session_state:
        st.session_state.start_time = time.time()
    
    elapsed = int(time.time() - st.session_state.start_time)
    
    # [핵심] 1달(180초)마다 재고 초기화 체크
    current_total_months = elapsed // 180
    if 'last_reset_month' not in st.session_state:
        st.session_state.last_reset_month = 0
    
    # 달이 바뀌면 재고 초기화 로직 실행
    if current_total_months > st.session_state.last_reset_month:
        doc = get_gsheet_client()
        if doc:
            # DB에서 원본 재고 데이터를 새로 읽어와 세션 갱신
            st.session_state.villages = doc.worksheet("Village_Data").get_all_records()
            st.session_state.last_reset_month = current_total_months
            st.toast("🌙 달이 바뀌어 전국의 시장 재고가 초기화되었습니다!", icon="♻️")

    year = (current_total_months // 12) + 1
    month = (current_total_months % 12) + 1
    week = ((elapsed % 180) // 45) + 1
    
    return year, month, week, elapsed % 45

# --- 4. 핵심 로직 ---
def get_status(player, items_info, mercs_info):
    curr_w = sum(count * items_info.get(item, {}).get('w', 0) for item, count in player['inventory'].items())
    max_w = 1000 + sum(mercs_info.get(m, {}).get('w_bonus', 0) for m in player['mercs'])
    return curr_w, max_w

def calculate_price(item_name, stock, items_info, settings):
    base = items_info[item_name]['base']
    vol = settings.get('volatility', 5000) / 1000
    curr_s = max(1, int(stock))
    ratio = 5000 / curr_s 
    return int(base * max(0.5, min(20.0, math.pow(ratio, (vol / 4)))))

# --- 5. 메인 엔진 ---
static_data = load_static_db()
if static_data:
    settings, items_info, mercs_info = static_data
    doc = get_gsheet_client()
    
    # 시간 업데이트 및 재고 동기화 실행
    year, month, week, next_week_remains = update_game_time_and_sync()

    if 'game_started' not in st.session_state:
        st.session_state.game_started = False
        st.session_state.villages = doc.worksheet("Village_Data").get_all_records()

    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        slots = doc.worksheet("Player_Data").get_all_records()
        for i, p in enumerate(slots):
            if st.button(f"슬롯 {i+1} 접속 ({p['pos']})"):
                st.session_state.player = {
                    'money': int(p['money']), 'pos': p['pos'],
                    'inventory': json.loads(p['inventory']) if p['inventory'] else {},
                    'mercs': json.loads(p['mercs']) if p['mercs'] else []
                }
                st.session_state.game_started = True
                st.rerun()
    else:
        player = st.session_state.player
        curr_w, max_w = get_status(player, items_info, mercs_info)

        # 상단 UI
        st.markdown(f"""
        <div style="background:#2c3e50; color:white; padding:15px; border-radius:10px; margin-bottom:10px;">
            <h3 style="margin:0;">📅 {year}년 {month}월 {week}주차</h3>
            <small>다음 주까지: {45 - next_week_remains}초 | 위치: {player['pos']} | 자금: {player['money']:,}냥 | 무게: {curr_w:,}/{max_w:,}</small>
        </div>
        """, unsafe_allow_html=True)
        
        if next_week_remains < 2:
            st.toast(f"🔔 {week}주차가 시작되었습니다!", icon="🏯")

        tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🚩 이동", "🎒 정보", "⚔️ 주막"])

        with tab1: # 저잣거리
            v_idx = next(i for i, v in enumerate(st.session_state.villages) if v['village_name'] == player['pos'])
            v_data = st.session_state.villages[v_idx]

            for item in items_info.keys():
                stock = int(v_data.get(item, 0))
                price = calculate_price(item, stock, items_info, settings)
                my_stock = player['inventory'].get(item, 0)
                
                c1, c2, c3 = st.columns([2, 1, 1])
                c1.write(f"**{item}** (시장: {stock:,} | 보유: {my_stock:,})")
                c2.write(f"{price:,}냥")
                if c3.button("선택", key=f"t_{item}"): st.session_state.active_trade = item
            
            if 'active_trade' in st.session_state:
                at = st.session_state.active_trade
                st.divider()
                st.subheader(f"📦 {at} 매매")
                t_amt = st.number_input("수량 입력", 1, 100000, 100)
                
                b_col, s_col = st.columns(2)
                log_placeholder = st.empty()

                if b_col.button("일괄 매수"):
                    logs = []
                    got = 0
                    while got < t_amt:
                        cur_s = int(v_data[at])
                        p_now = calculate_price(at, cur_s, items_info, settings)
                        batch = min(100, t_amt - got)
                        
                        if (get_status(player, items_info, mercs_info)[0] + (batch * items_info[at]['w'])) > max_w:
                            batch = max(0, int((max_w - get_status(player, items_info, mercs_info)[0]) // items_info[at]['w']))
                            if batch <= 0: logs.append("⚠️ 무게 초과!"); break
                        if cur_s < batch: batch = cur_s
                        if batch <= 0: logs.append("❌ 재고 부족"); break
                        if player['money'] < (p_now * batch): logs.append("❌ 자금 부족"); break

                        player['money'] -= (p_now * batch)
                        player['inventory'][at] = player['inventory'].get(at, 0) + batch
                        v_data[at] = int(v_data[at]) - batch
                        got += batch
                        logs.append(f"➤ {got}/{t_amt} 매수 중... ({p_now}냥)")
                        log_placeholder.code("\n".join(logs[-5:]))
                        time.sleep(0.1)
                    
                    doc.worksheet("Village_Data").update_cell(v_idx+2, list(v_data.keys()).index(at)+1, v_data[at])
                    st.rerun()

                if s_col.button("일괄 매도"):
                    logs = []
                    sold = 0
                    my_s = player['inventory'].get(at, 0)
                    target = min(t_amt, my_s)
                    while sold < target:
                        cur_s = int(v_data[at])
                        p_now = calculate_price(at, cur_s, items_info, settings)
                        batch = min(100, target - sold)
                        
                        player['money'] += (p_now * batch)
                        player['inventory'][at] -= batch
                        v_data[at] = int(v_data[at]) + batch
                        sold += batch
                        logs.append(f"➤ {sold}/{target} 매도 중... ({p_now}냥)")
                        log_placeholder.code("\n".join(logs[-5:]))
                        time.sleep(0.1)
                    
                    doc.worksheet("Village_Data").update_cell(v_idx+2, list(v_data.keys()).index(at)+1, v_data[at])
                    st.rerun()

        with tab2: # 이동
            for v in st.session_state.villages:
                if v['village_name'] == player['pos']: continue
                if st.button(f"{v['village_name']} 이동"):
                    player['pos'] = v['village_name']
                    st.rerun()
                    
        # (tab3 정보, tab4 주막 로직은 기존과 동일)
