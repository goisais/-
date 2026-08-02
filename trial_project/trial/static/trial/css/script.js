/*
  言い訳裁判 - フロント側の簡易インタラクション
  ここではデモとして「見た目が動く」ところまでを実装しています。
  実際のガチャ抽選・タイマー同期・コメントのリアルタイム共有は
  サーバー側（Flask-SocketIO など）と連携させて置き換えてください。
*/

// ---- ホスト設定画面: フェーズ時間のプラス/マイナス調整 ----
function adjustTime(button, deltaMinutesHalfStep) {
  const row = button.closest(".stepper");
  const valueEl = row.querySelector(".value");
  const hiddenInput = row.querySelector('input[type="hidden"]');

  const [min, sec] = valueEl.textContent.split(":").map(Number);
  let totalSeconds = min * 60 + sec + deltaMinutesHalfStep * 30; // 30秒刻みで増減
  totalSeconds = Math.max(30, totalSeconds); // 最低30秒は確保

  const newMin = Math.floor(totalSeconds / 60);
  const newSec = String(totalSeconds % 60).padStart(2, "0");
  const formatted = `${newMin}:${newSec}`;

  valueEl.textContent = formatted;
  if (hiddenInput) hiddenInput.value = formatted;
}

// ---- 法廷配信画面: 異議ありボタンのカウントアップ ----
function incrementObjection() {
  const countEl = document.getElementById("objection-count");
  if (!countEl) return;
  const current = parseInt(countEl.textContent, 10) || 0;
  countEl.textContent = current + 1;

  // TODO: ここで本来はサーバーに「異議あり」イベントを送信し、
  // 他の視聴者の画面にもリアルタイムで反映させる（WebSocket等）
}

// ---- 法廷配信画面: コメント送信 ----
function submitComment() {
  const input = document.getElementById("comment-input");
  const feed = document.getElementById("comment-feed");
  if (!input || !feed || !input.value.trim()) return;

  const item = document.createElement("div");
  item.className = "comment-item";
  item.innerHTML = `<strong>あなた：</strong>${escapeHtml(input.value.trim())}`;
  feed.appendChild(item);
  feed.scrollTop = feed.scrollHeight;
  input.value = "";

  // TODO: ここで本来はサーバーにコメントを送信し、
  // ホスト・他の視聴者全員の画面にも同じコメントを配信する
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ---- 法廷配信画面: フェーズタイマーのカウントダウン(見た目のみのデモ) ----
document.addEventListener("DOMContentLoaded", () => {
  const activeTimeEl = document.querySelector(".phase-card.active .phase-time");
  if (!activeTimeEl) return;

  let [min, sec] = activeTimeEl.textContent.split(":").map(Number);
  let totalSeconds = min * 60 + sec;

  setInterval(() => {
    if (totalSeconds <= 0) return;
    totalSeconds -= 1;
    const m = Math.floor(totalSeconds / 60);
    const s = String(totalSeconds % 60).padStart(2, "0");
    activeTimeEl.textContent = `${m}:${s}`;
    // TODO: 制限時間0になったら次のフェーズに自動で切り替える処理をここに追加
  }, 1000);

  // 動揺度・あやしさゲージのデモ更新（マイク入力等と接続する部分は別途実装）
  const nervousnessFill = document.getElementById("nervousness-fill");
  const nervousnessValue = document.getElementById("nervousness-value");
  const suspicionFill = document.getElementById("suspicion-fill");
  const suspicionValue = document.getElementById("suspicion-value");

  if (nervousnessFill && suspicionFill) {
    setInterval(() => {
      const n = randomWalk(parseInt(nervousnessValue.textContent, 10));
      const s = randomWalk(parseInt(suspicionValue.textContent, 10));
      nervousnessFill.style.width = n + "%";
      nervousnessValue.textContent = n + "%";
      suspicionFill.style.width = s + "%";
      suspicionValue.textContent = s + "%";
    }, 3000);
  }
});

function randomWalk(current) {
  const delta = Math.floor(Math.random() * 21) - 10; // -10 ~ +10
  return Math.min(100, Math.max(0, current + delta));
}
