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

# --- 3. 실시간 시간 및 재고 초기화 엔진 ---
def sync_engine(doc):
    if 'start_time' not in st.session_state:
        st.session_state.start_time = time.time()
    
    # 실시간 흐르는 시간 계산
    elapsed = int(time.time() - st.session_state.start_time)
    current_total_months = elapsed // 180
    
    # 180초(1달) 주기 재고 초기화
    if 'last_reset_month' not in st.session_state:
        st.session_state.last_reset_month = 0
    
    if current_total_months > st.session_state.last_reset_month:
        try:
            st.session_state.villages = doc.worksheet("Village_Data").get_all_records()
            st.session_state.last_reset_month = current_total_months
            st.toast("🌙 달이 바뀌어 전국의 재고가 초기화되었습니다!", icon="♻️")
        except: pass

    year = (current_total_months // 12) + 1
    month = (current_total_months % 12) + 1
    week = ((elapsed % 180) // 45) + 1
    remains = 45 - (elapsed % 45) # 다음 주까지 남은 초
    
    return year, month, week, remains, elapsed

# --- 4. 핵심 계산 함수 ---
def get_status(player, items_info, mercs_info):
    curr_w = sum(count * items_info.get(item, {}).get('w', 0) for item, count in player['inventory'].items())
    max_w = 1000 + sum(mercs_info.get(m, {}).get('w_bonus', 0) for m in player['mercs'])
    return curr_w, max_w

def calculate_price(item_name, stock, items_info, settings):
    # 데이터 타입 안전하게 변환
    base = items_info.get(item_name, {}).get('base', 100)
    vol = settings.get('volatility', 5000) / 1000
    try:
        curr_s = max(1, int(stock))
    except: curr_s = 5000
    
    ratio = 5000 / curr_s 
    price = int(base * max(0.5, min(20.0, math.pow(ratio, (vol / 4)))))
    return price

# --- 5. 메인 실행 ---
static_data = load_static_db()
if static_data:
    settings, items_info, mercs_info = static_data
    doc = get_gsheet_client()
    
    # 시간 데이터 업데이트
    year, month, week, remains, total_sec = sync_engine(doc)

    if 'game_started' not in st.session_state or not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        # 슬롯 선택 (간략화)
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

        # [상단 UI: 실시간 초시간 표시]
        st.markdown(f"""
        <div style="background:#1e1e1e; color:#00ff00; padding:15px; border-radius:10px; border:2px solid #444;">
            <h2 style="margin:0; color:white;">📅 {year}년 {month}월 {week}주차</h2>
            <p style="margin:5px 0 0 0;">⏱️ <b>다음 주까지: {remains}초</b> (총 진행: {total_sec}초)</p>
            <div style="font-size:0.9em; color:#aaa;">📍 {player['pos']} | 💰 {player['money']:,}냥 | ⚖️ {curr_w:,}/{max_w:,}</div>
        </div>
        """, unsafe_allow_html=True)

        # 매 1초마다 화면 갱신을 원할 경우 (성능에 따라 선택)
        # st.empty()를 활용한 자동 새로고침 대신 사용자가 행동할 때마다 최신 시간이 반영됩니다.

        tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🚩 이동", "🎒 정보", "⚔️ 주막"])

        with tab1: # 저잣거리
            v_idx = next(i for i, v in enumerate(st.session_state.villages) if v['village_name'] == player['pos'])
            v_data = st.session_state.villages[v_idx]

            for item in items_info.keys():
                stock = int(v_data.get(item, 0))
                price = calculate_price(item, stock, items_info, settings)
                my_stock = player['inventory'].get(item, 0)
                
                col1, col2, col3 = st.columns([2, 1, 1])
                col1.write(f"**{item}** (시장:{stock:,} | 보유:{my_stock:,})")
                col2.write(f"{price:,}냥")
                if col3.button("거래", key=f"btn_{item}"):
                    st.session_state.active_trade = item
            
            if 'active_trade' in st.session_state:
                at = st.session_state.active_trade
                st.markdown(f"--- ### 📦 {at} 매매 중")
                amt = st.number_input("수량", 1, 100000, 100)
                
                b_col, s_col = st.columns(2)
                log_box = st.empty()

                if b_col.button("일괄 매수 시작"):
                    logs = []
                    done = 0
                    while done < amt:
                        cur_s = int(v_data[at])
                        p_now = calculate_price(at, cur_s, items_info, settings)
                        batch = min(100, amt - done)
                        
                        # 무게/자금/재고 체크
                        if (get_status(player, items_info, mercs_info)[0] + (batch * items_info[at]['w'])) > max_w:
                            batch = max(0, int((max_w - get_status(player, items_info, mercs_info)[0]) // items_info[at]['w']))
                            if batch <= 0: logs.append("⚠️ 무게 초과!"); break
                        if cur_s < batch: batch = cur_s
                        if batch <= 0: logs.append("❌ 재고 부족"); break
                        if player['money'] < (p_now * batch): logs.append("❌ 자금 부족"); break

                        # 체결
                        player['money'] -= (p_now * batch)
                        player['inventory'][at] = player['inventory'].get(at, 0) + batch
                        v_data[at] = int(v_data[at]) - batch
                        done += batch
                        logs.append(f"➤ {done}/{amt} 구매 중... ({p_now:,}냥)")
                        log_box.code("\n".join(logs[-5:]))
                        time.sleep(0.05)
                    
                    doc.worksheet("Village_Data").update_cell(v_idx+2, list(v_data.keys()).index(at)+1, v_data[at])
                    st.success("매수 완료!")
                    st.rerun()

                if s_col.button("일괄 매도 시작"):
                    logs = []
                    done = 0
                    my_s = player['inventory'].get(at, 0)
                    target = min(amt, my_s)
                    while done < target:
                        cur_s = int(v_data[at])
                        p_now = calculate_price(at, cur_s, items_info, settings)
                        batch = min(100, target - done)
                        
                        player['money'] += (p_now * batch)
                        player['inventory'][at] -= batch
                        v_data[at] = int(v_data[at]) + batch
                        done += batch
                        logs.append(f"➤ {done}/{target} 판매 중... ({p_now:,}냥)")
                        log_box.code("\n".join(logs[-5:]))
                        time.sleep(0.05)
                    
                    doc.worksheet("Village_Data").update_cell(v_idx+2, list(v_data.keys()).index(at)+1, v_data[at])
                    st.success("매도 완료!")
                    st.rerun()

        with tab2: # 이동
            for v in st.session_state.villages:
                if v['village_name'] == player['pos'] or v['village_name'] == "용병 고용소": continue
                if st.button(f"{v['village_name']} 이동 (현재 {player['pos']})", key=f"mv_{v['village_name']}"):
                    player['pos'] = v['village_name']
                    st.rerun()

        with tab3: # 정보 및 저장
            if st.button("💾 서버에 데이터 저장"):
                ws = doc.worksheet("Player_Data")
                r_idx = st.session_state.slot_num + 1
                save_data = [st.session_state.slot_num, player['money'], player['pos'], 
                             json.dumps(player['mercs'], ensure_ascii=False), 
                             json.dumps(player['inventory'], ensure_ascii=False), 
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{r_idx}:F{r_idx}", [save_data])
                st.success("데이터베이스 저장 완료!")
