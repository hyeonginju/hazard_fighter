"""
인앱 브라우저 감지 테스트.

감지 로직은 클라이언트 JS(`app/static/inapp.js`)에 있어 pytest 가 직접 실행할 수 없다.
하지만 UA 패턴 표는 오탐(정상 브라우저에 경고 배너)·미탐(카톡에서 안내 없음)이 곧바로
사용자 피해로 이어지는 부분이라 검증이 필요하다. inapp.js 가 "불러와도 아무 일도 하지
않는" 모듈이라 node 로 그대로 import 해서 표만 돌려본다.

node 가 없는 환경(파이썬 전용 CI 등)에서는 skip — 이 테스트 때문에 node 가 필수가 되면
안 되므로. 배너 마크업 자체는 서빙 테스트로 확인한다.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

INAPP_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "inapp.js"
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음 — JS 감지 규칙 테스트 생략")

# 실제 앱들이 보내는 UA 형태 (버전 숫자만 임의)
IN_APP_UAS = {
    "카카오톡": "Mozilla/5.0 (Linux; Android 14; SM-S928N Build/UP1A.231005.007; wv) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/126.0.6478.71 Mobile Safari/537.36 KAKAOTALK 25.2.1",
    "라인": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Mobile/15E148 Safari/604.1 Line/14.9.0",
    "네이버 앱": "Mozilla/5.0 (Linux; Android 14; SM-S928N) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Mobile Safari/537.36 NAVER(inapp; search; 2000; 12.6.1)",
    "다음 앱": "Mozilla/5.0 (Linux; Android 13; SM-A536N) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Mobile Safari/537.36 DaumApps/4.5.1",
    "인스타그램": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Mobile/15E148 Instagram 340.0.0.19.107",
    "페이스북": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Mobile/15E148 [FBAN/FBIOS;FBDV/iPhone15,3;FBMD/iPhone]",
}

# 인앱이 아니므로 절대 걸리면 안 되는 정상 브라우저들 (오탐 방지 회귀 테스트)
NORMAL_UAS = [
    # 안드로이드 크롬
    "Mozilla/5.0 (Linux; Android 14; SM-S928N) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.6478.71 Mobile Safari/537.36",
    # iOS 사파리
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    # iOS 크롬
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) CriOS/126.0.6478.54 Mobile/15E148 Safari/604.1",
    # 삼성 인터넷
    "Mozilla/5.0 (Linux; Android 14; SM-S928N) AppleWebKit/537.36 (KHTML, like Gecko) "
    "SamsungBrowser/25.0 Chrome/121.0.0.0 Mobile Safari/537.36",
    # 네이버 웨일 (인앱이 아닌 독립 브라우저 — 'NAVER(inapp' 이 없다)
    "Mozilla/5.0 (Linux; Android 14; SM-S928N) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Whale/3.24.223.21 Mobile Safari/537.36",
    # 데스크톱 사파리
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]


def _run_js(body: str, payload: object):
    """inapp.js 소스 뒤에 body 를 붙여 실행하고, 출력한 JSON 을 파이썬 값으로 돌려준다.

    import 대신 소스를 이어붙이는 이유: 브라우저는 확장자와 무관하게 ES 모듈로 읽지만
    node 는 package.json 없는 .js 를 CommonJS 로 취급해 named import 가 실패한다.
    (--input-type=module 로 실행하면 소스의 export 선언은 그대로 통과한다.)
    """
    script = INAPP_JS.read_text(encoding="utf-8") + "\n" + body
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        env={**os.environ, "PAYLOAD": json.dumps(payload)},
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _detect(uas: list[str]) -> list[str | None]:
    return _run_js(
        "const uas = JSON.parse(process.env.PAYLOAD);\n"
        "console.log(JSON.stringify(uas.map((ua) => (detectInAppBrowser(ua) || {}).name || null)));\n",
        uas,
    )


@needs_node
def test_in_app_browsers_detected():
    assert _detect(list(IN_APP_UAS.values())) == list(IN_APP_UAS.keys())


@needs_node
def test_normal_browsers_not_detected():
    assert _detect(NORMAL_UAS) == [None] * len(NORMAL_UAS)


@needs_node
def test_kakao_escapes_with_custom_scheme():
    url = _run_js(
        "const ua = JSON.parse(process.env.PAYLOAD);\n"
        'console.log(JSON.stringify(externalBrowserUrl(detectInAppBrowser(ua), "https://hazard.peterju.cloud/login")));\n',
        IN_APP_UAS["카카오톡"],
    )
    assert url == "kakaotalk://web/openExternal?url=https%3A%2F%2Fhazard.peterju.cloud%2Flogin"


@needs_node
def test_instagram_has_no_escape_url():
    """탈출 스킴이 없는 앱은 null — 화면에서 '주소 복사'로 안내해야 한다."""
    url = _run_js(
        "const ua = JSON.parse(process.env.PAYLOAD);\n"
        'console.log(JSON.stringify(externalBrowserUrl(detectInAppBrowser(ua), "https://hazard.peterju.cloud/login")));\n',
        IN_APP_UAS["인스타그램"],
    )
    assert url is None


def test_notice_markup_served_on_both_pages():
    for path in ("/login", "/app"):
        html = client.get(path).text
        assert 'id="inapp-notice"' in html
        assert 'id="btn-open-external"' in html


def test_inapp_module_served():
    assert client.get("/static/inapp.js").status_code == 200
