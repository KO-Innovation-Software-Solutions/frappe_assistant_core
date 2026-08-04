// fac_admin_utils.js
// Utility functions for FAC Admin page (renderMarkdown, etc.)
// Extracted from fac_admin.js lines 8-35

(function() {
    const ns = frappe.fac_admin;

    // Render markdown with proper table support.
    // frappe.markdown() uses showdown but its whitespace preprocessing
    // can break table syntax, and the default converter has tables disabled.
    // We use a dedicated converter instance with tables enabled.
    let _facMarkdownConverter = null;

    // Strip dangerous tags/attributes from rendered HTML before it is injected
    // via innerHTML. Showdown passes raw inline HTML through untouched, so a
    // template/skill authored with <img onerror=...> or <script> would otherwise
    // execute. DOMParser + attribute walk avoids a dependency on DOMPurify.
    ns.sanitizeHtml = function(html) {
        if (!html) return '';
        const doc = new DOMParser().parseFromString(html, 'text/html');
        doc.querySelectorAll(
            'script, iframe, object, embed, link, meta, style, base, form, input, button, select, textarea'
        ).forEach((el) => el.remove());
        doc.querySelectorAll('*').forEach((el) => {
            [...el.attributes].forEach((attr) => {
                const name = attr.name.toLowerCase();
                if (name.startsWith('on')) { el.removeAttribute(attr.name); return; }
                const val = (attr.value || '').trim().toLowerCase();
                if (['href', 'src', 'action', 'formaction', 'xlink:href'].includes(name)) {
                    if (!val || /^\s*(javascript|vbscript|data):/.test(val)) {
                        el.removeAttribute(attr.name);
                    }
                }
                if (name === 'style' && /(expression|javascript|behavior|url\s*\(\s*["']?\s*(javascript|vbscript))/.test(val)) {
                    el.removeAttribute(attr.name);
                }
            });
        });
        return doc.body.innerHTML;
    };

    ns.renderMarkdown = function(text) {
        if (!text) return '';
        if (!_facMarkdownConverter) {
            // Initialize frappe's converter so we can access the showdown lib
            if (!frappe.md2html) frappe.markdown('');
            if (frappe.md2html) {
                const Showdown = frappe.md2html.constructor;
                _facMarkdownConverter = new Showdown({
                    tables: true,
                    ghCodeBlocks: true,
                    strikethrough: true,
                    tasklists: true,
                    encodeEmails: true,
                    ellipsis: true,
                });
            }
        }
        if (_facMarkdownConverter) {
            return ns.sanitizeHtml(_facMarkdownConverter.makeHtml(text));
        }
        // Fallback
        return `<pre>${frappe.utils.escape_html(text)}</pre>`;
    };

    // Wrap occurrences of `query` in `text` with <mark>. Both inputs are escaped
    // so the result is safe to inject as innerHTML.
    ns.highlight = function(text, query) {
        const safe = frappe.utils.escape_html(text || '');
        if (!query) return safe;
        const needle = String(query).trim();
        if (!needle) return safe;
        const re = new RegExp(needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
        return safe.replace(re, m => `<mark class="fac-hl">${m}</mark>`);
    };

    // Skeleton loader card HTML helper. `rows` controls how many placeholders.
    ns.skeletonCards = function(rows) {
        const n = rows || 4;
        let out = '<div class="fac-skeleton-wrap">';
        for (let i = 0; i < n; i++) {
            out += `
                <div class="fac-skeleton-card">
                    <div class="fac-skeleton-line fac-skeleton-line--title"></div>
                    <div class="fac-skeleton-line fac-skeleton-line--body"></div>
                    <div class="fac-skeleton-line fac-skeleton-line--body short"></div>
                </div>
            `;
        }
        out += '</div>';
        return out;
    };
})();
