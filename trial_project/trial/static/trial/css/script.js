/*
  言い訳裁判 - フロント側の共通スクリプト

  異議あり・コメントの送受信は各画面(trial.html)側で
  Socket.IOを直接使って実装しているので、ここには置いていません。
  ここに置くのは、複数の画面で使い回す小さなユーティリティだけです。
*/

// ---- ホスト設定画面: フェーズ時間のプラス/マイナス調整 ----
function adjustTime(button, deltaHalfStep) {
  const row = button.closest(".stepper");
  const valueEl = row.querySelector(".value");
  const hiddenInput = row.querySelector('input[type="hidden"]');

  const [min, sec] = valueEl.textContent.split(":").map(Number);
  let totalSeconds = min * 60 + sec + deltaHalfStep * 30; // 30秒刻みで増減
  totalSeconds = Math.max(10, totalSeconds); // 最低10秒は確保

  const newMin = Math.floor(totalSeconds / 60);
  const newSec = String(totalSeconds % 60).padStart(2, "0");
  const formatted = `${newMin}:${newSec}`;

  valueEl.textContent = formatted;
  if (hiddenInput) hiddenInput.value = formatted;
}

// ---- 法廷配信画面: フェーズタイマーのカウントダウン(見た目のみ・次フェーズ自動切替は未実装) ----
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
    // TODO: 次のフェーズ以降で、0になったら自動的に次フェーズへ切り替える処理と
    // 全員の画面を同期させる処理を追加する
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
