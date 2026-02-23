import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 페이지 설정 및 스타일 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

st.markdown("""
<style>
    .slot-card { background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 10px; border-left: 5px solid #4b7bff; }
    .stButton button { width: 100%; margin: 5px 0; padding: 12px; font-size: 16px; }
</style>
""", unsafe_allow_html=True)

# --- 2. 데이터 연동 로직 ---
@st.cache_resource
def connect_gsheet():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
                                                     ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("조선거상_DB")
    except: return None

def load_game_data():
    doc = connect_gsheet()
    if not doc: return None
    
    # 1) 설정 및 아이템 정보 
    settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
    items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
    
    # 2) 국가별 마을 데이터 자동 그룹화 (Korea_Village_Data 등) 
    regions = {}
    item_max_stocks = {name: 0 for name in items_info.keys()}
    for ws in doc.worksheets():
        if "_Village_Data" in ws.title:
            region_name = ws.title.replace("_Village_Data", "")
            data = ws.get_all_records()
            regions[region_name] = data
            for row in data:
                for item, stock in row.items():
                    if item in item_max_stocks:
                        item_max_stocks[item] = max(item_max_stocks[item], int(stock or 0))
    
    # 3) 슬롯 데이터 (플레이어 정보) 
    player_recs = doc.worksheet("Player_Data").get_all_records()
    return doc, settings, items_info, regions, item_max_stocks, player_recs

# --- 3. 게임 실행부 ---
res = load_game_data()
if res:
    doc, settings, items_info, regions, item_max_stocks, player_recs = res

    if 'game_started' not in st.session_state: st.session_state.game_started = False

    # --- [초기 화면: 슬롯 정보 출력] ---
    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        st.subheader("불러올 슬롯을 선택하세요")
        
        for i in range(3):
            p = player_recs[i]
            slot_num = i + 1
            # 슬롯 정보 가공
            money = f"{int(p['money']):,}냥" if p['money'] else "정보 없음"
            pos = p['pos'] if p['pos'] else "정보 없음"
            save_time = p['last_save'] if p['last_save'] else "기록 없음"
            
            # 슬롯 카드 출력
            st.markdown(f"""
            <div class="slot-card">
                <b>💾 슬롯 {slot_num}</b><br>
                📍 위치: {pos} | 💰 소지금: {money}<br>
                🕒 마지막 저장: {save_time}
            </div>
            """, unsafe_allow_html=True)
            
            if st.button(f"슬롯 {slot_num} 시작", key=f"start_{slot_num}"):
                st.session_state.player = {
                    'money': int(p['money']) if p['money'] else 10000,
                    'pos': p['pos'] if p['pos'] else "한양",
                    'inventory': json.loads(p['inventory']) if p['inventory'] else {},
                    'mercs': json.loads(p['mercs']) if p['mercs'] else []
                }
                st.session_state.stats = {'slot': slot_num}
                st.session_state.game_started = True
                st.rerun()

    # --- [게임 화면] ---
    else:
        player = st.session_state.player
        curr_pos = player['pos']
        
        st.header(f"📍 {curr_pos}")
        st.metric("💰 내 자본", f"{player['money']:,}냥")

        tab1, tab2, tab3 = st.tabs(["🛒 장터", "🚩 이동", "👤 정보"])

        with tab1: # 장터 로직 (생략 - 기존과 동일)
            st.write("아이템 거래가 가능합니다.")

        with tab2:
            st.subheader("🚩 국가별 이동 목록")
            # 💡 [핵심] 국가별로 탭을 나누고 그 안에 리스트 생성
            region_tabs = st.tabs(list(regions.keys()))
            
            for idx, r_name in enumerate(regions.keys()):
                with region_tabs[idx]:
                    with st.container(height=350): # 스크롤 박스
                        for v in regions[r_name]:
                            v_name = v['village_name']
                            if v_name == curr_pos: continue
                            
                            # 현재 좌표 찾기
                            c_x, c_y = 100, 100
                            for r in regions.values():
                                for village in r:
                                    if village['village_name'] == curr_pos:
                                        c_x, c_y = village['x'], village['y']
                            
                            dist = math.sqrt((c_x-v['x'])**2 + (c_y-v['y'])**2)
                            cost = int(dist * settings.get('travel_cost', 15))
                            
                            col1, col2 = st.columns([3, 1])
                            col1.write(f"**{v_name}** ({int(dist)}리 / {cost}냥)")
                            if col2.button("이동", key=f"m_{r_name}_{v_name}"):
                                if player['money'] >= cost:
                                    player['money'] -= cost
                                    player['pos'] = v_name
                                    st.rerun()

        with tab3:
            if st.button("💾 데이터 저장", key="save_game"):
                ws = doc.worksheet("Player_Data")
                data = [st.session_state.stats['slot'], player['money'], player['pos'], 
                        json.dumps(player['mercs'], ensure_ascii=False), 
                        json.dumps(player['inventory'], ensure_ascii=False), 
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{st.session_state.stats['slot']+1}:F{st.session_state.stats['slot']+1}", [data])
                st.success("성공적으로 저장되었습니다!")
