/*
 * 정적 데모용 로그인 화면.
 * 실제 서비스는 서버사이드 OAuth code 흐름으로 구글·카카오 인증을 처리했다.
 * 여기서는 서버가 없으므로 버튼을 안내로 대체하고, 구독 화면 데모로 넘긴다.
 */
const status = document.querySelector("#login-status");

function explain(provider) {
  status.className = "status demo-hint";
  status.innerHTML =
    `ℹ️ 데모 화면이라 ${provider} 인증은 진행되지 않아요. ` +
    `실제 서비스에서는 인증 후 30일 JWT 를 발급받아 구독 화면으로 이동했어요. ` +
    `<a href="/app">구독 화면 데모 보기</a>`;
}

document.querySelector("#btn-kakao").addEventListener("click", (e) => {
  e.preventDefault();
  explain("카카오");
});

document.querySelector("#btn-google").addEventListener("click", (e) => {
  e.preventDefault();
  explain("구글");
});
