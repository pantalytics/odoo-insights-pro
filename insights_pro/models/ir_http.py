# -*- coding: utf-8 -*-
from odoo import models, release


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        """Expose the (dormant-by-default) Insights Pro configuration to the
        backend JS bundle through the session, so no extra RPC round-trip is
        needed to bootstrap PostHog.
        """
        result = super().session_info()
        result["insights_pro"] = self._insights_pro_config()
        return result

    def _insights_pro_config(self):
        icp = self.env["ir.config_parameter"].sudo()
        api_key = (icp.get_param("insights_pro.posthog_project_key") or "").strip()
        api_host = (
            icp.get_param("insights_pro.posthog_host") or "https://eu.i.posthog.com"
        ).strip()
        enabled = icp.get_param("insights_pro.enabled", "True") not in ("False", "0", "")

        env = self.env
        # Pseudonymous identity: database name + user id. Never a name or email.
        distinct_id = "%s#%s" % (env.cr.dbname, env.uid)

        return {
            # The loader stays a no-op until both flags are true.
            "enabled": bool(enabled and api_key),
            "api_key": api_key,
            "api_host": api_host,
            "distinct_id": distinct_id,
            # Per-customer workspace so data never mixes between databases.
            "workspace": env.cr.dbname,
            "company": env.company.name if env.company else None,
            "odoo_version": release.version,
            # Privacy defaults — overridable via system parameters if ever needed.
            "mask_all_text": icp.get_param("insights_pro.mask_all_text", "False")
            in ("True", "1"),
            "disable_session_recording": icp.get_param(
                "insights_pro.disable_session_recording", "False"
            )
            in ("True", "1"),
        }
