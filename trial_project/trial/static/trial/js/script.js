/*
  言い訳裁判 - フロント側の共通スクリプト

  フェーズタイマー・ゲージ・異議あり・コメント・投票の送受信は
  法廷配信画面(trial.html)側でSocket.IOを直接使って実装しているので、
  ここには置いていません。ここに置くのは、複数の画面で使い回す
  小さなユーティリティだけです。
*/

// ---- ホスト設定画面: フェーズ時間のプラス/マイナス調整 ----
function adjustTime(button, deltaHalfStep) {
  const row = button.closest(".stepper");
  const valueEl = row.querySelector(".value");
  const hiddenInput = row.querySelector('input[type="hidden"]');

  const [min, sec] = valueEl.textContent.split(":").map(Number);
  let totalSeconds = min * 60 + sec + deltaHalfStep * 30; // 30秒刻みで増減
  totalSeconds = Math.max(30, totalSeconds); // 最低30秒、常に30秒刻みを維持する

  const newMin = Math.floor(totalSeconds / 60);
  const newSec = String(totalSeconds % 60).padStart(2, "0");
  const formatted = `${newMin}:${newSec}`;

  valueEl.textContent = formatted;
  if (hiddenInput) hiddenInput.value = formatted;
}
