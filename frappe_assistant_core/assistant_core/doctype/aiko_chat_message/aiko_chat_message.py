import frappe
from frappe.model.document import Document


class AikoChatMessage(Document):

    def after_insert(self):
        self.update_session_tokens()

    def on_update(self):
        self.update_session_tokens()

    def update_session_tokens(self):
        if not self.session:
            return
        result = frappe.db.sql("""
            SELECT COALESCE(SUM(total_tokens), 0)
            FROM `tabAiko Chat Message`
            WHERE session = %s
        """, self.session)
        total = result[0][0] if result else 0
        frappe.db.set_value("Aiko Chat Session", self.session, "total_tokens", total)