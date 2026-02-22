import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime
import hashlib
import uuid

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
    .success-box {
        background-color: #d4edda;
        color: #155724;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. 세션 관리 함수 (기기별 분리) ---
def get_device_id():
    """기기별 고유 ID 생성 (세션 기반)"""
    if 'device_id' not in st.session_state:
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
    if 'last_auto_save' not in st.session_state:
        st.session_state.last_auto_save = time.time()

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

# --- 4. 데이터 로드 함수 (에러 처리 강화) ---
@st.cache_data(ttl=10)
def load_game_data():
    doc = connect_gsheet()
    if not doc:
        st.error("❌ 구글 시트 연결에 실패했습니다. 새로고침 후 다시 시도해주세요.")
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
        
        # 마을 데이터 로드 (인덱스 에러 방지)
        vil_ws = doc.worksheet("Village_Data")
        vil_vals = vil_ws.get_all_values()
        if len(vil_vals) < 2:
            st.error("❌ 마을 데이터가 없습니다.")
            return None, None, None, None, None, None
            
        headers = [h.strip() for h in vil_vals[0]]
        
        villages = {}
        initial_stocks = {}
        
        for row in vil_vals[1:]:
            if not row or not row[0].strip():
                continue
            v_name = row[0].strip()
            
            # 좌표 안전하게 로드
            try:
                x = int(row[1]) if len(row) > 1 and row[1].strip() else 0
                y = int(row[2]) if len(row) > 2 and row[2].strip() else 0
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
        
        # 플레이어 데이터 로드
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
                    'device_id': r.get('device_id', '')
                })
        
        return settings, items_info, merc_data, villages, initial_stocks, slots
    
    except Exception as e:
        st.error(f"❌ 데이터 로드 에러: {e}")
        return None, None, None, None, None, None

# --- 5. 가격 변동 함수 (추가) ---
def update_prices(settings, items_info, market_data):
    """재고 기반 가격 변동 계산"""
    if not settings or not items_info or not market_data:
        return
        
    vol = settings.get('volatility', 500)
    for v_name, v_data in market_data.items():
        for i_name, i_info in v_data.items():
            if i_name in items_info:
                base = items_info[i_name]['base']
                stock = i_info['stock']
                if stock <= 0:
                    i_info['price'] = int(base * 10)  # 품귀 현상
                else:
                    # 가격 = 기준가 * (1 + 변동성/(재고+10))
                    i_info['price'] = int(base * (1 + (vol / (stock + 10))))

# --- 6. 시간 시스템 함수 (최대 12개월 제한) ---
def update_game_time(player, settings, market_data, initial_stocks):
    current_time = time.time()
    
    if 'last_time_update' not in st.session_state:
        st.session_state.last_time_update = current_time
        return player, []
    
    elapsed = current_time - st.session_state.last_time_update
    months_passed = min(int(elapsed / 180), 12)  # 한번에 최대 12개월만
    
    events = []
    
    if months_passed > 0:
        old_month = player['month']
        old_year = player['year']
        
        for _ in range(months_passed):
            player['week'] += 1
            if player['week'] > 4:
                player['week'] = 1
                player['month'] += 1
                if player['month'] > 12:
                    player['month'] = 1
                    player['year'] += 1
        
        st.session_state.last_time_update = current_time
        
        # 월 변경 이벤트
        if old_month != player['month'] or old_year != player['year']:
            events.append(("month", f"🌙 {player['year']}년 {player['month']}월이 시작되었습니다!"))
            reset_count = 0
            for v_name in market_data:
                if v_name in initial_stocks:
                    for item_name in market_data[v_name]:
                        if item_name in initial_stocks[v_name]:
                            old_stock = market_data[v_name][item_name]['stock']
                            new_stock = initial_stocks[v_name][item_name]
                            market_data[v_name][item_name]['stock'] = new_stock
                            if old_stock != new_stock:
                                reset_count += 1
            if reset_count > 0:
                events.append(("reset", f"🔄 {reset_count}개 품목 재고 초기화"))
        
        events.append(("week", f"🌟 {player['year']}년 {player['month']}월 {player['week']}주차"))
        
        # 주차별 효과
        if player['week'] == 1:
            events.append(("week_effect", "📅 새 달의 시작! 재고가 보충됩니다."))
            for v_name in market_data:
                if v_name in initial_stocks:
                    for item_name in market_data[v_name]:
                        if item_name in initial_stocks[v_name]:
                            base_stock = initial_stocks[v_name][item_name]
                            current_stock = market_data[v_name][item_name]['stock']
                            if current_stock < base_stock:
                                market_data[v_name][item_name]['stock'] = int(base_stock * 1.1)
        elif player['week'] == 2:
            events.append(("week_effect", "📈 변동성 증가 주간!"))
            settings['volatility'] = settings.get('volatility', 500) * 1.2
        elif player['week'] == 3:
            events.append(("week_effect", "⚠️ 품귀 현상 주의!"))
        elif player['week'] == 4:
            events.append(("week_effect", "📅 다음달 재고 초기화 준비!"))
        
        # 계절별 효과
        if player['month'] in [3, 4, 5]:
            events.append(("season", "🌸 봄: 인삼/가죽 수요 증가!"))
        elif player['month'] in [6, 7, 8]:
            events.append(("season", "☀️ 여름: 비단 수요 증가!"))
        elif player['month'] in [9, 10, 11]:
            events.append(("season", "🍂 가을: 쌀 수요 증가!"))
        else:
            events.append(("season", "❄️ 겨울: 가죽갑옷 수요 급증!"))
    
    return player, events

def get_time_display(player):
    month_names = ["1월", "2월", "3월", "4월", "5월", "6월", 
                   "7월", "8월", "9월", "10월", "11월", "12월"]
    return f"{player['year']}년 {month_names[player['month']-1]} {player['week']}주차"

# --- 7. 거리 계산 함수 (추가) ---
def calculate_travel_cost(from_v, to_v, settings):
    """두 마을 간 이동비 계산"""
    dist = math.sqrt((from_v['x'] - to_v['x'])**2 + (from_v['y'] - to_v['y'])**2)
    return int(dist * settings.get('travel_cost', 15))

# --- 8. 게임 로직 함수들 ---
def get_weight(player, items_info, merc_data):
    cw = 0
    for item, qty in player['inv'].items():
        if item in items_info:
            cw += qty * items_info[item]['w']
    
    tw = 200
    for merc in player['mercs']:
        if merc in merc_data:
            tw += merc_data[merc]['w_bonus']
    
    return cw, tw

def calculate_max_purchase(player, items_info, market_data, pos, item_name, target_price, merc_data):
    if item_name not in items_info:
        return 0
    
    cw, tw = get_weight(player, items_info, merc_data)
    item_weight = items_info[item_name]['w']
    
    max_by_money = player['money'] // target_price if target_price > 0 else 0
    max_by_weight = (tw - cw) // item_weight if item_weight > 0 else 999999
    max_by_stock = market_data[pos][item_name]['stock']
    
    return min(max_by_money, max_by_weight, max_by_stock)

def process_buy(player, items_info, market_data, pos, item_name, qty, progress_placeholder, settings, merc_data):
    total_bought = 0
    total_spent = 0
    trade_log = []
    batch_prices = []
    
    while total_bought < qty:
        # 가격 업데이트
        update_prices(settings, items_info, market_data)
        target = market_data[pos][item_name]
        
        # 잔액 체크 (마이너스 방지)
        if player['money'] < target['price']:
            trade_log.append(f"⚠️ 잔액 부족으로 거래 중단")
            break
        
        cw, tw = get_weight(player, items_info, merc_data)
        can_pay = player['money'] // target['price'] if target['price'] > 0 else 0
        can_load = (tw - cw) // items_info[item_name]['w'] if items_info[item_name]['w'] > 0 else 999999
        
        batch = min(100, qty - total_bought, target['stock'], can_pay, can_load)
        
        if batch <= 0:
            if target['stock'] <= 0:
                trade_log.append(f"⚠️ 재고 소진으로 거래 중단")
            elif can_pay <= 0:
                trade_log.append(f"⚠️ 잔액 부족으로 거래 중단")
            elif can_load <= 0:
                trade_log.append(f"⚠️ 무게 초과로 거래 중단")
            break
        
        for _ in range(batch):
            player['money'] -= target['price']
            total_spent += target['price']
            player['inv'][item_name] = player['inv'].get(item_name, 0) + 1
            target['stock'] -= 1
            total_bought += 1
            batch_prices.append(target['price'])
        
        avg_price = sum(batch_prices) // len(batch_prices)
        trade_log.append(f"➤ {total_bought}/{qty} 구매 중... (체결가: {target['price']}냥 | 평균가: {avg_price}냥)")
        
        with progress_placeholder.container():
            for log in trade_log[-5:]:
                st.markdown(f"<div class='trade-line'>{log}</div>", unsafe_allow_html=True)
        
        time.sleep(0.3)
    
    return total_bought, total_spent, trade_log

def process_sell(player, items_info, market_data, pos, item_name, qty, progress_placeholder, settings, merc_data):
    total_sold = 0
    total_earned = 0
    trade_log = []
    batch_prices = []
    
    while total_sold < qty:
        # 가격 업데이트
        update_prices(settings, items_info, market_data)
        current_price = market_data[pos][item_name]['price']
        
        batch = min(100, qty - total_sold)
        
        for _ in range(batch):
            player['money'] += current_price
            player['inv'][item_name] -= 1
            market_data[pos][item_name]['stock'] += 1
            total_sold += 1
            total_earned += current_price
            batch_prices.append(current_price)
        
        avg_price = sum(batch_prices) // len(batch_prices)
        trade_log.append(f"➤ {total_sold}/{qty} 판매 중... (체결가: {current_price}냥 | 평균가: {avg_price}냥)")
        
        with progress_placeholder.container():
            for log in trade_log[-5:]:
                st.markdown(f"<div class='trade-line'>{log}</div>", unsafe_allow_html=True)
        
        time.sleep(0.3)
    
    return total_sold, total_earned, trade_log

# --- 9. 용병 판매 함수 (추가) ---
def sell_mercenary(merc_name, player, merc_data):
    """용병 판매 (80% 환불)"""
    if merc_name in player['mercs']:
        refund = int(merc_data[merc_name]['price'] * 0.8)
        player['money'] += refund
        player['mercs'].remove(merc_name)
        return True, refund
    return False, 0

# --- 10. 저장 함수들 ---
def save_player_data(doc, player, stats, device_id):
    try:
        if not doc:
            st.error("❌ 시트 연결이 끊어졌습니다.")
            return False
            
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
                device_id
            ]
            play_ws.update(f'A{row_idx}:J{row_idx}', [save_values])
            return True
    except Exception as e:
        st.error(f"❌ 저장 실패: {e}")
        return False

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

def auto_save(doc):
    """자동 저장 (5분마다)"""
    if time.time() - st.session_state.last_auto_save > 300:  # 5분
        if save_player_data(doc, st.session_state.player, st.session_state.stats, get_device_id()):
            st.toast("🔄 자동 저장 완료", icon="💾")
            st.session_state.last_auto_save = time.time()

# --- 11. 메인 실행 ---
init_session()
doc = connect_gsheet()

if doc:
    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        st.markdown("---")
        
        # 이전 접속 확인
        if load_from_session() and st.session_state.player:
            st.markdown(f"""
            <div class='success-box'>
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
        
        # 슬롯 선택 UI
        settings, items_info, merc_data, villages, initial_stocks, slots = load_game_data()
        
        if slots and settings and items_info:
            st.subheader("📋 세이브 슬롯 선택")
            for s in slots:
                device_info = " (다른 기기)" if s['device_id'] and s['device_id'] != get_device_id() else ""
                with st.container():
                    st.info(f"**슬롯 {s['slot']}**{device_info} | 📍 {s['pos']} | 💰 {s['money']:,}냥 | 📅 {s['year']}년 {s['month']}월")
            
            slot_choice = st.text_input("슬롯 번호", value="1", key="slot_input")
            
            if st.button("🎮 게임 시작", use_container_width=True):
                selected = next((s for s in slots if str(s['slot']) == slot_choice), None)
                if selected:
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
                    
                    # 시장 데이터 초기화
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
                    
                    # 가격 초기화
                    update_prices(settings, items_info, market_data)
                    
                    save_to_session()
                    st.session_state.game_started = True
                    st.rerun()
                else:
                    st.error("❌ 존재하지 않는 슬롯입니다.")
        else:
            st.error("❌ 게임 데이터를 불러올 수 없습니다. 관리자에게 문의하세요.")
    
    else:
        # 게임 메인 화면
        if not all([st.session_state.player, st.session_state.settings, 
                    st.session_state.items_info, st.session_state.merc_data,
                    st.session_state.villages, st.session_state.market_data]):
            st.error("❌ 게임 데이터가 손상되었습니다. 메인으로 돌아갑니다.")
            if st.button("🏠 메인으로"):
                st.session_state.game_started = False
                st.rerun()
            st.stop()
        
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
        
        # 탭 메뉴
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 거래", "📦 인벤토리", "⚔️ 용병", "📊 통계", "⚙️ 기타"])
        
        # [탭1] 거래
        with tab1:
            if player['pos'] == "용병 고용소":
                st.subheader("⚔️ 용병 고용")
                if merc_data:
                    for name, data in merc_data.items():
                        owned = "✓" if name in player['mercs'] else ""
                        with st.container():
                            st.info(f"{name} {owned}\n\n고용비: {data['price']:,}냥 | 무게보너스: +{data['w_bonus']}근")
                            
                            col_a, col_b = st.columns(2)
                            if owned:
                                if col_a.button(f"✅ 이미 고용됨", key=f"merc_{name}", disabled=True, use_container_width=True):
                                    pass
                                # 용병 판매 버튼
                                if col_b.button(f"💰 판매", key=f"sell_merc_{name}", use_container_width=True):
                                    success, refund = sell_mercenary(name, player, merc_data)
                                    if success:
                                        st.success(f"✅ {name} 판매 완료! {refund:,}냥 획득")
                                        save_to_session()
                                        st.rerun()
                            else:
                                if col_a.button(f"⚔️ 고용", key=f"merc_{name}", use_container_width=True):
                                    if player['money'] >= data['price']:
                                        player['money'] -= data['price']
                                        player['mercs'].append(name)
                                        cw, tw = get_weight(player, items_info, merc_data)
                                        weight_placeholder.metric("⚖️ 무게", f"{cw}/{tw}근")
                                        money_placeholder.metric("💰 소지금", f"{player['money']:,}냥")
                                        save_to_session()
                                        st.success(f"✅ {name} 고용 완료!")
                                        st.rerun()
                                    else:
                                        st.error("❌ 잔액 부족")
                                col_b.button(f"❌", key=f"blank_{name}", disabled=True, use_container_width=True)
                else:
                    st.warning("고용 가능한 용병이 없습니다.")
            
            else:
                if player['pos'] in market_data:
                    items = list(market_data[player['pos']].keys())
                    if items:
                        st.subheader(f"🛒 {player['pos']} 시세")
                        
                        for item_name in items:
                            d = market_data[player['pos']][item_name]
                            base_price = items_info[item_name]['base']
                            
                            if d['price'] > base_price:
                                price_class = "price-up"
                                trend = "▲"
                            elif d['price'] < base_price:
                                price_class = "price-down"
                                trend = "▼"
                            else:
                                price_class = "price-same"
                                trend = "■"
                            
                            with st.container():
                                st.markdown(f"**{item_name}** {trend}")
                                col1, col2, col3 = st.columns([2,1,1])
                                price_placeholder = col1.empty()
                                price_placeholder.markdown(f"<span class='{price_class}'>{d['price']:,}냥</span>", unsafe_allow_html=True)
                                col2.write(f"재고: {d['stock']}")
                                
                                max_buy = calculate_max_purchase(
                                    player, items_info, market_data, 
                                    player['pos'], item_name, d['price'], merc_data
                                )
                                col3.write(f"최대: {max_buy}개")
                                
                                col_a, col_b, col_c = st.columns([2,1,1])
                                qty = col_a.text_input("수량", value="1", key=f"qty_{item_name}", label_visibility="collapsed")
                                progress_placeholder = st.empty()
                                
                                # 매수 버튼
                                if col_b.button("💰 매수", key=f"buy_{item_name}", use_container_width=True):
                                    try:
                                        qty_int = int(qty)
                                        if qty_int > 0:
                                            actual_qty = min(qty_int, max_buy)
                                            if actual_qty > 0:
                                                progress_placeholder.markdown("<div class='trade-progress'></div>", unsafe_allow_html=True)
                                                
                                                bought, spent, trade_log = process_buy(
                                                    player, items_info, market_data,
                                                    player['pos'], item_name, actual_qty, 
                                                    progress_placeholder, settings, merc_data
                                                )
                                                
                                                if bought > 0:
                                                    st.session_state.stats['total_bought'] += bought
                                                    st.session_state.stats['total_spent'] += spent
                                                    st.session_state.stats['trade_count'] += 1
                                                    
                                                    money_placeholder.metric("💰 소지금", f"{player['money']:,}냥")
                                                    cw, tw = get_weight(player, items_info, merc_data)
                                                    weight_placeholder.metric("⚖️ 무게", f"{cw}/{tw}근")
                                                    trade_placeholder.metric("📊 거래", f"{st.session_state.stats['trade_count']}회")
                                                    price_placeholder.markdown(f"<span class='{price_class}'>{d['price']:,}냥</span>", unsafe_allow_html=True)
                                                    
                                                    save_to_session()
                                                    
                                                    avg_price = spent // bought
                                                    st.markdown(f"<div class='trade-complete'>✅ 총 {bought}개 매수 완료! (총 {spent:,}냥 | 평균가: {avg_price}냥)</div>", unsafe_allow_html=True)
                                                else:
                                                    st.warning("⚠️ 구매하지 못했습니다.")
                                            else:
                                                st.error("❌ 구매 가능한 수량이 없습니다")
                                        else:
                                            st.error("❌ 0보다 큰 수량을 입력하세요")
                                    except ValueError:
                                        st.error("❌ 올바른 숫자를 입력하세요")
                                
                                # 매도 버튼
                                if col_c.button("📦 매도", key=f"sell_{item_name}", use_container_width=True):
                                    try:
                                        qty_int = int(qty)
                                        if qty_int > 0:
                                            max_sell = player['inv'].get(item_name, 0)
                                            actual_qty = min(qty_int, max_sell)
                                            if actual_qty > 0:
                                                progress_placeholder.markdown("<div class='trade-progress'></div>", unsafe_allow_html=True)
                                                
                                                sold, earned, trade_log = process_sell(
                                                    player, items_info, market_data,
                                                    player['pos'], item_name, actual_qty,
                                                    progress_placeholder, settings, merc_data
                                                )
                                                
                                                st.session_state.stats['total_sold'] += sold
                                                st.session_state.stats['total_earned'] += earned
                                                st.session_state.stats['trade_count'] += 1
                                                
                                                money_placeholder.metric("💰 소지금", f"{player['money']:,}냥")
                                                cw, tw = get_weight(player, items_info, merc_data)
                                                weight_placeholder.metric("⚖️ 무게", f"{cw}/{tw}근")
                                                trade_placeholder.metric("📊 거래", f"{st.session_state.stats['trade_count']}회")
                                                price_placeholder.markdown(f"<span class='{price_class}'>{d['price']:,}냥</span>", unsafe_allow_html=True)
                                                
                                                save_to_session()
                                                
                                                avg_price = earned // sold
                                                st.markdown(f"<div class='trade-complete'>✅ 총 {sold}개 매도 완료! (총 {earned:,}냥 | 평균가: {avg_price:,}냥)</div>", unsafe_allow_html=True)

                                                 # [추가] try 문을 닫아주는 except 블록이 누락되었습니다.
                except Exception as e:
                st.error(f"거래 중 오류가 발생했습니다: {e}")
