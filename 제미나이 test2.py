import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="wide")

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

# --- 3. 실시간 시간 엔진 (라이브러리 없이 작동) ---
def sync_engine(doc):
    if 'start_time' not in st.session_state:
        st.session_state.start_time = time.time()
    
    elapsed = int(time.time() - st.session_state.start_time)
    current_total_months = elapsed // 180
    
    # 180초(1달) 주기 재고 초기화
    if 'last_reset_month' not in st.session_state:
        st.session_state.last_reset_month = 0
    if current_total_months > st.session_state.last_reset_month:
        try:
            st.session_state.villages = doc.worksheet("Village_Data").get_all_records()
            st.session_state.last_reset_month = current_total_months
            st.toast("🌙 달이 바뀌어 전국의 재고가 초기화되었습니다!")
        except: pass

    year = (current_total_months // 12) + 1
    month = (current_total_months % 12) + 1
    week = ((elapsed % 180) // 45) + 1
    remains = 45 - (elapsed % 45)
    
    return year, month, week, remains, elapsed

# --- 4. 가격 계산 (ValueError 철저 방어) ---
def calculate_price(item_name, stock, items_info, settings):
    base = items_info.get(item_name, {}).get('base', 100)
    vol = settings.get('volatility', 5000) / 1000
    # 문자열이나 공백 에러 방지
    try:
        curr_s = int(stock) if stock and str(stock).isdigit() else 5000
    except: curr_s = 5000
    
    ratio = 5000 / max(1, curr_s) 
    return int(base * max(0.5, min(20.0, math.pow(ratio, (vol / 4)))))

# --- 5. 메인 게임 로직 ---
static_data = load_static_db()
if static_data:
    settings, items_info, mercs_info = static_data
    doc = get_gsheet_client()
    year, month, week, remains, total_sec = sync_engine(doc)

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
                st.session_state.slot_num = i + 1
                st.session_state.game_started = True
                st.rerun()
    else:
        player = st.session_state.player
        # 무게 계산
        curr_w = sum(count * items_info.get(item, {}).get('w', 0) for item, count in player['inventory'].items())
        max_w = 1000 + sum(mercs_info.get(m, {}).get('w_bonus', 0) for m in player['mercs'])

        # [상단 UI: 실시간 초시간 표시]
        st.markdown(f"""
        <div style="background:#222; color:#0f0; padding:15px; border-radius:10px; border:2px solid #555;">
            <div style="display:flex; justify-content:space-between;">
                <h2 style="margin:0; color:white;">📅 {year}년 {month}월 {week}주차</h2>
                <h2 style="margin:0; color:#ff0;">⏱️ {remains}초 남음</h2>
            </div>
            <p style="margin:5px 0 0 0;">📍 {player['pos']} | 💰 {player['money']:,}냥 | ⚖️ {curr_w:,}/{max_w:,}</p>
        </div>
        """, unsafe_allow_html=True)

        tab1, tab2, tab3 = st.tabs(["🛒 저잣거리", "🚩 이동", " Backpack"])

        with tab1: # 저잣거리 (매수/매도 핵심)
            if 'villages' not in st.session_state:
                st.session_state.villages = doc.worksheet("Village_Data").get_all_records()
            
            v_idx = next(i for i, v in enumerate(st.session_state.villages) if v['village_name'] == player['pos'])
            v_data = st.session_state.villages[v_idx]

            for item in items_info.keys():
                stock_val = v_data.get(item, 0)
                price = calculate_price(item, stock_val, items_info, settings)
                my_stock = player['inventory'].get(item, 0)
                
                c1, c2, c3 = st.columns([2, 1, 1])
                c1.write(f"**{item}** (시장:{stock_val} | 보유:{my_stock})")
                c2.write(f"**{price:,}냥**")
                if c3.button("거래", key=f"trade_{item}"):
                    st.session_state.active_trade = item
            
            if 'active_trade' in st.session_state:
                at = st.session_state.active_trade
                st.divider()
                st.subheader(f"📦 {at} 매매")
                amt = st.number_input("수량", 1, 100000, 100)
                
                b_col, s_col = st.columns(2)
                if b_col.button("일괄 매수 시작"):
                    done = 0
                    while done < amt:
                        # 실시간 가격 갱신을 위해 매 루프마다 다시 계산
                        cur_s = int(v_data[at]) if str(v_data[at]).isdigit() else 0
                        p_now = calculate_price(at, cur_s, items_info, settings)
                        batch = min(100, amt - done)
                        
                        # 검증
                        if (curr_w + (batch * items_info[at]['w'])) > max_w: batch = max(0, int((max_w - curr_w) // items_info[at]['w']))
                        if cur_s < batch: batch = cur_s
                        if player['money'] < (p_now * batch) or batch <= 0: break
                        
                        # 체결
                        player['money'] -= (p_now * batch)
                        player['inventory'][at] = player['inventory'].get(at, 0) + batch
                        v_data[at] = int(v_data[at]) - batch
                        done += batch
                        time.sleep(0.01)
                    
                    doc.worksheet("Village_Data").update_cell(v_idx+2, list(v_data.keys()).index(at)+1, v_data[at])
                    st.rerun()

                if s_col.button("일괄 매도 시작"):
                    done = 0
                    target = min(amt, player['inventory'].get(at, 0))
                    while done < target:
                        cur_s = int(v_data[at]) if str(v_data[at]).isdigit() else 0
                        p_now = calculate_price(at, cur_s, items_info, settings)
                        batch = min(100, target - done)
                        
                        player['money'] += (p_now * batch)
                        player['inventory'][at] -= batch
                        v_data[at] = int(v_data[at]) + batch
                        done += batch
                        time.sleep(0.01)
                    
                    doc.worksheet("Village_Data").update_cell(v_idx+2, list(v_data.keys()).index(at)+1, v_data[at])
                    st.rerun()

        with tab2: # 이동
            for v in st.session_state.villages:
                if v['village_name'] == player['pos'] or v['village_name'] == "용병 고용소": continue
                if st.button(f"{v['village_name']} 이동", key=f"mv_{v['village_name']}"):
                    player['pos'] = v['village_name']
                    st.rerun()
