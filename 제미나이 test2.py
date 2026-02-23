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
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
        items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
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
                            try: val = int(stock); item_max_stocks[item] = max(item_max_stocks[item], val)
                            except: pass
        
        player_slots = doc.worksheet("Player_Data").get_all_records()
        return doc, settings, items_info, mercs_data, regions, item_max_stocks, player_slots
    except Exception as e:
        st.error(f"데이터 로딩 오류: {e}"); return None

# --- 3. 경제 엔진 (재고 기반 가격 계산) ---
def calculate_dynamic_price(item_name, current_stock, item_max_stocks, items_info, settings):
    base_price = items_info[item_name]['base']
    max_stock = item_max_stocks.get(item_name, 100)
    volatility = settings.get('volatility', 5) / 10  # 변동성 계수
    
    if current_stock <= 0: return base_price * 10 # 품절 시 폭등
    
    # 지수 함수를 이용한 가격 변동: (최대재고 / 현재재고) ^ 변동성
    price_ratio = math.pow((max_stock / current_stock), (volatility / 2))
    final_price = base_price * price_ratio
    
    # 최소 0.5배 ~ 최대 20배 제한
    return int(max(base_price * 0.5, min(base_price * 20.0, final_price)))

# --- 4. 메인 실행부 ---
data = load_all_data()
if data:
    doc, settings, items_info, mercs_data, regions, item_max_stocks, player_slots = data
    if 'game_started' not in st.session_state: st.session_state.game_started = False

    # [화면 1: 슬롯 선택 (로그인)]
    if not st.session_state.game_started:
        st.markdown("<h1 style='text-align: center; color: #2e5077;'>🏯 조선거상 온라인</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center;'>접속하실 슬롯을 선택해주세요.</p>", unsafe_allow_html=True)
        
        cols = st.columns(3)
        for i, p in enumerate(player_slots):
            with cols[i % 3]:
                st.markdown(f"""<div class="stat-card">
                    <h3>슬롯 {i+1}</h3>
                    <p>📍 <b>위치:</b> {p.get('pos','한양')}</p>
                    <p>💰 <b>소지금:</b> {int(p.get('money',0)):,}냥</p>
                    <small>마지막 저장: {p.get('last_save')}</small>
                </div>""", unsafe_allow_html=True)
                if st.button(f"슬롯 {i+1} 접속", key=f"btn_{i}"):
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
        
        # 사이드바: 플레이어 정보창
        with st.sidebar:
            st.markdown("### 👤 상단 정보")
            st.metric("소지금", f"{player['money']:,} 냥")
            st.info(f"📍 현재 위치: {player['pos']}")
            
            # 무게 계산 (예시: 기본 1000 + 용병 보너스)
            total_weight = sum(items_info[it]['w'] * q for it, q in player['inventory'].items() if it in items_info)
            max_weight = 1000 + sum(m.get('weight_bonus', 0) for m in player['mercs'])
            st.write(f"🎒 무게: {total_weight} / {max_weight}")
            st.progress(min(total_weight / max_weight, 1.0))
            
            if st.button("💾 게임 저장", use_container_width=True):
                ws = doc.worksheet("Player_Data")
                r_idx = st.session_state.slot_num + 1
                save_data = [st.session_state.slot_num, player['money'], player['pos'], 
                             json.dumps(player['mercs'], ensure_ascii=False), 
                             json.dumps(player['inventory'], ensure_ascii=False), 
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{r_idx}:F{r_idx}", [save_data])
                st.success("저장 완료!")

        # 메인 화면 탭
        tab_shop, tab_move, tab_inventory = st.tabs(["🛒 시전(장터)", "🚩 팔도강산(이동)", "📦 내 보따리"])

        with tab_shop:
            v_data = next((v for r in regions.values() for v in r if v['village_name'] == player['pos']), None)
            if v_data:
                st.subheader(f"🏠 {player['pos']} 저잣거리")
                cols = st.columns(2)
                for idx, item_name in enumerate(items_info.keys()):
                    stock = int(v_data.get(item_name, 0))
                    price = calculate_dynamic_price(item_name, stock, item_max_stocks, items_info, settings)
                    
                    with cols[idx % 2]:
                        with st.container(border=True):
                            c1, c2 = st.columns([2, 1])
                            c1.markdown(f"**{item_name}** \n재고: `{stock}`개  \n가격: **{price:,}**냥")
                            if c2.button("거래하기", key=f"t_{item_name}", use_container_width=True):
                                st.session_state.active_trade = {'name': item_name, 'price': price, 'stock': stock}

                if 'active_trade' in st.session_state:
                    at = st.session_state.active_trade
                    st.divider()
                    st.markdown(f"#### 🤝 {at['name']} 거래창")
                    amt = st.select_slider("거래량 선택", options=range(1, min(at['stock'], 101) if at['stock'] > 0 else [1]), value=1)
                    
                    b_col, s_col, c_col = st.columns(3)
                    if b_col.button(f"{at['price']*amt:,}냥 매수", type="primary"):
                        if player['money'] >= at['price'] * amt:
                            player['money'] -= at['price'] * amt
                            player['inventory'][at['name']] = player['inventory'].get(at['name'], 0) + amt
                            st.toast(f"{at['name']} {amt}개 매수 완료!")
                            st.rerun()
                        else: st.error("돈이 부족합니다!")
                    
                    owned = player['inventory'].get(at['name'], 0)
                    if s_col.button(f"{at['price']*amt:,}냥 매도"):
                        if owned >= amt:
                            player['money'] += at['price'] * amt
                            player['inventory'][at['name']] -= amt
                            st.toast(f"{at['name']} {amt}개 매도 완료!")
                            st.rerun()
                        else: st.error("물건이 부족합니다!")
                    
                    if c_col.button("닫기"):
                        del st.session_state.active_trade
                        st.rerun()

        with tab_move:
            st.subheader("🚩 이동할 지역을 선택하세요")
            country_tabs = st.tabs(list(regions.keys()))
            for idx, (country, villages) in enumerate(regions.items()):
                with country_tabs[idx]:
                    cols = st.columns(4)
                    for v_idx, v in enumerate(villages):
                        if v['village_name'] == player['pos']: continue
                        with cols[v_idx % 4]:
                            st.markdown(f"""<div class="city-card"><b>{v['village_name']}</b></div>""", unsafe_allow_html=True)
                            if st.button("이동", key=f"goto_{v['village_name']}", use_container_width=True):
                                player['pos'] = v['village_name']
                                st.rerun()

        with tab_inventory:
            st.subheader("📦 보유 아이템")
            if not player['inventory'] or sum(player['inventory'].values()) == 0:
                st.write("보따리가 비어있습니다.")
            else:
                for it, q in player['inventory'].items():
                    if q > 0:
                        st.markdown(f"""
                        <div class="item-row">
                            <span>✨ <b>{it}</b></span>
                            <span>{q} 개 ({items_info[it]['w'] * q} 근)</span>
                        </div>
                        """, unsafe_allow_html=True)
