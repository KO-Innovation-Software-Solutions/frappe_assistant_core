(function () {
  if (window.frappe) return;

  const handlers = {};

  function trigger(e, data) {
    (handlers[e] || []).forEach((fn) => fn(data));
  }

  window.frappe = {
    utils: {
      get_random: (n) => Math.random().toString(36).slice(2, 2 + (n || 8)),
    },
    call({ args, callback, error }) {
      const { thread_id, request_id } = args || {};
      // Schedule a mock response flow
      setTimeout(() => {
        if (callback) callback({ message: { success: true } });

        if (thread_id && request_id) {
          setTimeout(() => {
            trigger("aiko_stage", { thread_id, request_id, stage: "Fetching data…" });
          }, 600);
          setTimeout(() => {
            trigger("aiko_stage", { thread_id, request_id, stage: "Building dashboard…" });
          }, 1400);
          setTimeout(() => {
            trigger("aiko_done", {
              thread_id,
              request_id,
              success: true,
              data: "Here's a summary of your assets. All 42 assets are online.",
              ui: JSON.stringify({
                type: "Card",
                props: {
                  heading: "Asset Overview",
                  text: "42 assets — 25 active, 12 inactive, 5 in maintenance.",
                  icon: "chart",
                  variant: "default",
                },
              }),
            });
          }, 2500);
        }
      }, 200);
      return {
        then: (cb) => {
          setTimeout(() => cb({ message: { success: true } }), 200);
          return this;
        },
      };
    },
    msgprint() {},
    show_alert() {},
    realtime: {
      on(e, fn) {
        (handlers[e] = handlers[e] || []).push(fn);
      },
      off(e, fn) {
        if (!handlers[e]) return;
        handlers[e] = handlers[e].filter((h) => h !== fn);
      },
    },
  };
})();
