import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
from datetime import datetime

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

# CSS: 슬롯 디자인 및 스크롤바 최적화
st.markdown("""
<style>
    .slot-container {
        background-color: #ffffff; padding: 20px; border-radius: 15px;
        border: 1px solid #e1e4e8; margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    .scroll-box { max-height: 400px; overflow-y: auto; padding: 10px; border: 1px solid #eee; }
    .stButton button { width: 100%; height: 50px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 2. 데이터 연동 (캐싱 처리로 로딩 에러 방지) ---
@st.cache_resource
def get_gsheet_client():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("조선거상_DB")
    except: return None

def load_all_data():
    doc = get_gsheet_client()
    if not doc: return None
    
    # 세팅 및 아이템
    settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
    items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
    
    # 국가별 마을 데이터 동적 로드 (Korea_Village_Data, Japan_Village_Data 등 자동 감지)
    regions = {}
    for ws in doc.worksheets():
        if "_Village_Data" in ws.title:
            country = ws.title.replace("_Village_Data", "")
            regions[country] = ws.get_all_records()
            
    # 슬롯 정보
    player_slots = doc.worksheet("Player_Data").get_all_records()
    return doc, settings, items_info, regions, player_slots

# --- 3. 메인 로직 ---
data = load_all_data()
if not data:
    st.error("스프레드시트 연결에 실패했습니다. secrets 설정을 확인하세요.")
else:
    doc, settings, items_info, regions, player_slots = data

    if 'game_started' not in st.session_state:
        st.session_state.game_started = False

    # --- [화면 1: 슬롯 선택 (정보 출력)] ---
    if not st.session_state.game_started:
        st.title("🏯 거상: 대륙의 시작")
        st.write("진행하실 슬롯을 선택하세요.")

        for i, p in enumerate(player_slots):
            slot_id = i + 1
            with st.container():
                # 데이터가 비어있을 경우 초기값 설정
                money = f"{int(p['money']):,}냥" if p.get('money') else "10,000냥 (신규)"
                pos = p.get('pos') if p.get('pos') else "한양"
                last_save = p.get('last_save') if p.get('last_save') else "기록 없음"
                
                st.markdown(f"""
                <div class="slot-container">
                    <h3 style='margin:0;'>💾 슬롯 {slot_id}</h3>
                    <p style='margin:5px 0;'>📍 현재 위치: <b>{pos}</b> | 💰 소지금: <b>{money}</b></p>
                    <small style='color:gray;'>마지막 저장: {last_save}</small>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button(f"슬롯 {slot_id} 접속", key=f"btn_slot_{slot_id}"):
                    st.session_state.player = {
                        'money': int(p['money']) if p.get('money') else 10000,
                        'pos': pos,
                        'inventory': json.loads(p['inventory']) if p.get('inventory') else {},
                        'mercs': json.loads(p['mercs']) if p.get('mercs') else []
                    }
                    st.session_state.slot_num = slot_id
                    st.session_state.game_started = True
                    st.rerun()

    # --- [화면 2: 인게임 메인] ---
    else:
        player = st.session_state.player
        st.header(f"📍 {player['pos']}")
        st.subheader(f"💰 {player['money']:,}냥")

        tab_market, tab_move, tab_info = st.tabs(["🛒 저잣거리", "🚩 팔도강산 이동", "👤 상단 정보"])

        with tab_market:
            st.info("장터 기능 (생략 가능 - 현재 이동 시스템 집중)")

        with tab_move:
            st.subheader("🚩 이동할 국가와 마을을 선택하세요")
            
            # 💡 국가별 탭 자동 생성
            country_list = list(regions.keys())
            if not country_list:
                st.warning("등록된 마을 시트가 없습니다. (예: Korea_Village_Data)")
            else:
                selected_tabs = st.tabs(country_list)
                
                # 현재 플레이어 좌표 찾기
                cur_x, cur_y = 100, 100
                for r_data in regions.values():
                    for v in r_data:
                        if v['village_name'] == player['pos']:
                            cur_x, cur_y = v['x'], v['y']

                for i, country in enumerate(country_list):
                    with selected_tabs[i]:
                        # 💡 스크롤 가능한 컨테이너 (마을이 많아도 OK)
                        with st.container(height=400):
                            for v in regions[country]:
                                v_name = v['village_name']
                                if v_name == player['pos']: continue
                                
                                dist = math.sqrt((cur_x - v['x'])**2 + (cur_y - v['y'])**2)
                                cost = int(dist * settings.get('travel_cost', 15))
                                
                                col_name, col_btn = st.columns([3, 1])
                                col_name.write(f"**{v_name}**\n({int(dist)}리 / {cost}냥)")
                                if col_btn.button("이동", key=f"mv_{country}_{v_name}"):
                                    if player['money'] >= cost:
                                        player['money'] -= cost
                                        player['pos'] = v_name
                                        st.success(f"✅ {v_name}로 이동!")
                                        st.rerun()
                                    else:
                                        st.error("돈이 부족합니다!")

        with tab_info:
            if st.button("💾 현재 상태 저장", key="save_final"):
                ws = doc.worksheet("Player_Data")
                # 슬롯 번호에 맞는 행에 업데이트 (A2, A3, A4...)
                row_idx = st.session_state.slot_num + 1
                save_data = [
                    st.session_state.slot_num,
                    player['money'],
                    player['pos'],
                    json.dumps(player['mercs'], ensure_ascii=False),
                    json.dumps(player['inventory'], ensure_ascii=False),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ]
                ws.update(f"A{row_idx}:F{row_idx}", [save_data])
                st.success("저장되었습니다!")
