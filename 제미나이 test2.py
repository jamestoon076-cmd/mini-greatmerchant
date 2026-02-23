import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
from datetime import datetime

# --- 1. 페이지 설정 및 커스텀 스타일 ---
st.set_page_config(page_title="조선거상 온라인", page_icon="🏯", layout="wide")

st.markdown("""
<style>
    /* 메인 배경 및 폰트 설정 */
    .stApp { background-color: #f4f7f6; }
    
    /* 카드 스타일 UI */
    .stat-card {
        background: white; padding: 20px; border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-left: 5px solid #2e5077;
        margin-bottom: 20px;
    }
    
    /* 아이템 리스트 스타일 */
    .item-row {
        display: flex; justify-content: space-between; align-items: center;
        padding: 10px; border-bottom: 1px solid #eee;
    }
    
    /* 이동 버튼 스타일 */
    .city-card {
        background: #ffffff; border: 1px solid #e0e0e0; padding: 15px;
        border-radius: 10px; text-align: center; transition: 0.3s;
    }
    .city-card:hover { border-color: #2e5077; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
    
    /* 탭 메뉴 강조 */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #e1e4e8; border-radius: 5px 5px 0 0; padding: 10px 20px;
    }
    .stTabs [aria-selected="true"] { background-color: #2e5077 !important; color: white !important; }
</style>
""", unsafe_allow_html=True)

# --- 2. 데이터 연동 로직 ---
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
    try:
        # 설정 데이터 로드
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
        # 아이템 기본 정보 (기본가, 무게)
        items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        # 용병/밸런스 정보 (가격, 무게보너스)
        mercs_data = {r['name']: {'price': int(r['price']), 'weight_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
        
        regions = {}
        item_max_stocks = {name: 0 for name in items_info.keys()}
        for ws in doc.worksheets():
            if "_Village_Data" in ws.title:
                country = ws.title.replace("_Village_Data", "")
                rows = ws.get_all_records()
                regions[country] = rows
                for row in rows:
                    for item, stock in row.items():
                        if item in item_max_stocks:
                            try: 
                                val = int(stock)
                                item_max_stocks[item] = max(item_max_stocks[item], val)
                            except: pass
        
        player_slots = doc.worksheet("Player_Data").get_all_records()
        return doc, settings, items_info, mercs_data, regions, item_max_stocks, player_slots
    except Exception as e:
        st.error(f"데이터 로딩 오류: {e}")
        return None

# --- 3. 경제 엔진 (재고 기반 가격 변동 로직) ---
def calculate_dynamic_price(item_name, current_stock, item_max_stocks, items_info, settings):
    base_price = items_info[item_name]['base']
    max_stock = item_max_stocks.get(item_name, 100)
    # 변동성 수치 (Setting_Data의 volatility 사용, 기본값 5)
    volatility = settings.get('volatility', 5000) / 1000 
    
    curr_s = int(current_stock) if str(current_stock).isdigit() and int(current_stock) > 0 else 0
    if curr_s <= 0: return base_price * 10 # 품절 시 10배
    
    # 지수 함수를 이용한 가격 변동 공식
    ratio = max_stock / curr_s
    factor = math.pow(ratio, (volatility / 4))
    
    # 최소 0.5배 ~ 최대 20.0배 범위 제한
    return int(base_price * max(0.5, min(20.0, factor)))

# --- 4. 메인 실행부 ---
data = load_all_data()
if data:
    doc, settings, items_info, mercs_data, regions, item_max_stocks, player_slots = data
    if 'game_started' not in st.session_state: st.session_state.game_started = False

    # [화면 1: 슬롯 선택]
    if not st.session_state.game_started:
        st.markdown("<h1 style='text-align: center; color: #2e5077;'>🏯 거상: 대륙의 시작</h1>", unsafe_allow_html=True)
        
        cols = st.columns(3)
        for i, p in enumerate(player_slots):
            with cols[i % 3]:
                st.markdown(f"""<div class="stat-card">
                    <h3>💾 슬롯 {i+1}</h3>
                    <p>📍 <b>위치:</b> {p.get('pos','한양')}</p>
                    <p>💰 <b>소지금:</b> {int(p.get('money',0)):,}냥</p>
                    <small>최근 저장: {p.get('last_save','없음')}</small>
                </div>""", unsafe_allow_html=True)
                if st.button(f"슬롯 {i+1} 접속", key=f"btn_{i}", use_container_width=True):
                    st.session_state.player = {
                        'money': int(p.get('money', 10000)),
                        'pos': p.get('pos', '한양'),
                        'inventory': json.loads(p['inventory']) if p.get('inventory') else {},
                        'mercs': json.loads(p['mercs']) if p.get('mercs') else []
                    }
                    st.session_state.slot_num = i + 1
                    st.session_state.game_started = True
                    st.rerun()

    # [화면 2: 게임 본편]
    else:
        player = st.session_state.player
        
        # --- 사이드바: 플레이어 정보 및 상태 ---
        with st.sidebar:
            st.markdown("### 👤 상단 정보")
            st.metric("소지금", f"{player['money']:,} 냥")
            st.info(f"📍 위치: {player['pos']}")
            
            # 무게 계산 로직 (AttributeError 해결 버전)
            total_weight = sum(items_info[it]['w'] * q for it, q in player['inventory'].items() if it in items_info)
            
            bonus_w = 0
            for m in player['mercs']:
                if isinstance(m, dict): # 딕셔너리 형태일 때
                    bonus_w += m.get('weight_bonus', 0)
                elif isinstance(m, str) and m in mercs_data: # 이름(문자열) 형태일 때
                    bonus_w += mercs_data[m].get('weight_bonus', 0)
            
            max_weight = 1000 + bonus_w
            st.write(f"🎒 무게: {total_weight} / {max_weight}")
            st.progress(min(total_weight / max_weight, 1.0) if max_weight > 0 else 0)
            
            st.divider()
            if st.button("💾 데이터 저장", use_container_width=True, type="primary"):
                ws = doc.worksheet("Player_Data")
                r_idx = st.session_state.slot_num + 1
                save_data = [st.session_state.slot_num, player['money'], player['pos'], 
                             json.dumps(player['mercs'], ensure_ascii=False), 
                             json.dumps(player['inventory'], ensure_ascii=False), 
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{r_idx}:F{r_idx}", [save_data])
                st.success("안전하게 저장되었습니다!")

        # 메인 콘텐츠 탭
        tab_shop, tab_move, tab_inventory = st.tabs(["🛒 저잣거리", "🚩 팔도강산 이동", "👤 정보/인벤토리"])

        with tab_shop:
            # 현재 마을의 재고 데이터 찾기
            v_data = next((v for r in regions.values() for v in r if v['village_name'] == player['pos']), None)
            if v_data:
                st.subheader(f"🏠 {player['pos']} 시장 명부")
                cols = st.columns(2)
                for idx, item_name in enumerate(items_info.keys()):
                    stock = v_data.get(item_name, 0)
                    price = calculate_dynamic_price(item_name, stock, item_max_stocks, items_info, settings)
                    
                    with cols[idx % 2]:
                        with st.container(border=True):
                            c1, c2 = st.columns([2, 1])
                            c1.markdown(f"**{item_name}**\n\n가격: `{price:,}`냥 | 재고: `{stock}`개")
                            if c2.button("거래", key=f"t_{item_name}", use_container_width=True):
                                st.session_state.active_trade = {'name': item_name, 'price': price, 'stock': int(stock)}
                
                # 거래 모달 UI
                if 'active_trade' in st.session_state:
                    at = st.session_state.active_trade
                    st.markdown("---")
                    with st.expander(f"🤝 {at['name']} 거래 진행 중", expanded=True):
                        amt = st.number_input("거래 수량 입력", 1, 10000, 1)
                        total_cost = at['price'] * amt
                        
                        b_col, s_col, c_col = st.columns(3)
                        if b_col.button(f"{total_cost:,}냥 매수", use_container_width=True):
                            if player['money'] >= total_cost:
                                player['money'] -= total_cost
                                player['inventory'][at['name']] = player['inventory'].get(at['name'], 0) + amt
                                st.rerun()
                            else: st.error("소지금이 부족합니다!")
                            
                        owned = player['inventory'].get(at['name'], 0)
                        if s_col.button(f"{total_cost:,}냥 매도", use_container_width=True):
                            if owned >= amt:
                                player['money'] += total_cost
                                player['inventory'][at['name']] -= amt
                                st.rerun()
                            else: st.error("보유 수량이 부족합니다!")
                        
                        if c_col.button("거래 취소", use_container_width=True):
                            del st.session_state.active_trade
                            st.rerun()

        with tab_move:
            st.subheader("🚩 이동할 국가와 마을을 선택하세요")
            c_tabs = st.tabs(list(regions.keys()))
            for idx, country in enumerate(regions.keys()):
                with c_tabs[idx]:
                    m_cols = st.columns(4)
                    for v_idx, v in enumerate(regions[country]):
                        if v['village_name'] == player['pos']: continue
                        with m_cols[v_idx % 4]:
                            st.markdown(f'<div class="city-card"><b>{v["village_name"]}</b></div>', unsafe_allow_html=True)
                            if st.button("이동하기", key=f"mv_{v['village_name']}", use_container_width=True):
                                player['pos'] = v['village_name']
                                st.rerun()

        with tab_inventory:
            col_inv, col_merc = st.columns(2)
            with col_inv:
                st.subheader("📦 보유 아이템")
                for it, q in player['inventory'].items():
                    if q > 0:
                        st.markdown(f"""<div class="item-row">
                            <span>{it}</span>
                            <span><b>{q}</b> 개</span>
                        </div>""", unsafe_allow_html=True)
            with col_merc:
                st.subheader("⚔️ 고용 용병")
                if not player['mercs']:
                    st.write("고용한 용병이 없습니다.")
                for m in player['mercs']:
                    m_name = m if isinstance(m, str) else m.get('name', '알 수 없음')
                    st.info(f"🛡️ {m_name}")

else:
    st.error("구글 시트 데이터를 불러오지 못했습니다. st.secrets 설정을 확인해주세요.")
