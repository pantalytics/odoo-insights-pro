# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pan_insights_pro_enabled = fields.Boolean(
        string="Enable Insights Pro",
        config_parameter="pan_insights_pro.enabled",
        help="Master switch. Even when enabled, tracking stays off until a "
        "PostHog project key is provided.",
    )
    pan_insights_pro_project_key = fields.Char(
        string="PostHog Project Key",
        config_parameter="pan_insights_pro.posthog_project_key",
        help="Public project API key (starts with 'phc_'). Leave empty to keep "
        "the module dormant.",
    )
    pan_insights_pro_host = fields.Char(
        string="PostHog Host",
        config_parameter="pan_insights_pro.posthog_host",
        default="https://eu.i.posthog.com",
        help="PostHog instance URL. Use https://us.i.posthog.com for US Cloud.",
    )
    pan_insights_pro_mask_all_text = fields.Boolean(
        string="Mask all visible text",
        config_parameter="pan_insights_pro.mask_all_text",
        default=False,
        help="Input fields are ALWAYS masked. Tick this to also hide all visible "
        "text (labels, values) in recordings — maximum privacy, but you mainly "
        "see layout and flow. Leave off for useful recordings.",
    )
    pan_insights_pro_disable_session_recording = fields.Boolean(
        string="Disable session replay",
        config_parameter="pan_insights_pro.disable_session_recording",
        default=False,
        help="Session replay is ON by default (the most valuable signal). Tick "
        "to turn it off for this instance (e.g. a customer that opts out).",
    )
