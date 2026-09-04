/*
 * 정적 데모용 화면 스크립트.
 *
 * 원본(app/static/app.js)은 백엔드 API 를 호출해 화면을 채우지만, 이 사이트에는
 * 서버가 없다. 같은 DOM 구조에 샘플 데이터를 그대로 꽂아 실제 화면을 재현하고,
 * 쓰기 동작(등록·로그아웃)은 데모 안내로 대체한다.
 *
 * 지역 드롭다운과 태그·나이대 선택지는 원본과 동일한 데이터를 쓰므로 실제로 동작한다.
 */
import { DISTRICTS } from "/static/districts.js";

// 백엔드 enum 과 동일한 값 (app/models/enums.py)
const AGE_GROUPS = ["영유아/아동", "청소년", "성인", "고령"];
const TAGS = [
  "운전자", "보행보조필요", "주의력낮음", "판단력저하",
  "운동능력낮음", "임신부", "호흡기·심혈관질환", "실외근무/통학통근 중",
];
const $ = (sel) => document.querySelector(sel);

const DEMO_NOTE = "데모 화면이라 저장되지 않아요.";

// ---------- 샘플 데이터 ----------
const SAMPLE_SUBSCRIPTIONS = [
  { label: "어머니", ageGroup: "고령", region: "경상북도 경주시" },
  { label: "여자친구", ageGroup: "성인", region: "경기도 안양시" },
];

const SAMPLE_NOTIFICATIONS = [
  {
    risk: "HIGH",
    message:
      "경주에 호우경보가 내려졌어요. 어머니는 거동이 불편하시니 지금 이동 계획이 있다면 미루시는 게 좋겠어요. 하천 근처와 지하 통로는 특히 피해 주세요.",
    sentAt: "2026. 8. 14. 오후 6:12:40",
  },
  {
    risk: "MEDIUM",
    message:
      "안양에 강풍주의보가 발효됐어요. 출퇴근길에 간판이나 공사장 가림막 근처는 돌아가시는 걸 권해요.",
    sentAt: "2026. 8. 11. 오전 7:48:02",
  },
  {
    risk: "LOW",
    message:
      "경주 인근에서 규모 2.4 지진이 관측됐어요. 피해가 예상되는 수준은 아니지만 알려 드려요.",
    sentAt: "2026. 8. 3. 오후 11:05:19",
  },
];

// ---------- 폼 선택지 (원본과 동일) ----------
function initFormChoices() {
  const ageSelect = $("#input-age-group");
  AGE_GROUPS.forEach((g) => ageSelect.add(new Option(g, g)));

  const tagsBox = $("#input-tags");
  TAGS.forEach((t) => {
    const label = document.createElement("label");
    label.innerHTML = `<input type="checkbox" value="${t}" /> ${t}`;
    tagsBox.appendChild(label);
  });
}

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
    sigunguSelect.add(new Option("전체 (시/도 전체)", "전체"));
    DISTRICTS[sidoSelect.value].forEach((g) => sigunguSelect.add(new Option(g, g)));
  });
}

// ---------- 샘플 데이터로 화면 채우기 ----------
function renderDemo() {
  $("#user-info").textContent = "홍길동 (카카오 로그인)";
  $("#push-status").textContent = "✅ 이 기기로 알림을 받는 중이에요.";

  $("#subscription-list").innerHTML = SAMPLE_SUBSCRIPTIONS
    .map((s) => `<li><strong>${s.label}</strong> (${s.ageGroup}) — ${s.region}</li>`)
    .join("");

  $("#notification-list").innerHTML = SAMPLE_NOTIFICATIONS
    .map(
      (n) => `<li class="risk-${n.risk}"><span class="badge">${n.risk}</span> ${n.message}
        <small>발송됨 · ${n.sentAt}</small></li>`
    )
    .join("");
}

// ---------- 쓰기 동작은 안내로 대체 ----------
function initDemoHandlers() {
  $("#form-register").addEventListener("submit", (e) => {
    e.preventDefault();
    const status = $("#register-status");
    status.className = "status demo-hint";
    status.textContent = `ℹ️ ${DEMO_NOTE} 실제 서비스에서는 여기서 보호 대상이 등록되고, 해당 지역에 특보가 발생하면 이 기기로 푸시가 옵니다.`;
  });

  $("#btn-logout").addEventListener("click", () => {
    window.location.href = "/login";
  });

  $("#btn-refresh").addEventListener("click", () => {
    renderDemo();
  });
}

initFormChoices();
initRegionSelects();
renderDemo();
initDemoHandlers();
