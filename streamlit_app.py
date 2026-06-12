import streamlit as st
import pandas as pd
import json
import requests
import urllib3 # 🌟 추가: 경고 메시지 제어용 라이브러리
from google import genai
from google.genai import types

# 🌟 추가: SSL 인증서 무시로 인해 발생하는 귀찮은 경고 메시지들을 숨깁니다.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 0. API 설정 (★본인의 키 유지)
# ==========================================
GEMINI_API_KEY = "수정"
client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 1. 공공데이터 API 통신 로직 (KAMIS 농수산물유통정보)
# ==========================================
def fetch_kamis_realtime_data():
    # 사용자가 지정한 전체 URL (JSON 반환 설정 포함)
    api_url = "http://www.kamis.or.kr/service/price/xml.do?action=dailySalesList&p_cert_key=test&p_cert_id=test&p_returntype=json"
    
    # 🌟 1. 진짜 통신 시도 (가짜 데이터 및 방어 로직 완전 제거)
    response = requests.get(api_url, timeout=10, verify=False)
    response.raise_for_status() # HTTP 에러 시 여과 없이 예외 발생
    raw_data = response.json()  # JSON 형태로 파싱
    
    # 🌟 2. KAMIS JSON 구조에 맞춰 데이터프레임으로 변환 (파싱 로직 수정)
    if isinstance(raw_data, dict):
        # 🚨 수정: dailySalesList API는 'price' 키 안에 실제 데이터가 배열로 들어있습니다.
        if 'price' in raw_data:
            price_data = raw_data['price']
            
            # price 데이터가 리스트 형태일 때 (정상적인 다건 결과)
            if isinstance(price_data, list):
                df = pd.DataFrame(price_data)
                return df.astype(str) # PyArrow 직렬화 에러 방지
                
            # price 데이터가 딕셔너리 형태고 내부에 item이 있을 때 (단건 또는 특정 포맷)
            elif isinstance(price_data, dict) and 'item' in price_data:
                items = price_data['item']
                if isinstance(items, dict):
                    items = [items]
                df = pd.DataFrame(items)
                return df.astype(str)
                
            # 그 외의 형태일 경우
            else:
                return pd.DataFrame([price_data]).astype(str)
                
        # 기존 data 구조를 사용할 수 있는 다른 API를 위한 방어 로직 유지
        elif 'data' in raw_data and isinstance(raw_data['data'], dict) and 'item' in raw_data['data']:
            items = raw_data['data']['item']
            if isinstance(items, dict):
                items = [items]
            df = pd.DataFrame(items)
            return df.astype(str)
        else:
            # API 키 오류 등 에러 메시지가 반환될 경우 그대로 표출
            return pd.DataFrame([raw_data]).astype(str)
            
    elif isinstance(raw_data, list):
        return pd.DataFrame(raw_data).astype(str)
    else:
        return pd.DataFrame()

# ==========================================
# 2. AI 에이전트 통신 로직 (Gemini)
# ==========================================
system_instruction = """
너는 B2B 단체 급식소의 수석 AI 영양사(Dietitian)야.
주어진 실시간 식자재 도매가 데이터를 바탕으로 조건에 맞는 1끼 식단을 구성해.
반드시 아래 JSON 형식으로만 반환해. 마크다운 기호(```json) 절대 금지.
{
  "menu_name": "식단 테마 이름 (예: 고단백 가성비 식단)",
  "menu_list": ["밥류", "국류", "메인반찬", "서브반찬1", "서브반찬2"],
  "total_cost": 3500,
  "reason": "마크다운 기반의 식단 구성 의도 및 영양/단가 분석 리포트"
}
"""

if "step" not in st.session_state:
    st.session_state.step = 1
if "current_ai_response" not in st.session_state:
    st.session_state.current_ai_response = None
if "food_data" not in st.session_state:
    st.session_state.food_data = None

def ask_gemini(user_input):
    parsed_json = {
        "menu_name": "⚠️ 오류 발생", "menu_list": [], "total_cost": 0,
        "reason": "통신 지연이 발생했습니다. 다시 시도해주세요."
    }
    
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash', 
            contents=f"[지시사항]\n{system_instruction}\n\n{user_input}",
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
        )
        result_str = response.text.strip().replace("```json", "").replace("```", "").strip()
        parsed_json = json.loads(result_str)
    except Exception as e:
        print(f"Error: {e}")

    return parsed_json

# ==========================================
# 3. UI 화면 구성 
# ==========================================
st.set_page_config(page_title="AI Dietitian", page_icon="🍱", layout="wide")
st.title("🍱 B2B 실시간 단가 연동 AI 식단 큐레이터")
st.caption("공공데이터 API(KAMIS)를 실시간으로 연동하여 예산과 알레르기 조건에 맞는 최적의 식단을 생성합니다.")

if st.session_state.step == 1:
    st.subheader("1. 공공데이터 API 연동")
    
    if st.button("📡 KAMIS 농수산물유통정보 실시간 시세 가져오기", type="primary"):
        with st.spinner("공공데이터 포털 API와 직접 통신 중입니다..."):
            try:
                st.session_state.food_data = fetch_kamis_realtime_data()
                st.success("API 통신 완료! (실제 데이터 로드 성공)")
            except Exception as e:
                st.error(f"🚨 API 통신 오류 발생: {e}")
            
    if st.session_state.food_data is not None:
        st.dataframe(st.session_state.food_data, width="stretch")
        
        st.write("---")
        st.subheader("2. 단체 급식 제약 조건 설정")
        
        col1, col2 = st.columns(2)
        with col1:
            budget = st.slider("1인당 목표 단가 (원)", min_value=2000, max_value=8000, value=6000, step=100)
            target_group = st.selectbox("급식 타겟 군", ["일반 사무직 (균형식)", "현장 근로자 (고열량/고단백)", "초등학생 (저자극/성장기)", "병원 환자식 (저염/소화)"])
        with col2:
            allergies = st.multiselect("제외할 알레르기 성분 (결품 방지)", ["대두", "밀", "돼지고기", "소고기", "닭고기", "고등어", "새우", "오징어", "우유", "난류"])
            
        if st.button("🚀 AI 최적 식단 생성 알고리즘 가동"):
            with st.spinner(f"예산 {budget}원 내에서 {target_group}을 위한 식단을 계산 중입니다..."):
                food_json = st.session_state.food_data.to_json(orient="records", force_ascii=False)
                allergy_str = ", ".join(allergies) if allergies else "없음"
                
                # 🌟 핵심: 돈을 아끼지 않게 만드는 강력한 프롬프트 엔지니어링 추가
                prompt = f"""
                [실시간 식자재 API 데이터]
                {food_json}
                
                [급식 제약 조건 - 매우 중요!]
                1. 1인당 총 식자재 예산 한도: {budget}원
                2. ★예산 소진 규칙★: 무조건 싼 것만 찾지 말고, **반드시 주어진 예산({budget}원)의 85% ~ 100% 사이({int(budget*0.85)}원 ~ {budget}원) 금액을 꽉 채워서 사용**해! 예산이 높다면 가장 비싼 소고기, 돼지고기, 해산물 등 고급 식자재를 과감하게 메인 반찬으로 팍팍 넣어서 프리미엄 식단을 만들어.
                3. 대상: {target_group}
                4. 제외해야 할 알레르기 성분: {allergy_str}
                
                [미션]
                위 DB에 있는 식자재'만'을 조합하여 밥, 국, 메인반찬, 서브반찬1, 서브반찬2 로 구성된 1끼 식단을 짜줘.
                지정된 알레르기 성분이 포함된 식자재는 절대 사용 금지.
                Reason 항목에 각 메뉴별 선택 식자재, 1인분 추산 분량(g), 계산된 단가 내역을 명확한 표로 보여주고 총 비용이 예산 한도를 얼마나 꽉 채워 잘 활용했는지 자랑해줘.
                """
                st.session_state.current_ai_response = ask_gemini(prompt)
                st.session_state.step = 2
                st.rerun()

elif st.session_state.step == 2:
    ai_data = st.session_state.current_ai_response
    
    st.subheader(f"✨ 오늘의 추천 식단: {ai_data.get('menu_name', '추천 식단')}")
    
    menus = ai_data.get("menu_list", [])
    if menus:
        cols = st.columns(len(menus))
        for i, menu in enumerate(menus):
            with cols[i]:
                st.info(f"**{menu}**")
                
    st.metric(label="📊 1인당 예상 식자재 원가", value=f"{ai_data.get('total_cost', 0):,} 원")
    
    st.write("---")
    st.subheader("💡 AI 영양사 분석 리포트")
    st.markdown(ai_data.get("reason", ""), unsafe_allow_html=True)
    
    if st.button("🔄 조건 변경 및 다시 짜기"):
        st.session_state.clear()
        st.rerun()
