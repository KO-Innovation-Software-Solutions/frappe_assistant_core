import frappe
from frappe.model.document import Document


class AikoDashboardMessage(Document):

    def after_insert(self):
        self.update_session_stats()

    def on_update(self):
        self.update_session_stats()

    def update_session_stats(self):
        if not self.session:
            return

        total_tokens = frappe.db.sql(
            """
            SELECT COALESCE(SUM(total_tokens), 0)
            FROM `tabAiko Dashboard Message`
            WHERE session = %s
            """,
            self.session,
        )[0][0]

        providers_used = self._distinct_ordered("llm_provider")
        models_used = self._distinct_ordered("llm_model")

        frappe.db.set_value(
            "Aiko Dashboard Session",
            self.session,
            {
                "total_tokens": total_tokens,
                "llm_providers_used": providers_used,
                "llm_models_used": models_used,
            },
        )

    def _distinct_ordered(self, fieldname):
        rows = frappe.db.sql(
            f"""
            SELECT {fieldname}, MIN(creation) AS first_used
            FROM `tabAiko Dashboard Message`
            WHERE session = %s
                AND {fieldname} IS NOT NULL
                AND {fieldname} != ''
            GROUP BY {fieldname}
            ORDER BY first_used ASC
            """,
            self.session,
            as_dict=True,
        )
        return ", ".join(row[fieldname] for row in rows)