import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime
import pandas as pd

# --- 1. 페이지 설정 및 세션 초기화 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="wide")

if 'trade_logs' not in st.session_state:
    st.session_state.trade_logs = []

# --- 2. 데이터 연동 (캐시) ---
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

# --- 3. 안전한 데이터 변환 함수 (핵심 에러 방지) ---
def safe_int(val, default=0):
    """문자열, None, 빈값을 안전하게 정수로 변환"""
    if val is None: return default
    s_val = str(val).strip().replace(',', '')
    if not s_val or s_val == "": return default
    try:
        return int(float(s_val))
    except:
        return default

def get_status(player, items_info, mercs_info):
    curr_w = sum(safe_int(count) * items_info.get(item, {}).get('w', 0) for item, count in player['inventory'].items())
    max_w = 1000 + sum(mercs_info.get(m, {}).get('w_bonus', 0) for m in player['mercs'])
    return curr_w, max_w

def calculate_price(item_name, stock, items_info, settings):
    base = items_info.get(item_name, {}).get('base', 100)
    vol = settings.get('volatility', 5000) / 1000
    curr_s = safe_int(stock, 5000)
    ratio = 5000 / max(1, curr_s) 
    return int(base * max(0.5, min(20.0, math.pow(ratio, (vol / 4)))))

def sync_engine(doc):
    if 'start_time' not in st.session_state: st.session_state.start_time = time.time()
    elapsed = int(time.time() - st.session_state.start_time)
    c_month = elapsed // 180
    if 'last_reset_month' not in st.session_state: st.session_state.last_reset_month = 0
    if c_month > st.session_state.last_reset_month:
        try:
            st.session_state.villages = doc.worksheet("Village_Data").get_all_records()
            st.session_state.last_reset_month = c_month
        except: pass
    return (c_month // 12)+1, (c_month % 12)+1, ((elapsed % 180) // 45)+1, 45-(elapsed % 45)

# --- 4. 메인 게임 로직 ---
static_data = load_static_db()
if static_data:
    settings, items_info, mercs_info = static_data
    doc = get_gsheet_client()
    year, month, week, remains = sync_engine(doc)

    if 'game_started' not in st.session_state or not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        slots = doc.worksheet("Player_Data").get_all_records()
        for i, p in enumerate(slots):
            if st.button(f"슬롯 {i+1} 접속 ({p['pos']})"):
                st.session_state.player = {
                    'money': safe_int(p['money']), 'pos': p['pos'],
                    'inventory': json.loads(p['inventory']) if p['inventory'] else {},
                    'mercs': json.loads(p['mercs']) if p['mercs'] else []
                }
                st.session_state.slot_num = i+1
                st.session_state.game_started = True
                st.rerun()
    else:
        player = st.session_state.player
        c_w, m_w = get_status(player, items_info, mercs_info)

        # 상단 실시간 UI
        st.markdown(f"""
        <div style="background:#1a1a1a; color:#0f0; padding:15px; border-radius:10px; border:2px solid #444;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <h2 style="margin:0; color:white;">📅 {year}년 {month}월 {week}주차</h2>
                <h3 style="margin:0; color:#ff0;">⏱️ {remains}초 남음</h3>
            </div>
            <p style="margin:10px 0 0 0;">📍 <b>{player['pos']}</b> | 💰 <b>{player['money']:,}냥</b> | ⚖️ <b>{c_w:,} / {m_w:,} 斤</b></p>
        </div>""", unsafe_allow_html=True)

        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 저잣거리", "🚩 이동", "⚔️ 용병 주막", "📊 통계 및 분석", "💾 저장"])

        with tab1: # 저잣거리
            if 'villages' not in st.session_state: st.session_state.villages = doc.worksheet("Village_Data").get_all_records()
            v_idx = next(i for i, v in enumerate(st.session_state.villages) if v['village_name'] == player['pos'])
            v_data = st.session_state.villages[v_idx]

            for item in items_info.keys():
                s_val = safe_int(v_data.get(item, 0))
                price = calculate_price(item, s_val, items_info, settings)
                my_s = safe_int(player['inventory'].get(item, 0))
                c1, c2, c3 = st.columns([2, 1, 1])
                c1.write(f"**{item}** (재고:{s_val:,} | 보유:{my_s:,})")
                c2.write(f"**{price:,}냥**")
                if c3.button("거래", key=f"t_{item}"): st.session_state.active_trade = item
            
            if 'active_trade' in st.session_state:
                at = st.session_state.active_trade
                st.divider()
                st.subheader(f"📦 {at} 매매 실행")
                amt = st.number_input("수량", 1, 100000, 100)
                b_col, s_col = st.columns(2)
                
                if st.session_state.trade_logs:
                    st.code("\n".join(st.session_state.trade_logs[-5:]))

                if b_col.button("일괄 매수 시작"):
                    done = 0
                    st.session_state.trade_logs = []
                    while done < amt:
                        curr_weight, max_weight = get_status(player, items_info, mercs_info)
                        cur_s = safe_int(v_data.get(at, 0))
                        p_now = calculate_price(at, cur_s, items_info, settings)
                        batch = min(100, amt - done)
                        if curr_weight + (batch * items_info[at]['w']) > max_weight:
                            batch = max(0, int((max_weight - curr_weight) // items_info[at]['w']))
                            if batch <= 0: st.session_state.trade_logs.append("🛑 무게 초과!"); break
                        if cur_s < batch: batch = cur_s
                        if player['money'] < (p_now * batch) or batch <= 0: break
                        player['money'] -= (p_now * batch)
                        player['inventory'][at] = player['inventory'].get(at, 0) + batch
                        v_data[at] = safe_int(v_data[at]) - batch
                        done += batch
                        st.session_state.trade_logs.append(f"✅ {done}/{amt}개 체결... (단가: {p_now:,}냥)")
                        time.sleep(0.01)
                    doc.worksheet("Village_Data").update_cell(v_idx+2, list(v_data.keys()).index(at)+1, v_data[at])
                    st.rerun()

        with tab2: # 이동
            st.subheader("🚩 팔도 강산 이동")
            cols = st.columns(3)
            villages_to_show = [v for v in st.session_state.villages if v['village_name'] != player['pos']]
            for idx, v in enumerate(villages_to_show):
                with cols[idx % 3]:
                    if st.button(f"🚩 {v['village_name']}", use_container_width=True, key=f"mv_{v['village_name']}"):
                        player['pos'] = v['village_name']
                        st.rerun()

        with tab4: # 통계 및 분석 (에러 수정 및 기능 강화)
            st.subheader("📊 상단 분석 보고서")
            current_v_idx = next(i for i, v in enumerate(st.session_state.villages) if v['village_name'] == player['pos'])
            cv_data = st.session_state.villages[current_v_idx]
            
            total_inv_val = 0
            inv_rows = []
            for item, count in player['inventory'].items():
                cnt = safe_int(count)
                if cnt <= 0: continue
                cur_s = safe_int(cv_data.get(item, 5000))
                p_now = calculate_price(item, cur_s, items_info, settings)
                val = cnt * p_now
                total_inv_val += val
                inv_rows.append({
                    "품목": item, "수량": f"{cnt:,}", "총무게": f"{cnt * items_info[item]['w']:,}斤",
                    "현재가": f"{p_now:,}냥", "평가액": f"{val:,}냥"
                })

            m1, m2, m3 = st.columns(3)
            m1.metric("💰 총 자산", f"{player['money'] + total_inv_val:,}냥")
            m2.metric("💵 현금", f"{player['money']:,}냥")
            m3.metric("📦 물품 시가", f"{total_inv_val:,}냥")
            
            st.markdown("#### 🎒 인벤토리 현황 및 순익 분석")
            if inv_rows: st.table(pd.DataFrame(inv_rows))
            else: st.info("보유 중인 물품이 없습니다.")

            st.divider()
            st.markdown("#### 🔍 전국 품목별 최적 도시 분석")
            market_rows = []
            for item in items_info.keys():
                all_prices = []
                for v in st.session_state.villages:
                    # [핵심 수정] 모든 마을의 재고를 안전하게 가져옴
                    s = safe_int(v.get(item, 5000))
                    p = calculate_price(item, s, items_info, settings)
                    all_prices.append((p, v['village_name']))
                
                all_prices.sort()
                min_p, min_v = all_prices[0]
                max_p, max_v = all_prices[-1]
                market_rows.append({
                    "품목": item, 
                    "가장 싼 곳": f"{min_v} ({min_p:,}냥)", 
                    "가장 비싼 곳": f"{max_v} ({max_p:,}냥)",
                    "수익률": f"{((max_p/min_p)-1)*100:.1f}%"
                })
            st.table(pd.DataFrame(market_rows))

        with tab5: # 저장
            if st.button("💾 데이터 저장"):
                ws = doc.worksheet("Player_Data")
                r_idx = st.session_state.slot_num + 1
                save_data = [st.session_state.slot_num, player['money'], player['pos'], 
                             json.dumps(player['mercs'], ensure_ascii=False), 
                             json.dumps(player['inventory'], ensure_ascii=False), 
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{r_idx}:F{r_idx}", [save_data])
                st.success("저장 완료!")
