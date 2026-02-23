import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime
import time

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

# --- 2. DB 연결 및 데이터 로드 (최적화) ---
@st.cache_resource
def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gspread"], scopes=scopes)
    return gspread.authorize(creds)

@st.cache_data(ttl=600) # 10분간 데이터 유지 (API 호출 절약)
def load_all_game_data():
    client = get_gspread_client()
    doc = client.open("조선거상_DB")
    
    # 모든 시트 목록을 한 번만 가져옴 (APIError 방지 핵심)
    all_sheets = doc.worksheets()
    sheet_map = {s.title: s for s in all_sheets}
    
    def find_sheet(name):
        # 정확한 이름 혹은 포함된 이름 찾기
        if name in sheet_map: return sheet_map[name]
        for title, ws in sheet_map.items():
            if name in title: return ws
        return None

    # 데이터 추출
    settings = {r['변수명']: float(r['값']) for r in find_sheet("Setting_Data").get_all_records() if r.get('변수명')}
    items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in find_sheet("Item_Data").get_all_records()}
    mercs_db = {r['name']: {'price': int(r['price']), 'w_bonus': int(r.get('weight_bonus', 0))} for r in find_sheet("Balance_Data").get_all_records()}
    all_villages = find_sheet("Village_Data").get_all_records()
    player_data_raw = find_sheet("Player_Data").get_all_records()
    
    return settings, items_info, mercs_db, all_villages, player_data_raw

# --- 3. 핵심 유틸리티 ---
def calc_price(item, stock, items_info, settings):
    base = items_info[item]['base']
    initial_stock = 100 
    ratio = stock / initial_stock if stock > 0 else 0
    # 가격변동개선.py 로직
    if ratio < 0.5: factor = 2.5
    elif ratio < 1.0: factor = 1.8
    else: factor = 1.0
    return int(base * factor)

# --- 4. 게임 실행 로직 ---
try:
    settings, items_info, mercs_db, all_villages, player_data_raw = load_all_game_data()
except Exception as e:
    st.error("📡 데이터베이스를 불러오는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
    st.stop()

# 플레이어 세션 초기화
if 'player' not in st.session_state:
    p_init = player_data_raw[0] # 1번 슬롯
    st.session_state.player = {
        'slot': p_init['slot'], 'money': int(p_init['money']), 'pos': p_init['pos'],
        'inv': json.loads(p_init['inventory']) if p_init['inventory'] else {},
        'mercs': json.loads(p_init['mercs']) if p_init['mercs'] else []
    }

p = st.session_state.player

# --- UI 상단바 ---
curr_w = sum(p['inv'].get(i, 0) * items_info[i]['w'] for i in p['inv'] if i in items_info)
max_w = 200 + sum(mercs_db[m]['w_bonus'] for m in p['mercs'] if m in mercs_db)

st.title("🏯 조선거상 미니")
st.info(f"📍 {p['pos']} | 💰 {p['money']:,}냥 | ⚖️ {curr_w}/{max_w}근")

# 탭 구성 (UI개선.py 스타일)
tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🚩 이동", "🎒 상단 정보", "⚔️ 고용소"])

with tab1: # 저잣거리
    if p['pos'] == "용병 고용소":
        st.warning("이곳은 상점이 없습니다. 이동 탭을 이용해 마을로 가세요.")
    else:
        v_data = next((v for v in all_villages if v['village_name'] == p['pos']), None)
        for item, info in items_info.items():
            stock = int(v_data.get(item, 0)) if v_data.get(item) else 0
            price = calc_price(item, stock, items_info, settings)
            with st.expander(f"{item} (가격: {price:,}냥 | 재고: {stock})"):
                qty = st.number_input(f"수량", 1, 100, key=f"q_{item}")
                c1, c2 = st.columns(2)
                if c1.button("매수", key=f"b_{item}"):
                    if p['money'] >= price * qty and curr_w + (info['w'] * qty) <= max_w:
                        p['money'] -= price * qty
                        p['inv'][item] = p['inv'].get(item, 0) + qty
                        st.rerun()
                if c2.button("매도", key=f"s_{item}"):
                    if p['inv'].get(item, 0) >= qty:
                        p['money'] += price * qty
                        p['inv'][item] -= qty
                        st.rerun()

with tab2: # 이동
    st.subheader("🚩 팔도강산 이동")
    for v in all_villages:
        if v['village_name'] == p['pos']: continue
        col_v, col_b = st.columns([3, 1])
        col_v.write(f"**{v['village_name']}**")
        if col_b.button("이동", key=f"mv_{v['village_name']}"):
            p['pos'] = v['village_name']
            st.rerun()

with tab3: # 상단 정보 (해고 기능 포함)
    st.subheader("🎒 내 상단 관리")
    col1, col2 = st.columns(2)
    with col1:
        st.write("**[내 물건]**")
        for it, count in p['inv'].items():
            if count > 0: st.write(f"- {it}: {count}개")
    with col2:
        st.write("**[내 용병단]**")
        for idx, m_name in enumerate(p['mercs']):
            st.write(f"👤 {m_name}")
            if st.button("해고", key=f"fire_{idx}"):
                if curr_w > max_w - mercs_db[m_name]['w_bonus']:
                    st.error("무게 초과로 해고 불가!")
                else:
                    p['mercs'].pop(idx)
                    st.rerun()
    
    st.divider()
    if st.button("💾 데이터 저장"):
        client = get_gspread_client()
        play_ws = client.open("조선거상_DB").worksheet("Player_Data")
        save_val = [p['slot'], p['money'], p['pos'], json.dumps(p['mercs'], ensure_ascii=False), json.dumps(p['inv'], ensure_ascii=False), datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
        play_ws.update(f"A{p['slot']+1}:F{p['slot']+1}", [save_val])
        st.success("저장 완료!")

with tab4: # 고용소
    if p['pos'] == "용병 고용소":
        st.subheader("⚔️ 용병 고용소")
        for m_name, m_info in mercs_db.items():
            c1, c2 = st.columns([3, 1])
            c1.write(f"**{m_name}** ({m_info['price']:,}냥)")
            if c2.button("고용", key=f"h_{m_name}"):
                if len(p['mercs']) < settings['max_mercenaries'] and p['money'] >= m_info['price']:
                    p['money'] -= m_info['price']
                    p['mercs'].append(m_name)
                    st.rerun()
                else: st.error("고용 불가!")
    else:
        st.info("💡 용병 고용소로 이동하면 용병을 고용할 수 있습니다.")
