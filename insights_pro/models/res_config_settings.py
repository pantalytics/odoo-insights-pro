# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    insights_pro_enabled = fields.Boolean(
        string="Enable Insights Pro",
        config_parameter="insights_pro.enabled",
        help="Master switch. Even when enabled, tracking stays off until a "
        "PostHog project key is provided.",
    )
    insights_pro_project_key = fields.Char(
        string="PostHog Project Key",
        config_parameter="insights_pro.posthog_project_key",
        help="Public project API key (starts with 'phc_'). Leave empty to keep "
        "the module dormant.",
    )
    insights_pro_host = fields.Char(
        string="PostHog Host",
        config_parameter="insights_pro.posthog_host",
        default="https://eu.i.posthog.com",
        help="PostHog instance URL. Use https://us.i.posthog.com for US Cloud.",
    )
    insights_pro_mask_all_text = fields.Boolean(
        string="Mask all input text",
        config_parameter="insights_pro.mask_all_text",
        default=True,
        help="Replace captured text with asterisks so no user-entered content "
        "leaves the browser.",
    )
    insights_pro_disable_session_recording = fields.Boolean(
        string="Disable session replay",
        config_parameter="insights_pro.disable_session_recording",
        default=True,
        help="Keep PostHog session recording turned off.",
    )
