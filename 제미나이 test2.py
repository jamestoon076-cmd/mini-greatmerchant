import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

# --- 2. 데이터베이스 연결 및 유틸리티 함수 ---
@st.cache_resource
def connect_db():
    try:
        # Streamlit Secrets에 저장된 gspread 인증 정보 사용
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gspread"], scopes=scopes)
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"❌ DB 연결 실패: {e}")
        return None

def get_ws(doc, name):
    """시트 이름이 정확하지 않아도 포함된 이름을 찾아주는 안전 함수"""
    try: return doc.worksheet(name)
    except:
        for s in doc.worksheets():
            if name in s.title: return s
        return None

def safe_int(value, default=0):
    if value == "" or value is None: return default
    try: return int(float(value))
    except: return default

# --- 3. 가격 변동 로직 (가격변동개선.py 기준) ---
def calc_price(item, stock, items_info, settings):
    if item not in items_info: return 0
    base = items_info[item]['base']
    # 재고가 적을수록 가격 폭등 (기준 재고 100)
    initial_stock = 100 
    ratio = stock / initial_stock if stock > 0 else 0
    
    if ratio < 0.5: factor = 2.5
    elif ratio < 1.0: factor = 1.8
    else: factor = 1.0
    
    return int(base * factor)

# --- 4. 메인 게임 엔진 ---
doc = connect_db()

if doc:
    # 데이터 프리로딩
    set_ws = get_ws(doc, "Setting_Data")
    item_ws = get_ws(doc, "Item_Data")
    vill_ws = get_ws(doc, "Village_Data")
    merc_ws = get_ws(doc, "Balance_Data")
    play_ws = get_ws(doc, "Player_Data")

    # 기본 정보 딕셔너리화
    settings = {r['변수명']: float(r['값']) for r in set_ws.get_all_records() if r.get('변수명')}
    items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in item_ws.get_all_records()}
    mercs_db = {r['name']: {'price': int(r['price']), 'w_bonus': int(r.get('weight_bonus', 0))} for r in merc_ws.get_all_records()}
    all_villages = vill_ws.get_all_records()

    # 플레이어 세션 초기화 (1번 슬롯 기준)
    if 'player' not in st.session_state:
        p_data = play_ws.get_all_records()[0]
        st.session_state.player = {
            'slot': p_data['slot'],
            'money': int(p_data['money']),
            'pos': p_data['pos'],
            'inv': json.loads(p_data['inventory']) if p_data['inventory'] else {},
            'mercs': json.loads(p_data['mercs']) if p_data['mercs'] else []
        }

    p = st.session_state.player

    # --- UI 레이아웃 시작 ---
    st.title("🏯 조선거상 미니")

    # [상단 정보 바]
    curr_w = sum(p['inv'].get(i, 0) * items_info[i]['w'] for i in p['inv'] if i in items_info)
    max_w = 200 + sum(mercs_db[m]['w_bonus'] for m in p['mercs'] if m in mercs_db)
    
    st.markdown(f"""
    <div style="background-color: #ffffff; padding: 15px; border-radius: 12px; border: 1px solid #ddd; margin-bottom: 15px;">
        <span style="font-size: 1.1em;">📍 <b>{p['pos']}</b></span> | 
        <span style="color: #2e7d32;">💰 <b>{p['money']:,}냥</b></span> | 
        <span style="color: #1565c0;">⚖️ <b>{curr_w}/{max_w}근</b></span>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🚩 이동", "🎒 상단 정보", "⚔️ 고용소"])

    # [TAB 1: 저잣거리]
    with tab1:
        if p['pos'] == "용병 고용소":
            st.info("💡 이곳은 고용소입니다. 물건을 거래하려면 이동 탭에서 마을로 가세요.")
        else:
            v_data = next((v for v in all_villages if v['village_name'] == p['pos']), None)
            st.subheader(f"🏬 {p['pos']} 시장")
            for item in items_info.keys():
                stock = safe_int(v_data.get(item, 0))
                price = calc_price(item, stock, items_info, settings)
                
                with st.expander(f"{item} (가격: {price:,}냥 | 재고: {stock})"):
                    qty = st.number_input(f"수량 선택", 1, 1000, key=f"q_{item}")
                    col1, col2 = st.columns(2)
                    if col1.button(f"매수", key=f"buy_{item}", use_container_width=True):
                        if p['money'] >= price * qty and curr_w + (items_info[item]['w'] * qty) <= max_w:
                            p['money'] -= price * qty
                            p['inv'][item] = p['inv'].get(item, 0) + qty
                            st.rerun()
                        else: st.error("자금 또는 무게가 부족합니다!")
                    
                    if col2.button(f"매도", key=f"sel_{item}", use_container_width=True):
                        if p['inv'].get(item, 0) >= qty:
                            p['money'] += price * qty
                            p['inv'][item] -= qty
                            st.rerun()
                        else: st.error("팔 물건이 부족합니다!")

    # [TAB 2: 이동]
    with tab2:
        st.subheader("🚩 팔도강산 이동")
        for v in all_villages:
            if v['village_name'] == p['pos']: continue
            with st.container():
                c_v, c_b = st.columns([3, 1])
                c_v.write(f"**{v['village_name']}**")
                if c_b.button("이동", key=f"mv_{v['village_name']}"):
                    p['pos'] = v['village_name']
                    st.rerun()

    # [TAB 3: 상단 정보 (해고 기능 포함)]
    with tab3:
        st.subheader("🎒 내 상단 관리")
        col_inv, col_merc = st.columns(2)
        
        with col_inv:
            st.write("**[소지 물품]**")
            for it, count in p['inv'].items():
                if count > 0: st.write(f"📦 {it}: {count}개")
        
        with col_merc:
            st.write("**[용병단]**")
            for idx, m_name in enumerate(p['mercs']):
                st.write(f"👤 {m_name}")
                if st.button("해고", key=f"fire_{idx}"):
                    # 해고 시 무게 체크
                    new_max_w = max_w - mercs_db[m_name]['w_bonus']
                    if curr_w > new_max_w:
                        st.error("짐이 무거워 용병을 보낼 수 없습니다!")
                    else:
                        p['mercs'].pop(idx)
                        st.rerun()
        
        st.divider()
        if st.button("💾 데이터 저장", use_container_width=True):
            save_val = [p['slot'], p['money'], p['pos'], json.dumps(p['mercs'], ensure_ascii=False), json.dumps(p['inv'], ensure_ascii=False), datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
            play_ws.update(f"A{p['slot']+1}:F{p['slot']+1}", [save_val])
            st.success("성공적으로 저장되었습니다!")

    # [TAB 4: 고용소]
    with tab4:
        if p['pos'] == "용병 고용소":
            st.subheader("⚔️ 용병 고용")
            for m_name, info in mercs_db.items():
                with st.container():
                    c1, c2 = st.columns([3, 1])
                    c1.write(f"**{m_name}**\n\n(💰 {info['price']:,}냥 | ⚖️ +{info['w_bonus']}근)")
                    if c2.button("고용", key=f"h_{m_name}"):
                        if len(p['mercs']) < settings['max_mercenaries'] and p['money'] >= info['price']:
                            p['money'] -= info['price']
                            p['mercs'].append(m_name)
                            st.rerun()
                        else: st.error("고용 불가!")
        else:
            st.warning("⚠️ 용병 고용소에서만 이용 가능합니다.")
            if st.button("용병 고용소로 즉시 이동"):
                p['pos'] = "용병 고용소"
                st.rerun()
