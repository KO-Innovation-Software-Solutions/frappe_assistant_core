// public/js/aiko_dashboard_src/src/socket.js
//
// Direct port of aiko_chat.js's send / aiko_stage / aiko_done pattern.
// No fetch/SSE — same frappe.call + frappe.realtime approach as the
// existing chat widget, just wrapped for use from React.
//
// IMPORTANT: expects window.frappe to be available (this app is loaded
// inside a Frappe page via aiko_dashboard.js, so frappe.* is already on
// window — same assumption aiko_chat.js makes).

export function sendPrompt({ message, threadId, onStage, onDone, onError }) {
  const requestId = frappe.utils.get_random(10);

  const stageHandler = (data) => {
    if (data.thread_id !== threadId) return;
    if (data.request_id !== requestId) return;
    onStage?.(data.stage);
  };

  const doneHandler = (data) => {
    if (data.thread_id !== threadId) return;
    if (data.request_id !== requestId) return;
    cleanup();
    if (data.success) {
      // data.ui = OpenUI Lang from renderer.py (NEW)
      // data.data = plain text fallback (existing)
      onDone?.({ ui: data.ui, text: data.data, sessionName: data.session_name });
    } else {
      onError?.(data.error || "An error occurred.");
    }
  };

  function cleanup() {
    frappe.realtime.off("aiko_stage", stageHandler);
    frappe.realtime.off("aiko_done", doneHandler);
  }

  frappe.realtime.on("aiko_stage", stageHandler);
  frappe.realtime.on("aiko_done", doneHandler);

  frappe.call({
    method: "frappe_assistant_core.aiko.api.chat",
    args: { message, thread_id: threadId, request_id: requestId },
    callback: (r) => {
      if (!r.message || !r.message.success) {
        cleanup();
        onError?.("Could not start the request. Please try again.");
      }
    },
    error: () => {
      cleanup();
      onError?.("Network error or server unavailable.");
    },
  });

  return requestId;
}