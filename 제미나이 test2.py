import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime
import pandas as pd

# --- 1. 페이지 설정 및 초기화 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="wide")

# 매매 로그 유지를 위한 세션 상태
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

# --- 3. 핵심 엔진 함수 ---
def get_status(player, items_info, mercs_info):
    # 인벤토리 무게 합계
    curr_w = sum(int(count) * items_info.get(item, {}).get('w', 0) for item, count in player['inventory'].items())
    # 기본 1000 + 용병 보너스
    max_w = 1000 + sum(mercs_info.get(m, {}).get('w_bonus', 0) for m in player['mercs'])
    return curr_w, max_w

def calculate_price(item_name, stock, items_info, settings):
    base = items_info.get(item_name, {}).get('base', 100)
    vol = settings.get('volatility', 5000) / 1000
    try:
        curr_s = int(str(stock).replace(',','')) if stock else 5000
    except: curr_s = 5000
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

# --- 4. 메인 실행부 ---
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
                    'money': int(p['money']), 'pos': p['pos'],
                    'inventory': json.loads(p['inventory']) if p['inventory'] else {},
                    'mercs': json.loads(p['mercs']) if p['mercs'] else []
                }
                st.session_state.slot_num = i+1
                st.session_state.game_started = True
                st.rerun()
    else:
        player = st.session_state.player
        c_w, m_w = get_status(player, items_info, mercs_info)

        # [상단 UI]
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
                s_raw = v_data.get(item, 0)
                s_val = int(s_raw) if str(s_raw).isdigit() else 0
                price = calculate_price(item, s_val, items_info, settings)
                my_s = int(player['inventory'].get(item, 0))
                
                c1, c2, c3 = st.columns([2, 1, 1])
                c1.write(f"**{item}** (재고:{s_val:,} | 보유:{my_s:,})")
                c2.write(f"**{price:,}냥**")
                if c3.button("거래", key=f"t_{item}"): st.session_state.active_trade = item
            
            if 'active_trade' in st.session_state:
                at = st.session_state.active_trade
                st.divider()
                st.subheader(f"📦 {at} 매매")
                amt = st.number_input("수량", 1, 100000, 100)
                b_col, s_col = st.columns(2)
                
                if st.session_state.trade_logs:
                    st.code("\n".join(st.session_state.trade_logs[-5:]))

                if b_col.button("일괄 매수 시작"):
                    done = 0
                    st.session_state.trade_logs = []
                    while done < amt:
                        curr_weight, max_weight = get_status(player, items_info, mercs_info)
                        cur_s = int(v_data[at])
                        p_now = calculate_price(at, cur_s, items_info, settings)
                        batch = min(100, amt - done)
                        
                        # 무게 체크
                        if curr_weight + (batch * items_info[at]['w']) > max_weight:
                            batch = max(0, int((max_weight - curr_weight) // items_info[at]['w']))
                            if batch <= 0: st.session_state.trade_logs.append("🛑 무게 한도 초과!"); break
                        
                        if cur_s < batch: batch = cur_s
                        if player['money'] < (p_now * batch) or batch <= 0: break

                        player['money'] -= (p_now * batch)
                        player['inventory'][at] = player['inventory'].get(at, 0) + batch
                        v_data[at] = int(v_data[at]) - batch
                        done += batch
                        st.session_state.trade_logs.append(f"✅ {done}/{amt}개 매수 완료... (단가: {p_now:,}냥)")
                        time.sleep(0.01)
                    doc.worksheet("Village_Data").update_cell(v_idx+2, list(v_data.keys()).index(at)+1, v_data[at])
                    st.rerun()

        with tab2: # 이동
            st.subheader("🚩 팔도 강산 이동")
            cols = st.columns(3)
            for idx, v in enumerate(st.session_state.villages):
                if v['village_name'] == player['pos']: continue
                with cols[idx % 3]:
                    if st.button(f"🚩 {v['village_name']}", use_container_width=True, key=f"mv_{v['village_name']}"):
                        player['pos'] = v['village_name']
                        st.rerun()

        with tab3: # 용병 고용/해고
            st.subheader("⚔️ 용병 주막")
            if player['pos'] != "용병 고용소": st.warning("용병 관리는 '용병 고용소'에서만 가능합니다.")
            for m_name, m_info in mercs_info.items():
                mc1, mc2, mc3 = st.columns([2, 1, 1])
                mc1.write(f"**{m_name}** (+{m_info['w_bonus']:,} 斤)")
                mc2.write(f"{m_info['price']:,}냥")
                if mc3.button("고용", key=f"buy_{m_name}"):
                    if player['money'] >= m_info['price']:
                        player['money'] -= m_info['price']
                        player['mercs'].append(m_name)
                        st.rerun()
            st.divider()
            for idx, m_name in enumerate(player['mercs']):
                rc1, rc2 = st.columns([3, 1])
                rc1.write(f"{idx+1}. **{m_name}**")
                if rc2.button("해고", key=f"fire_{idx}"):
                    player['money'] += int(mercs_info[m_name]['price'] * 0.5)
                    player['mercs'].pop(idx)
                    st.rerun()

        with tab4: # 통계 및 분석 (요청하신 기능)
            st.subheader("📊 상단 보고서")
            
            # 1. 인벤토리 가치 계산 (현재지 기준)
            total_inv_val = 0
            inv_data = []
            for item, count in player['inventory'].items():
                if count > 0:
                    cur_s = int(v_data.get(item, 5000))
                    p_now = calculate_price(item, cur_s, items_info, settings)
                    val = count * p_now
                    total_inv_val += val
                    inv_data.append({
                        "품목": item, "수량": f"{count:,}개", 
                        "무게": f"{count * items_info[item]['w']:,}斤",
                        "현재가": f"{p_now:,}냥", "평가액": f"{val:,}냥"
                    })
            
            m1, m2, m3 = st.columns(3)
            m1.metric("💰 총 자산", f"{player['money'] + total_inv_val:,}냥")
            m2.metric("💵 현금", f"{player['money']:,}냥")
            m3.metric("📦 물품 가치", f"{total_inv_val:,}냥")

            st.markdown("#### 🎒 내 인벤토리 현황")
            if inv_data: st.table(pd.DataFrame(inv_data))
            else: st.write("보유 물품이 없습니다.")

            st.divider()
            st.markdown("#### 🔍 전국 시세 분석 (최저가/최고가 도시)")
            market_list = []
            for item in items_info.keys():
                all_prices = []
                for v in st.session_state.villages:
                    s = int(v.get(item, 5000))
                    p = calculate_price(item, s, items_info, settings)
                    all_prices.append((p, v['village_name']))
                
                all_prices.sort()
                min_p, min_v = all_prices[0]
                max_p, max_v = all_prices[-1]
                market_list.append({
                    "품목": item, 
                    "최저가 도시": f"{min_v} ({min_p:,})", 
                    "최고가 도시": f"{max_v} ({max_p:,})",
                    "이익률": f"{((max_p/min_p)-1)*100:.1f}%"
                })
            st.table(pd.DataFrame(market_list))

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
