/*
 * 로그인 화면.
 * - 이미 로그인돼 있으면(JWT 보유) 바로 구독 화면으로 — 30일 내 재방문은 로그인 화면을 안 본다.
 * - localStorage 의 last_provider 로 "지난번에 이 방법으로 로그인했어요" 배지를 띄워
 *   같은 사람이 실수로 다른 프로바이더를 눌러 계정이 2개 생기는 걸 줄인다 (같은 기기 한정).
 * - 카톡 등 인앱 브라우저면 배너로 기본 브라우저 전환을 안내한다 (구글 로그인이 막힘).
 */
import { showInAppNoticeIfNeeded } from "/static/inapp.js";

const hashParams = new URLSearchParams(location.hash.slice(1));

if (localStorage.getItem("jwt")) {
  location.replace("/app");
} else {
  showInAppNoticeIfNeeded();
  if (hashParams.get("login_error")) {
    document.querySelector("#login-status").textContent =
      "로그인이 완료되지 않았어요. 다시 시도해 주세요.";
    history.replaceState(null, "", "/login");
  }
  const last = localStorage.getItem("last_provider");
  if (last === "kakao" || last === "google") {
    document.querySelector(`#badge-${last}`).hidden = false;
  }
}
