/*
 * 웹 PWA 구독 화면 클라이언트.
 * 빌드 도구 없이 순수 ES 모듈로 동작 — Firebase SDK 는 등록 시점에만 CDN 에서 동적 import.
 *
 * 단일 폼 흐름: 이메일 + 보호 대상 + 지역을 한 번에 적고 "보호 대상 알림 추가하기" →
 *   ① 알림 권한 + FCM 토큰 발급 (실패하면 여기서 중단 — 알림을 켜야만 등록됨)
 *   ② 보호 대상 생성(같은 호칭 있으면 재사용) → 구독 생성 → 기기 토큰 등록
 *
 * 지역 드롭다운은 표준 행정구역 목록(districts.js)으로 만든다. 공공 API의 예보구역명
 * ('경주남부'·'부산' 등)과의 대응은 백엔드 매칭 규칙(crud.regions_match)이 처리하므로,
 * 사용자는 익숙한 이름(경주시)만 고르면 된다.
 *
 * 인증은 아직 임시(user_email 쿼리/바디) — JWT 붙으면 이 파일의 email 전달부만 바뀐다.
 */
import { DISTRICTS } from "/static/districts.js";

// 백엔드 enum 과 동일한 값 (app/models/enums.py). 화면 선택지로 사용.
const AGE_GROUPS = ["영유아/아동", "청소년", "성인", "고령"];
const TAGS = [
  "운전자", "보행보조필요", "주의력낮음", "판단력저하",
  "운동능력낮음", "임신부", "호흡기·심혈관질환", "실외근무/통학통근 중",
];
const $ = (sel) => document.querySelector(sel);

// ---------- API 헬퍼 ----------
async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`${path} 실패 (${res.status}): ${await res.text()}`);
  return res.json();
}
const email = () => $("#input-email").value.trim();
const withEmail = (path) => `${path}?user_email=${encodeURIComponent(email())}`;

// ---------- 폼 초기화 ----------
function initForm() {
  $("#input-email").value = localStorage.getItem("email") || "";

  const ageSelect = $("#input-age-group");
  AGE_GROUPS.forEach((g) => ageSelect.add(new Option(g, g)));

  const tagBox = $("#input-tags");
  TAGS.forEach((t) => {
    const label = document.createElement("label");
    label.innerHTML = `<input type="checkbox" value="${t}" /> ${t}`;
    tagBox.appendChild(label);
  });
}

// ---------- 지역 계단식 드롭다운 (표준 행정구역) ----------
function initRegionSelects() {
  const sidoSelect = $("#input-sido");
  const sigunguSelect = $("#input-sigungu");

  sidoSelect.innerHTML = "";
  sidoSelect.add(new Option("시/도 선택", "", true, true));
  sidoSelect.options[0].disabled = true;
  Object.keys(DISTRICTS).forEach((s) => sidoSelect.add(new Option(s, s)));

  sidoSelect.addEventListener("change", () => {
    sigunguSelect.disabled = false;
    sigunguSelect.innerHTML = "";
    // '전체' = 시도 단위 특보 구독. 세종처럼 하위 목록이 없는 곳은 이것만 뜬다.
    sigunguSelect.add(new Option("전체 (시/도 전체)", "전체"));
    DISTRICTS[sidoSelect.value].forEach((g) => sigunguSelect.add(new Option(g, g)));
  });
}

// 폼에서 고른 행정구역을 region 으로 get-or-create 하고 id 반환.
async function resolveRegionId() {
  const sido = $("#input-sido").value;
  const sigungu = $("#input-sigungu").value;
  if (!sido || !sigungu) throw new Error("지역을 선택해 주세요.");
  const region = await api("/regions", {
    method: "POST",
    body: JSON.stringify({ sido, sigungu }),
  });
  return region.id;
}

// ---------- FCM: 알림 권한 + 토큰 발급 (등록의 관문) ----------
let firebaseCfg = null; // /firebase-config 응답 캐시
let messagingInstance = null; // Firebase 는 중복 초기화를 막으므로 한 번만 만들어 공유

async function getMessagingInstance() {
  if (messagingInstance) return messagingInstance;
  const { initializeApp, getApps, getApp } = await import("https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js");
  const { getMessaging } = await import("https://www.gstatic.com/firebasejs/10.12.0/firebase-messaging.js");
  const app = getApps().length ? getApp() : initializeApp(firebaseCfg.config);
  messagingInstance = getMessaging(app);
  return messagingInstance;
}

// 포그라운드 수신: 탭이 화면에 열려 있으면 푸시가 시스템 알림으로 자동 표시되지 않고
// 페이지로 직접 온다. 핸들러가 없으면 조용히 버려지므로(실기기에서 실제로 겪음),
// 서비스워커의 showNotification 으로 직접 띄우고 목록을 갱신한다.
async function listenForegroundMessages() {
  try {
    if (!("serviceWorker" in navigator) || Notification.permission !== "granted") return;
    if (!localStorage.getItem("fcm_token")) return; // 이 기기에서 알림을 켠 적이 없음
    if (!firebaseCfg) firebaseCfg = await api("/firebase-config");
    if (!firebaseCfg.enabled) return;
    const registration = await navigator.serviceWorker.register("/firebase-messaging-sw.js");
    const { onMessage } = await import("https://www.gstatic.com/firebasejs/10.12.0/firebase-messaging.js");
    onMessage(await getMessagingInstance(), (payload) => {
      const n = payload.notification || {};
      registration.showNotification(n.title || "명예소방관 안전 알림", {
        body: n.body || "",
        icon: "/static/icon.svg",
      });
      refreshNotifications();
    });
  } catch {
    // 포그라운드 표시는 부가 기능 — 실패해도 화면은 계속 동작
  }
}

async function ensurePushToken(statusEl) {
  if (!("serviceWorker" in navigator) || !("Notification" in window)) {
    throw new Error("이 브라우저는 웹 푸시를 지원하지 않아요. (iPhone은 Safari에서 '홈 화면에 추가' 후 열어 주세요. 카카오톡 등 앱 안 브라우저라면 Chrome/Safari 로 열어 주세요)");
  }
  if (Notification.permission === "denied") {
    // 이미 거부된 상태 — 팝업이 다시 뜨지 않으므로 설정 안내만 가능
    throw new Error("알림이 차단돼 있어요. 주소창 자물쇠(🔒) → 권한 → 알림을 '허용'으로 바꾼 뒤 다시 눌러 주세요.");
  }

  // 권한 요청은 버튼 클릭 직후 "첫 번째"로 — 다른 await(fetch 등)를 먼저 하면
  // 사용자 활성화(user activation)가 소진돼 모바일 크롬이 팝업 없이 조용히 거부한다.
  statusEl.textContent = "알림 권한 요청 중… (브라우저 팝업에서 허용을 눌러 주세요)";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("알림 권한이 허용되지 않았어요. 팝업이 안 보였다면 주소창 근처의 알림(🔔) 표시를 눌러 허용해 주세요.");
  }

  if (!firebaseCfg) firebaseCfg = await api("/firebase-config");
  if (!firebaseCfg.enabled) {
    throw new Error("서버에 Firebase 웹 설정이 없어요 (.env 의 FCM_WEB_* 참고).");
  }

  const cached = localStorage.getItem("fcm_token");
  if (cached) return cached; // 이미 발급받은 기기 — 재발급 불필요

  statusEl.textContent = "푸시 수신 설정 중…";
  const { getToken } = await import("https://www.gstatic.com/firebasejs/10.12.0/firebase-messaging.js");
  const registration = await navigator.serviceWorker.register("/firebase-messaging-sw.js");
  const token = await getToken(await getMessagingInstance(), {
    vapidKey: firebaseCfg.vapidKey,
    serviceWorkerRegistration: registration,
  });
  localStorage.setItem("fcm_token", token);
  listenForegroundMessages(); // 등록 직후부터 탭이 열려 있어도 알림이 보이게
  return token;
}

// ---------- 등록 (단일 CTA) ----------
function initRegister() {
  $("#form-register").addEventListener("submit", async (e) => {
    e.preventDefault();
    const statusEl = $("#register-status");
    const btn = $("#btn-register");
    btn.disabled = true;
    try {
      localStorage.setItem("email", email());

      // ① 알림이 관문 — 토큰을 못 받으면 등록 자체를 진행하지 않는다.
      const fcmToken = await ensurePushToken(statusEl);

      // ② 보호 대상 — 같은 호칭이 이미 있으면 재사용 (지역만 추가하는 경우 중복 방지)
      statusEl.textContent = "등록 중…";
      const label = $("#input-person-label").value.trim();
      const existing = (await api(withEmail("/persons"))).find((p) => p.label === label);
      const person =
        existing ??
        (await api("/persons", {
          method: "POST",
          body: JSON.stringify({
            user_email: email(),
            label,
            age_group: $("#input-age-group").value,
            tags: [...$("#input-tags").querySelectorAll("input:checked")].map((c) => c.value),
          }),
        }));

      // ③ 지역 → 구독 → 기기 토큰
      const regionId = await resolveRegionId();
      await api("/subscriptions", {
        method: "POST",
        body: JSON.stringify({ user_email: email(), person_id: person.id, region_id: regionId }),
      });
      await api("/device-tokens", {
        method: "POST",
        body: JSON.stringify({ user_email: email(), fcm_token: fcmToken, platform: "web" }),
      });

      statusEl.textContent = "✅ 등록 완료! 특보가 발생하면 이 기기로 푸시가 와요.";
      $("#input-person-label").value = "";
      refreshSubscriptions();
      refreshNotifications(); // 구독 직후 소급 평가(backfill)로 알림이 생겼을 수 있음
    } catch (err) {
      statusEl.textContent = `❌ ${err.message}`;
    } finally {
      btn.disabled = false;
    }
  });
}

// ---------- 등록된 알림 (구독 목록) ----------
async function refreshSubscriptions() {
  if (!email()) return;
  const [subs, persons, allRegions] = await Promise.all([
    api(withEmail("/subscriptions")),
    api(withEmail("/persons")),
    api("/regions"),
  ]);
  const regionById = Object.fromEntries(allRegions.map((r) => [r.id, r]));
  const personById = Object.fromEntries(persons.map((p) => [p.id, p]));
  $("#subscription-list").innerHTML = subs.length
    ? subs
        .map((s) => {
          const r = regionById[s.region_id];
          const p = personById[s.person_id];
          return `<li><strong>${p ? p.label : "?"}</strong>${p ? ` (${p.age_group})` : ""} — ${r ? `${r.sido} ${r.sigungu}` : "?"}</li>`;
        })
        .join("")
    : "<li class='empty'>아직 등록된 알림이 없어요.</li>";
}

// ---------- 알림 내역 ----------
async function refreshNotifications() {
  if (!email()) return;
  const items = await api(withEmail("/notifications"));
  $("#notification-list").innerHTML = items.length
    ? items
        .map((n) => `<li class="risk-${n.risk_level}"><span class="badge">${n.risk_level}</span> ${n.message}
          <small>${n.sent_at ? "발송됨 · " + new Date(n.sent_at).toLocaleString("ko-KR") : "발송 대기"}</small></li>`)
        .join("")
    : "<li class='empty'>아직 알림이 없어요.</li>";
}

// ---------- 시작 ----------
initForm();
initRegionSelects();
initRegister();
$("#btn-refresh").addEventListener("click", refreshNotifications);
refreshSubscriptions();
refreshNotifications();
listenForegroundMessages(); // 이미 알림을 켠 기기는 페이지를 열자마자 포그라운드 수신 대기
