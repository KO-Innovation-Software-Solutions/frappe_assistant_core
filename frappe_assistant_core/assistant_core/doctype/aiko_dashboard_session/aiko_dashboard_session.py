import frappe
from frappe.model.document import Document


class AikoDashboardSession(Document):

    def before_save(self):
        self.update_total_tokens()
        self.update_llm_usage_summary()

    def update_total_tokens(self):
        result = frappe.db.sql(
            """
            SELECT COALESCE(SUM(total_tokens), 0)
            FROM `tabAiko Dashboard Message`
            WHERE session = %s
            """,
            self.name,
        )
        self.total_tokens = result[0][0] if result else 0

    def update_llm_usage_summary(self):
        """
        Builds an ordered, de-duplicated list of the providers/models used
        in this session, ordered by when each was first used. e.g. if the
        session started on openai and later switched to ollama, this
        produces "openai, ollama" (not just the latest one).
        """
        self.llm_providers_used = self._distinct_ordered("llm_provider")
        self.llm_models_used = self._distinct_ordered("llm_model")

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
            self.name,
            as_dict=True,
        )
        return ", ".join(row[fieldname] for row in rows)