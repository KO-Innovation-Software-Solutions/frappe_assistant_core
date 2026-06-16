# Copyright (c) 2026, Paul Clinton and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AikoChatSession(Document):

    def before_save(self):
        self.update_total_tokens()

    def update_total_tokens(self):
        result = frappe.db.sql("""
            SELECT COALESCE(SUM(total_tokens), 0)
            FROM `tabAiko Chat Message`
            WHERE session = %s
        """, self.name)
        self.total_tokens = result[0][0] if result else 0