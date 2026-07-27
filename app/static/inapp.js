/*
 * 앱 안(인앱) 브라우저 감지 + 기본 브라우저로 내보내기.
 *
 * 왜 필요한가: 이 서비스의 주 유입 경로는 "카톡으로 부모님께 링크 보내기"인데,
 * 카카오톡 인앱 브라우저에서는 (1) 구글이 정책상 OAuth 를 거부하고
 * (disallowed_useragent) (2) 웹푸시 토큰 발급도 막히거나 불안정하다.
 * 즉 링크를 그냥 누르면 로그인도 알림 등록도 안 된다 — 안내가 없으면 사용자는
 * "고장났다"고 생각하고 이탈한다.
 *
 * 감지는 User-Agent 문자열 패턴으로 한다. "지금 인앱인가?"를 알려주는 표준 API 는
 * 없기 때문. 오탐(정상 브라우저를 인앱으로 오인해 쓸데없는 경고를 띄움)이 미탐보다
 * 나쁘므로, 앱 이름이 UA 에 분명히 박히는 경우만 잡고 안드로이드 웹뷰 일반 표식
 * (`; wv`)처럼 모호한 건 잡지 않는다.
 *
 * 이 모듈은 불러오는 것만으로 아무 일도 하지 않는다(DOM 접근은 함수 안에서만).
 * 덕분에 감지 규칙을 node 로 그대로 실행해 테스트할 수 있다 (tests/test_inapp_browser.py).
 */

// escape: 기본 브라우저로 넘기는 방법이 있는 앱만 표시 (없으면 주소 복사로 안내)
const IN_APP_BROWSERS = [
  { name: "카카오톡", pattern: /KAKAOTALK/i, escape: "kakao" },
  { name: "라인", pattern: /\bLine\//i, escape: "line" },
  { name: "네이버 앱", pattern: /NAVER\(inapp/i },
  { name: "다음 앱", pattern: /DaumApps/i },
  { name: "인스타그램", pattern: /Instagram/i },
  { name: "페이스북", pattern: /FBAN|FBAV/i },
];

export function detectInAppBrowser(ua = navigator.userAgent) {
  return IN_APP_BROWSERS.find((browser) => browser.pattern.test(ua)) || null;
}

/** 기본 브라우저로 같은 주소를 다시 여는 URL. 방법이 없는 앱이면 null. */
export function externalBrowserUrl(browser, href) {
  if (browser.escape === "kakao") {
    // 카카오톡이 제공하는 커스텀 스킴 — 안드로이드·iOS 양쪽에서 동작
    return `kakaotalk://web/openExternal?url=${encodeURIComponent(href)}`;
  }
  if (browser.escape === "line") {
    // 라인은 쿼리 파라미터로 지시한다
    return `${href}${href.includes("?") ? "&" : "?"}openExternalBrowser=1`;
  }
  return null;
}

/**
 * 인앱이면 #inapp-notice 배너를 채워 보여준다 (로그인·구독 화면이 같은 마크업 공유).
 * 인앱이 아니면 아무것도 하지 않는다 — 배너는 기본 hidden.
 */
export function showInAppNoticeIfNeeded() {
  const browser = detectInAppBrowser();
  const notice = document.querySelector("#inapp-notice");
  if (!browser || !notice) return null;

  const message = notice.querySelector("#inapp-message");
  message.textContent =
    `${browser.name} 안 브라우저로 열려 있어요. 여기서는 구글 로그인이 막히고(구글 정책) ` +
    `알림 등록도 안 될 수 있어요. Chrome·Safari 로 열면 정상 동작합니다.`;

  const url = externalBrowserUrl(browser, location.href);
  if (url) {
    const openBtn = notice.querySelector("#btn-open-external");
    openBtn.hidden = false;
    openBtn.addEventListener("click", () => {
      location.href = url;
    });
  } else {
    // 표준 방법이 없는 앱 — 주소를 복사해 직접 붙여넣도록
    const copyBtn = notice.querySelector("#btn-copy-url");
    copyBtn.hidden = false;
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(location.href);
        copyBtn.textContent = "✓ 복사됐어요 — 브라우저에 붙여넣어 주세요";
      } catch {
        message.textContent = `이 주소를 복사해 브라우저에서 열어 주세요: ${location.href}`;
      }
    });
  }

  notice.hidden = false;
  return browser;
}
