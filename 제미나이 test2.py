import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 페이지 설정 및 커스텀 스타일 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

st.markdown("""
<style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: white; padding: 10px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .price-up { color: #ff4b4b; font-weight: bold; }
    .price-down { color: #4b7bff; font-weight: bold; }
    .trade-container { background-color: white; padding: 15px; border-radius: 12px; border: 1px solid #e1e4e8; margin-bottom: 10px; }
    .village-card { padding: 10px; border-bottom: 1px solid #eee; }
</style>
""", unsafe_allow_html=True)

# --- 2. 데이터베이스 연결 (Google Sheets) ---
@st.cache_resource
def connect_db():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gspread"], scopes=scopes)
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"❌ DB 연결 실패: {e}")
        return None

def load_game_data(doc):
    try:
        # 설정 데이터
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
        
        # 아이템 및 용병 정보
        items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        mercs_data = {r['name']: {'price': int(r['price']), 'w_bonus': int(r.get('weight_bonus', 0))} for r in doc.worksheet("Balance_Data").get_all_records()}
        
        # 마을 데이터 로드 (국가별 탭 구분)
        regions = {}
        for ws in doc.worksheets():
            if "_Village_Data" in ws.title:
                country = ws.title.replace("_Village_Data", "")
                regions[country] = ws.get_all_records()
        
        # 플레이어 데이터
        player_slots = doc.worksheet("Player_Data").get_all_records()
        
        return settings, items_info, mercs_data, regions, player_slots
    except Exception as e:
        st.error(f"❌ 데이터 로드 실패: {e}")
        return None

# --- 3. 핵심 로직: 가격 변동 시스템 ---
def get_current_price(item_name, current_stock, items_info, settings):
    """가격변동개선.py의 재고 비율 로직 적용"""
    if item_name not in items_info: return 0
    
    base = items_info[item_name]['base']
    # 초기 재고 기준값 (DB에 없을 경우 기본 100)
    initial_stock = 100 
    
    if current_stock <= 0:
        return int(base * settings.get('max_price_rate', 3.0))
    
    stock_ratio = current_stock / initial_stock
    
    # 가격변동개선.py의 조건부 배율 적용
    if stock_ratio < 0.5:
        price_factor = 2.5
    elif stock_ratio < 1.0:
        price_factor = 1.8
    else:
        price_factor = 1.0
        
    price = int(base * price_factor)
    
    # 상하한선 제한
    min_p = int(base * settings.get('min_price_rate', 0.4))
    max_p = int(base * settings.get('max_price_rate', 3.0))
    return max(min_p, min(max_p, price))

# --- 4. 메인 게임 루프 ---
doc = connect_db()
if doc:
    data = load_game_data(doc)
    if data:
        settings, items_info, mercs_data, regions, player_slots = data
        
        if 'game_started' not in st.session_state:
            st.session_state.game_started = False

        # [화면 1: 슬롯 선택]
        if not st.session_state.game_started:
            st.title("🏯 조선거상: 대륙의 시작")
            cols = st.columns(len(player_slots[:3]))
            for i, p in enumerate(player_slots[:3]):
                with cols[i]:
                    st.markdown(f"""<div class="stMetric">
                    <b>💾 슬롯 {p['slot']}</b><br>
                    📍 {p.get('pos','한양')}<br>
                    💰 {int(p.get('money',0)):,}냥</div>""", unsafe_allow_html=True)
                    if st.button(f"{p['slot']}번 접속", key=f"btn_{i}"):
                        st.session_state.player = {
                            'slot': p['slot'],
                            'money': int(p.get('money', 10000)),
                            'pos': p.get('pos', '한양'),
                            'inv': json.loads(p['inventory']) if p.get('inventory') else {},
                            'mercs': json.loads(p['mercs']) if p.get('mercs') else [],
                            'year': int(p.get('year', 1592)), 'month': int(p.get('month', 1))
                        }
                        st.session_state.game_started = True
                        st.rerun()

        # [화면 2: 인게임 모드]
        else:
            p = st.session_state.player
            
            # 상단 상태바
            st.header(f"📍 {p['pos']}")
            c1, c2, c3 = st.columns(3)
            c1.metric("💰 소지금", f"{p['money']:,}냥")
            
            # 무게 계산
            curr_w = sum(p['inv'].get(it, 0) * items_info[it]['w'] for it in p['inv'] if it in items_info)
            max_w = 200 + sum(mercs_data[m]['w_bonus'] for m in p['mercs'] if m in mercs_data)
            c2.metric("⚖️ 무게", f"{curr_w}/{max_w}근")
            c3.metric("📅 일시", f"{p['year']}년 {p['month']}월")

            tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🚩 팔도강산", "⚔️ 용병단", "💾 시스템"])

            with tab1: # 거래 (가격변동개선 로직 적용)
                # 현재 마을의 재고 데이터 찾기
                v_row = next((r for rs in regions.values() for r in rs if r['village_name'] == p['pos']), None)
                
                if v_row:
                    for item_name, info in items_info.items():
                        # --- 수정 후 (안전한 방식) ---
                        raw_stock = v_row.get(item_name, 0)
                        
                        # 값이 없거나 공백 문자열인 경우 0으로 처리, 그 외에는 숫자로 변환
                        if raw_stock == "" or raw_stock is None:
                            stock = 0
                        else:
                            try:
                                stock = int(raw_stock)
                            except ValueError:
                                stock = 0 # 숫자가 아닌 값이 들어있을 경우 예외 처리
                        
                        price = get_current_price(item_name, stock, items_info, settings)
                        
                        with st.container():
                            col_info, col_trade = st.columns([2, 2])
                            with col_info:
                                st.markdown(f"**{item_name}**")
                                st.markdown(f"가격: `{price:,}냥` | 재고: `{stock}개`")
                            
                            with col_trade:
                                qty = st.number_input("수량", min_value=1, max_value=max(1, stock), key=f"q_{item_name}")
                                b_col, s_col = st.columns(2)
                                if b_col.button("매수", key=f"b_{item_name}"):
                                    if p['money'] >= price * qty and curr_w + (info['w'] * qty) <= max_w:
                                        p['money'] -= price * qty
                                        p['inv'][item_name] = p['inv'].get(item_name, 0) + qty
                                        st.success(f"{item_name} {qty}개 매수 완료")
                                        st.rerun()
                                    else: st.error("자금 또는 무게 부족")
                                
                                if s_col.button("매도", key=f"s_{item_name}"):
                                    if p['inv'].get(item_name, 0) >= qty:
                                        p['money'] += price * qty
                                        p['inv'][item_name] -= qty
                                        st.success(f"{item_name} {qty}개 매도 완료")
                                        st.rerun()
                                    else: st.error("수량 부족")
                    st.divider()

            with tab2: # 국가별 이동 (UI개선 탭 방식)
                countries = list(regions.keys())
                selected_country_tabs = st.tabs(countries)
                for i, country in enumerate(countries):
                    with selected_country_tabs[i]:
                        for v in regions[country]:
                            if v['village_name'] == p['pos']: continue
                            col_v, col_m = st.columns([3, 1])
                            col_v.write(f"**{v['village_name']}**")
                            if col_m.button("이동", key=f"move_{v['village_name']}"):
                                p['pos'] = v['village_name']
                                st.rerun()

            with tab3: # 용병 (가격변동개선 로직)
                st.subheader("⚔️ 용병 고용소")
                max_mercs = int(settings.get('max_mercenaries', 5))
                st.write(f"고용 현황: {len(p['mercs'])} / {max_mercs}")
                
                for m_name, m_info in mercs_data.items():
                    with st.container():
                        col1, col2 = st.columns([3, 1])
                        col1.write(f"**{m_name}** (💰 {m_info['price']:,}냥 | ⚖️ 무게 +{m_info['w_bonus']}근)")
                        if col2.button("고용", key=f"hire_{m_name}"):
                            if len(p['mercs']) < max_mercs and p['money'] >= m_info['price']:
                                p['money'] -= m_info['price']
                                p['mercs'].append(m_name)
                                st.rerun()
                            else: st.error("조건 부족")

            with tab4: # 저장 및 기타
                if st.button("💾 게임 데이터 저장", use_container_width=True):
                    ws = doc.worksheet("Player_Data")
                    row_idx = p['slot'] + 1
                    save_values = [
                        p['slot'], p['money'], p['pos'], 
                        json.dumps(p['mercs'], ensure_ascii=False),
                        json.dumps(p['inv'], ensure_ascii=False),
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        1, p['month'], p['year']
                    ]
                    ws.update(f'A{row_idx}:I{row_idx}', [save_values])
                    st.success("데이터가 클라우드에 저장되었습니다!")
                
                if st.button("🚪 타이틀로 돌아가기", use_container_width=True):
                    st.session_state.game_started = False
                    st.rerun()

