import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="wide")

st.markdown("""
<style>
    .stButton button { width: 100%; height: 3em; font-weight: bold; }
    .log-box { background-color: #1e1e1e; color: #00ff00; padding: 15px; border-radius: 5px; font-family: 'Courier New'; font-size: 0.9em; min-height: 200px; overflow-y: auto; }
    .inventory-card { background-color: #f1f3f5; padding: 10px; border-radius: 8px; border-left: 5px solid #2c3e50; margin-bottom: 5px; }
    .stat-header { background: #2c3e50; color: white; padding: 15px; border-radius: 10px; margin-bottom: 20px; }
</style>
""", unsafe_allow_html=True)

# --- 2. 데이터베이스 연동 ---
@st.cache_resource
def get_gsheet_client():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"DB 연결 실패: {e}")
        return None

def load_data():
    doc = get_gsheet_client()
    if not doc: return None
    try:
        # 엑셀 데이터 로드
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records()}
        items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        mercs_info = {r['name']: {'price': int(r['price']), 'w_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
        villages = doc.worksheet("Village_Data").get_all_records()
        player_slots = doc.worksheet("Player_Data").get_all_records()
        
        # 가격 계산을 위한 최대 재고 산출
        item_max_stocks = {name: 0 for name in items_info.keys()}
        for v in villages:
            for item in items_info.keys():
                try: item_max_stocks[item] = max(item_max_stocks[item], int(v.get(item, 0)))
                except: pass
        
        return doc, settings, items_info, mercs_info, villages, item_max_stocks, player_slots
    except Exception as e:
        st.error(f"데이터 파싱 오류: {e}")
        return None

# --- 3. 핵심 엔진 함수 ---
def calculate_price(item_name, current_stock, max_stock, items_info, settings):
    base = items_info[item_name]['base']
    vol = settings.get('volatility', 5000) / 1000
    stock_val = max(1, int(current_stock))
    ratio = max_stock / stock_val
    factor = math.pow(ratio, (vol / 4))
    return int(base * max(0.5, min(20.0, factor)))

def get_status(player, items_info, mercs_info):
    curr_w = sum(count * items_info.get(item, {}).get('w', 0) for item, count in player['inventory'].items())
    max_w = 1000 + sum(mercs_info.get(m, {}).get('w_bonus', 0) for m in player['mercs'])
    return curr_w, max_w

# --- 4. 메인 실행 루프 ---
data_bundle = load_data()
if data_bundle:
    doc, settings, items_info, mercs_info, villages, item_max_stocks, player_slots = data_bundle

    if 'game_started' not in st.session_state: st.session_state.game_started = False

    # [화면 A: 슬롯 선택]
    if not st.session_state.game_started:
        st.title("🏯 조선거상: 대륙의 시작")
        cols = st.columns(len(player_slots))
        for i, p in enumerate(player_slots):
            with cols[i]:
                st.markdown(f"""<div class="slot-container"><b>💾 슬롯 {i+1}</b><br>
                📍 위치: {p['pos']}<br>💰 {int(p['money']):,}냥</div>""", unsafe_allow_html=True)
                if st.button(f"슬롯 {i+1} 시작", key=f"s_{i}"):
                    st.session_state.player = {
                        'money': int(p['money']),
                        'pos': p['pos'],
                        'inventory': json.loads(p['inventory']) if p['inventory'] else {},
                        'mercs': json.loads(p['mercs']) if p['mercs'] else []
                    }
                    st.session_state.slot_num = i + 1
                    st.session_state.game_started = True
                    st.rerun()

    # [화면 B: 인게임]
    else:
        player = st.session_state.player
        curr_w, max_w = get_status(player, items_info, mercs_info)

        # 상단 정보 UI
        st.markdown(f"""<div class="stat-header">
            <h2 style='margin:0;'>📍 {player['pos']} 상단</h2>
            <b>소지금:</b> {player['money']:,}냥 | <b>무게:</b> {curr_w:,} / {max_w:,}
        </div>""", unsafe_allow_html=True)

        tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🚩 이동", "👤 상단정보", "⚔️ 주막"])

        with tab1: # 저잣거리 (실시간 매매 시스템)
            v_data = next((v for v in villages if v['village_name'] == player['pos']), None)
            if v_data:
                # 아이템 리스트 출력
                for item in items_info.keys():
                    stock = int(v_data.get(item, 0))
                    price = calculate_price(item, stock, item_max_stocks[item], items_info, settings)
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"**{item}** (재고: {stock:,})")
                    c2.write(f"시세: {price:,}냥")
                    if c3.button("거래 선택", key=f"t_{item}"):
                        st.session_state.active_trade = item
                
                # 상세 거래창
                if 'active_trade' in st.session_state:
                    at_item = st.session_state.active_trade
                    st.divider()
                    st.subheader(f"📦 {at_item} 거래 진행")
                    t_amt = st.number_input("거래 희망 수량", 1, 100000, 100, step=100)
                    
                    b_col, s_col = st.columns(2)
                    log_placeholder = st.empty()

                    # --- 매수 루프 ---
                    if b_col.button("일괄 매수 시작"):
                        total_cost, current_got = 0, 0
                        logs = [f"구매 수량 >> {t_amt}"]
                        while current_got < t_amt:
                            # 0. 실시간 가격 및 무게 체크
                            cur_s = int(v_data[at_item])
                            p_now = calculate_price(at_item, cur_s, item_max_stocks[at_item], items_info, settings)
                            i_w = items_info[at_item]['w']
                            
                            batch = min(100, t_amt - current_got)
                            
                            # 제한 조건 확인
                            if (get_status(player, items_info, mercs_info)[0] + (batch * i_w)) > max_w:
                                batch = max(0, int((max_w - get_status(player, items_info, mercs_info)[0]) // i_w))
                                if batch <= 0: logs.append("⚠️ 무게가 가득 찼습니다."); break
                            if cur_s < batch: batch = cur_s
                            if batch <= 0: logs.append("❌ 재고가 부족합니다."); break
                            if player['money'] < (p_now * batch): logs.append("❌ 자금이 부족합니다."); break

                            # 체결 실행
                            cost = p_now * batch
                            player['money'] -= cost
                            player['inventory'][at_item] = player['inventory'].get(at_item, 0) + batch
                            v_data[at_item] -= batch # 로컬 재고 갱신
                            current_got += batch
                            total_cost += cost
                            
                            logs.append(f"➤ {current_got}/{t_amt} 구매 중... (체결가: {p_now:,} / 평균가: {int(total_cost/current_got):,})")
                            log_placeholder.markdown(f'<div class="log-box">{"<br>".join(logs[-6:])}</div>', unsafe_allow_html=True)
                            time.sleep(0.3) # 0.3초 간격
                        
                        # DB 반영
                        doc.worksheet("Village_Data").update_cell(villages.index(v_data)+2, list(v_data.keys()).index(at_item)+1, v_data[at_item])
                        logs.append(f"✅ 총 {current_got}개 구매 완료 (재고 DB 동기화 완료)")
                        log_placeholder.markdown(f'<div class="log-box">{"<br>".join(logs[-7:])}</div>', unsafe_allow_html=True)

                    # --- 매도 루프 ---
                    if s_col.button("일괄 매도 시작"):
                        total_rev, current_sold = 0, 0
                        my_stock = player['inventory'].get(at_item, 0)
                        act_target = min(t_amt, my_stock)
                        logs = [f"판매 수량 >> {act_target}"]
                        while current_sold < act_target:
                            cur_s = int(v_data[at_item])
                            p_now = calculate_price(at_item, cur_s, item_max_stocks[at_item], items_info, settings)
                            
                            batch = min(100, act_target - current_sold)
                            rev = p_now * batch
                            
                            player['money'] += rev
                            player['inventory'][at_item] -= batch
                            v_data[at_item] += batch
                            current_sold += batch
                            total_rev += rev
                            
                            logs.append(f"➤ {current_sold}/{act_target} 판매 중... (체결가: {p_now:,})")
                            log_placeholder.markdown(f'<div class="log-box">{"<br>".join(logs[-6:])}</div>', unsafe_allow_html=True)
                            time.sleep(0.3)

                        doc.worksheet("Village_Data").update_cell(villages.index(v_data)+2, list(v_data.keys()).index(at_item)+1, v_data[at_item])
                        logs.append(f"✅ 총 {current_sold}개 판매 완료 (시세 DB 반영됨)")
                        log_placeholder.markdown(f'<div class="log-box">{"<br>".join(logs[-7:])}</div>', unsafe_allow_html=True)

        with tab2: # 이동 시스템
            st.subheader("🚩 이동할 마을 선택")
            for v in villages:
                if v['village_name'] == player['pos'] or v['village_name'] == "용병 고용소": continue
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{v['village_name']}**")
                if c2.button("이동하기", key=f"mv_{v['village_name']}"):
                    player['pos'] = v['village_name']
                    st.rerun()

        with tab3: # 상단정보 (인벤토리)
            st.subheader("👤 상단 인벤토리 정보")
            st.write(f"현재 감당 무게: **{curr_w:,} / {max_w:,}**")
            for item, count in player['inventory'].items():
                if count > 0:
                    i_w = items_info.get(item, {}).get('w', 0) * count
                    st.markdown(f"""<div class="inventory-card">
                        <b>{item}</b>: {count:,}개 <small>(총 {i_w:,} 무게)</small>
                    </div>""", unsafe_allow_html=True)
            
            st.divider()
            if st.button("💾 상단 전체 정보 저장"):
                ws = doc.worksheet("Player_Data")
                save_row = [st.session_state.slot_num, player['money'], player['pos'], 
                            json.dumps(player['mercs'], ensure_ascii=False), 
                            json.dumps(player['inventory'], ensure_ascii=False), 
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{st.session_state.slot_num+1}:F{st.session_state.slot_num+1}", [save_row])
                st.success("데이터베이스에 상단 정보가 저장되었습니다.")

        with tab4: # 주막 (용병 시스템)
            st.subheader("⚔️ 용병 고용 및 해고")
            st.info(f"용병은 상단의 무게 제한을 늘려줍니다. (현재 최대: {max_w:,})")
            
            # 고용 가능한 용병
            cols = st.columns(len(mercs_info))
            for i, (m_name, m_val) in enumerate(mercs_info.items()):
                with cols[i]:
                    st.write(f"**{m_name}**")
                    st.caption(f"가격: {m_val['price']:,}냥\n보너스: +{m_val['w_bonus']}")
                    if st.button("고용", key=f"buy_{m_name}"):
                        if player['money'] >= m_val['price']:
                            player['money'] -= m_val['price']
                            player['mercs'].append(m_name)
                            st.rerun()
            
            st.divider()
            st.write("📋 현재 고용 중인 용병")
            for idx, m_name in enumerate(player['mercs']):
                c1, c2 = st.columns([3, 1])
                c1.write(f"{idx+1}. {m_name}")
                if c2.button("해고", key=f"fire_{idx}"):
                    player['mercs'].pop(idx)
                    st.rerun()
