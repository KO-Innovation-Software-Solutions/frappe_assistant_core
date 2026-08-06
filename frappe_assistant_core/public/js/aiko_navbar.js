// frappe_assistant_core/public/js/aiko_navbar.js
//
// Injects an "AIKO" button into the standard Frappe desk navbar, placed
// immediately to the left of the notifications bell. Clicking it opens
// the AIKO widget (AIWidgetShell), the same panel that lives at the
// bottom-right of the screen.
//
// This runs on every desk page load, on every site the app is installed
// on — no per-site or per-navbar-file edits needed.

(function () {
	function openAiko() {
		if (window.openAikoWidget) {
			window.openAikoWidget();
		} else {
			window.dispatchEvent(new CustomEvent('aiko:open'));
		}
	}

	function findNotificationsWrapper() {
		// This app's navbar bell lives inside a specific wrapper div. Try that
		// first, then fall back to more generic guesses for other setups.
		return (
			document.querySelector('.desktop-notifications') ||
			document.querySelector('.navbar .notifications-icon')?.closest('li, div') ||
			document.querySelector('#navbar-notifications')?.closest('li, div') ||
			document.querySelector('.navbar .dropdown-notifications')
		);
	}

	function injectButton() {
		if (document.getElementById('aiko-navbar-btn')) return true; // already injected

		const notificationsWrapper = findNotificationsWrapper();
		if (!notificationsWrapper || !notificationsWrapper.parentNode) return false;

		const wrapper = document.createElement('span');
		wrapper.style.cssText = 'display:inline-flex;align-items:center;list-style:none;vertical-align:middle;';
		wrapper.innerHTML = `
			<a href="#" id="aiko-navbar-btn" title="New Update" style="
				position: relative;
				display: inline-flex;
				align-items: center;
				gap: 6px;
				height: 2rem;
				line-height: 1;
				padding: 0 10px 0 8px;
				border-radius: 16px;
				background: #e6f1fb;
				text-decoration: none;
				box-sizing: border-box;
			">
				<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
					stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
					style="color:#185fa5;flex-shrink:0;">
					<path d="M12 2a2 2 0 0 1 2 2v1h1a3 3 0 0 1 3 3v2a3 3 0 0 1-3 3H9a3 3 0 0 1-3-3V8a3 3 0 0 1 3-3h1V4a2 2 0 0 1 2-2Z"/>
					<circle cx="9" cy="8" r=".5" fill="currentColor"/>
					<circle cx="15" cy="8" r=".5" fill="currentColor"/>
					<path d="M4 14v3a2 2 0 0 0 2 2h1M20 14v3a2 2 0 0 0-2 2h-1"/>
					<path d="M9 19h6"/>
				</svg>
				<span style="font-size:12px;font-weight:500;color:#185fa5;line-height:1;">AIKO</span>
				<span id="aiko-new-badge" style="
					position:absolute;top:-5px;right:-5px;
					background:#e24b4a;color:#fff;font-size:9px;font-weight:500;
					padding:1px 5px;border-radius:8px;line-height:1.4;
				">new</span>
			</a>
		`;

		wrapper.querySelector('a').addEventListener('click', function (e) {
			e.preventDefault();
			openAiko();
		});

		notificationsWrapper.parentNode.insertBefore(wrapper, notificationsWrapper);
		return true;
	}

	// The navbar can render slightly after this script runs, so retry via
	// frappe's own ready hook plus a short-lived observer as a fallback.
	frappe.after_ajax(function () {
		if (injectButton()) return;

		const observer = new MutationObserver(function () {
			if (injectButton()) observer.disconnect();
		});
		observer.observe(document.body, { childList: true, subtree: true });

		// Stop watching after 10s regardless, so we never leak an observer.
		setTimeout(function () { observer.disconnect(); }, 10000);
	});
})();