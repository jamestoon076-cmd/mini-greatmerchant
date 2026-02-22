import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime
import hashlib  # 추가
import uuid     # 추가

# --- 1. 페이지 설정 및 스타일 ---
st.set_page_config(
    page_title="조선거상 미니", 
    page_icon="🏯",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 모바일 최적화 CSS
st.markdown("""
<style>
    .stButton button { width: 100%; margin: 5px 0; padding: 15px; font-size: 18px; }
    .stTextInput input { font-size: 16px; padding: 10px; }
    div[data-testid="column"] { gap: 10px; }
    .price-up { color: #ff4b4b; font-weight: bold; }
    .price-down { color: #4b7bff; font-weight: bold; }
    .price-same { color: #808080; }
    .trade-progress {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
        font-family: monospace;
        font-size: 14px;
    }
    .trade-line {
        padding: 3px 0;
        border-bottom: 1px solid #e0e0e0;
    }
    .trade-complete {
        color: #00a65a;
        font-weight: bold;
        font-size: 16px;
        margin-top: 10px;
    }
    .warning-box {
        background-color: #fff3cd;
        color: #856404;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. 세션 관리 함수 (추가) ---
def get_device_id():
    """기기별 고유 ID 생성"""
    if 'device_id' not in st.session_state:
        # 세션 ID + 시간 + 랜덤값으로 고유 ID 생성
        session_key = f"{st.session_state.session_id}_{time.time()}_{uuid.uuid4()}"
        st.session_state.device_id = hashlib.md5(session_key.encode()).hexdigest()[:12]
    return st.session_state.device_id

def init_session():
    """세션 상태 초기화"""
    if 'session_id' not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if 'device_id' not in st.session_state:
        get_device_id()
    if 'game_started' not in st.session_state:
        st.session_state.game_started = False
    if 'player' not in st.session_state:
        st.session_state.player = None
    if 'market_data' not in st.session_state:
        st.session_state.market_data = None
    if 'settings' not in st.session_state:
        st.session_state.settings = None
    if 'items_info' not in st.session_state:
        st.session_state.items_info = None
    if 'villages' not in st.session_state:
        st.session_state.villages = None
    if 'merc_data' not in st.session_state:
        st.session_state.merc_data = None
    if 'stats' not in st.session_state:
        st.session_state.stats = {
            'total_bought': 0,
            'total_sold': 0,
            'total_spent': 0,
            'total_earned': 0,
            'trade_count': 0
        }
    if 'last_time_update' not in st.session_state:
        st.session_state.last_time_update = time.time()
    if 'events' not in st.session_state:
        st.session_state.events = []
    if 'last_update' not in st.session_state:
        st.session_state.last_update = time.time()
    if 'trade_log' not in st.session_state:
        st.session_state.trade_log = []
    if 'last_save_time' not in st.session_state:
        st.session_state.last_save_time = time.time()

# --- 3. 구글 시트 연결 함수 ---
@st.cache_resource
def connect_gsheet():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gspread"] 
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"❌ 시트 연결 에러: {e}")
        return None

# --- 4. 데이터 로드 함수 (수정됨) ---
@st.cache_data(ttl=10)
def load_game_data():
    doc = connect_gsheet()
    if not doc:
        return None, None, None, None, None, None
    
    try:
        # 설정 데이터 로드
        set_ws = doc.worksheet("Setting_Data")
        settings = {r['변수명']: float(r['값']) for r in set_ws.get_all_records()}
        
        # 아이템 정보 로드
        item_ws = doc.worksheet("Item_Data")
        items_info = {}
        for r in item_ws.get_all_records():
            if r.get('item_name'):
                name = str(r['item_name']).strip()
                items_info[name] = {
                    'base': int(r['base_price']),
                    'w': int(r['weight'])
                }
        
        # 용병 정보 로드
        bal_ws = doc.worksheet("Balance_Data")
        merc_data = {}
        for r in bal_ws.get_all_records():
            if r.get('name'):
                name = str(r['name']).strip()
                merc_data[name] = {
                    'price': int(r['price']),
                    'w_bonus': int(r.get('weight_bonus', 0))
                }
        
        # 마을 데이터 로드
        vil_ws = doc.worksheet("Village_Data")
        vil_vals = vil_ws.get_all_values()
        headers = [h.strip() for h in vil_vals[0]]
        
        villages = {}
        initial_stocks = {}
        
        for row in vil_vals[1:]:
            if not row or not row[0].strip():
                continue
            v_name = row[0].strip()
            try:
                x = int(row[1]) if len(row) > 1 and row[1] else 0
                y = int(row[2]) if len(row) > 2 and row[2] else 0
            except:
                x, y = 0, 0
            
            villages[v_name] = {'items': {}, 'x': x, 'y': y}
            initial_stocks[v_name] = {}
            
            if v_name != "용병 고용소":
                for i in range(3, len(headers)):
                    if headers[i] in items_info:
                        if len(row) > i and row[i].strip():
                            try:
                                stock = int(row[i])
                                villages[v_name]['items'][headers[i]] = stock
                                initial_stocks[v_name][headers[i]] = stock
                            except:
                                pass
        
        # 플레이어 데이터 로드 (device_id 추가)
        play_ws = doc.worksheet("Player_Data")
        slots = []
        for r in play_ws.get_all_records():
            if str(r.get('slot', '')).strip():
                slots.append({
                    'slot': int(r['slot']),
                    'money': int(r.get('money', 0)),
                    'pos': str(r.get('pos', '한양')),
                    'inv': json.loads(r.get('inventory', '{}')) if r.get('inventory') else {},
                    'mercs': json.loads(r.get('mercs', '[]')) if r.get('mercs') else [],
                    'week': int(r.get('week', 1)),
                    'month': int(r.get('month', 1)),
                    'year': int(r.get('year', 1)),
                    'last_save': r.get('last_save', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                    'device_id': r.get('device_id', '')  # device_id 추가
                })
        
        return settings, items_info, merc_data, villages, initial_stocks, slots
    
    except Exception as e:
        st.error(f"❌ 데이터 로드 에러: {e}")
        return None, None, None, None, None, None

# --- 5. 저장 함수 (수정됨) ---
def save_player_data(doc, player, stats, device_id):
    try:
        play_ws = doc.worksheet("Player_Data")
        all_records = play_ws.get_all_records()
        
        row_idx = None
        for i, record in enumerate(all_records, start=2):
            if record.get('slot') == player['slot']:
                row_idx = i
                break
        
        if row_idx:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            save_values = [
                player['slot'],
                player['money'],
                player['pos'],
                json.dumps(player['mercs'], ensure_ascii=False),
                json.dumps(player['inv'], ensure_ascii=False),
                now,
                player['week'],
                player['month'],
                player['year'],
                device_id  # device_id 저장
            ]
            # J열까지 업데이트
            play_ws.update(f'A{row_idx}:J{row_idx}', [save_values])
            return True
    except Exception as e:
        st.error(f"❌ 저장 실패: {e}")
        return False

# --- 6. 세션 저장 함수 (추가) ---
def save_to_session():
    """세션에 플레이어 데이터 저장"""
    st.session_state.player_data = {
        'player': st.session_state.player,
        'stats': st.session_state.stats,
        'device_id': get_device_id(),
        'last_save': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

def load_from_session():
    """세션에서 플레이어 데이터 로드"""
    if 'player_data' in st.session_state:
        data = st.session_state.player_data
        if data['device_id'] == get_device_id():
            st.session_state.player = data['player']
            st.session_state.stats = data['stats']
            return True
    return False

# --- 7. 자동 저장 함수 (추가) ---
def auto_save(doc):
    """5분마다 자동 저장"""
    if time.time() - st.session_state.last_save_time > 300:  # 5분
        if save_player_data(doc, st.session_state.player, st.session_state.stats, get_device_id()):
            st.toast("🔄 자동 저장 완료", icon="💾")
            st.session_state.last_save_time = time.time()
            save_to_session()

# --- 나머지 함수들은 원본 그대로 유지 ---
# update_game_time, get_time_display, update_prices, get_weight,
# calculate_max_purchase, process_buy, process_sell 함수들...

# --- 8. 메인 실행 (수정됨) ---
init_session()  # 세션 초기화
doc = connect_gsheet()

if doc:
    # [화면 1] 슬롯 선택 (수정됨)
    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        st.markdown("---")
        
        # 세션에 저장된 데이터 확인
        if load_from_session() and st.session_state.player:
            st.markdown(f"""
            <div class='warning-box'>
                <h3>📱 이전 접속 기기가 감지되었습니다!</h3>
                <p>슬롯 {st.session_state.player['slot']}에서 게임을 계속할 수 있습니다.</p>
            </div>
            """, unsafe_allow_html=True)
            
            col1, col2 = st.columns(2)
            if col1.button("✅ 이어하기", use_container_width=True):
                st.session_state.game_started = True
                st.rerun()
            if col2.button("🆕 새로 시작", use_container_width=True):
                if 'player_data' in st.session_state:
                    del st.session_state.player_data
                st.rerun()
            st.divider()
        
        settings, items_info, merc_data, villages, initial_stocks, slots = load_game_data()
        
        if slots:
            st.subheader("📋 세이브 슬롯 선택")
            for s in slots:
                # 다른 기기 접속 표시
                device_info = " (다른 기기)" if s['device_id'] and s['device_id'] != get_device_id() else ""
                with st.container():
                    st.info(f"**슬롯 {s['slot']}**{device_info} | 📍 {s['pos']} | 💰 {s['money']:,}냥 | 📅 {s['year']}년 {s['month']}월")
            
            slot_choice = st.text_input("슬롯 번호", value="1", key="slot_input")
            
            if st.button("🎮 게임 시작", use_container_width=True):
                selected = next((s for s in slots if str(s['slot']) == slot_choice), None)
                if selected:
                    # 다른 기기 접속 확인
                    if selected['device_id'] and selected['device_id'] != get_device_id():
                        st.warning("⚠️ 다른 기기에서 마지막으로 저장된 슬롯입니다. 계속하시겠습니까?")
                        col1, col2 = st.columns(2)
                        if col1.button("예, 계속합니다"):
                            pass
                        else:
                            st.stop()
                    
                    st.session_state.player = selected
                    st.session_state.settings = settings
                    st.session_state.items_info = items_info
                    st.session_state.merc_data = merc_data
                    st.session_state.villages = villages
                    st.session_state.initial_stocks = initial_stocks
                    st.session_state.last_time_update = time.time()
                    
                    market_data = {}
                    for v_name, v_data in villages.items():
                        if v_name != "용병 고용소":
                            market_data[v_name] = {}
                            for item_name, stock in v_data['items'].items():
                                market_data[v_name][item_name] = {
                                    'stock': stock,
                                    'price': 0
                                }
                    st.session_state.market_data = market_data
                    
                    # 세션에 저장
                    save_to_session()
                    
                    st.session_state.game_started = True
                    st.rerun()
                else:
                    st.error("❌ 존재하지 않는 슬롯입니다.")
    
    # [화면 2] 게임 메인 (수정됨)
    else:
        player = st.session_state.player
        settings = st.session_state.settings
        items_info = st.session_state.items_info
        merc_data = st.session_state.merc_data
        villages = st.session_state.villages
        market_data = st.session_state.market_data
        initial_stocks = st.session_state.initial_stocks
        
        # 자동 저장
        auto_save(doc)
        
        # 시간 업데이트
        current_time = time.time()
        if current_time - st.session_state.last_update > 10:
            player, events = update_game_time(player, settings, market_data, initial_stocks)
            if events:
                st.session_state.events = events
            st.session_state.last_update = current_time
        
        # 시세 업데이트
        update_prices(settings, items_info, market_data)
        cw, tw = get_weight(player, items_info, merc_data)
        
        # 이벤트 표시
        if st.session_state.events:
            for event_type, message in st.session_state.events:
                st.markdown(f"<div class='event-message'>{message}</div>", unsafe_allow_html=True)
            st.session_state.events = []
        
        # 상단 정보
        st.title(f"🏯 {player['pos']}")
        
        col1, col2, col3, col4 = st.columns(4)
        money_placeholder = col1.empty()
        money_placeholder.metric("💰 소지금", f"{player['money']:,}냥")
        
        weight_placeholder = col2.empty()
        weight_placeholder.metric("⚖️ 무게", f"{cw}/{tw}근")
        
        time_placeholder = col3.empty()
        time_placeholder.metric("📅 시간", get_time_display(player))
        
        trade_placeholder = col4.empty()
        trade_placeholder.metric("📊 거래", f"{st.session_state.stats['trade_count']}회")
        
        st.divider()
        
        # [기존 탭 코드는 그대로 유지, 저장 버튼만 수정]
        # ... (여기에 기존 tab1~tab5 코드 그대로 유지)
        
        # [탭5] 기타 부분의 저장 버튼 수정
        with tab5:
            st.subheader("⚙️ 게임 메뉴")
            
            # 이동 (그대로)
            # ... (이동 코드 그대로)
            
            st.divider()
            
            # 시간 정보 (그대로)
            st.write("**⏰ 시간 시스템**")
            remaining = 180 - int(time.time() - st.session_state.last_time_update)
            if remaining < 0:
                remaining = 0
            st.info(f"현실 3분 = 게임 1달\n\n다음 달까지: {remaining}초")
            
            st.divider()
            
            # 저장 버튼 (device_id 포함)
            if st.button("💾 저장", use_container_width=True):
                if save_player_data(doc, player, st.session_state.stats, get_device_id()):
                    save_to_session()
                    st.success("✅ 저장 완료!")
            
            # 종료
            if st.button("🚪 메인으로", use_container_width=True):
                st.session_state.game_started = False
                st.cache_data.clear()
                st.rerun()
