# Blueprint module: promised flows and test coverage

Module `pan_self_learning_blueprint`. Contract: `docs/blueprint-architecture.md`
and `docs/blueprint-format.md`. Tests live in
`pan_self_learning_blueprint/tests/` (`TransactionCase`, plus one `HttpCase`
smoke test of the map; all tagged `post_install`, `-at_install`).
✓ = covered by an automated test in the module suite,
◐ = covered by `tools/ui_check.mjs` (run by hand, see below), not by the suite,
✗ = gap (not covered yet).

Run: `odoo-bin -d <db> -i pan_self_learning_blueprint --test-enable --test-tags /pan_self_learning_blueprint --stop-after-init`

The browser test (`test_map_ui`) needs Chrome and the Python package
`websocket-client`. Without them Odoo reports it as skipped, not as passed.

UI check (manual): with a server running and the module upgraded, run
`node tools/ui_check.mjs` (its header names the URL, login and database it
expects). It checks desktop and mobile.

## Structure (chains, phases, roles, processes, activities)

| Flow | Status | Test |
|---|---|---|
| Codes are unique per model (chain, phase, role, process, activity, scenario) | ✓ | `test_structure_activity` `test_*_code_unique` |
| The same code may be used in two different models | ✓ | `test_same_code_allowed_across_models` |
| Required fields are enforced (name, code, process, role, phase, chain) | ✓ | `test_activity_required_fields`, `test_structure_required_fields` |
| Activity defaults to choice state `proposal`; chain is related from the process | ✓ | `test_activity_defaults_and_related_chain` |
| Choice states are proposal → provisional → fixed → revised | ✓ | `test_choice_state_values` |
| Changing the choice state is tracked in the activity chatter | ✓ | `test_activity_has_chatter` |
| Records are ordered by sequence | ✓ | `test_order_by_sequence` |
| One2many inverses (chain→processes, process/role/phase→activities) | ✓ | `test_one2many_inverses` |
| Default chains and phases (binding xml ids) are installed | ✓ | `test_default_structure_loaded` |
| Codes without spaces are refused (chain, process, activity, scenario), also on rename | ✓ | `test_code_with_spaces_refused`, `test_code_rename_with_space_refused` |
| Process activity count and "Activities" button | ✓ | `test_process_activity_count_and_action` |

## Progress (rungs)

| Flow | Status | Test |
|---|---|---|
| Task rung is a selection 0..5, default `"0"` | ✓ | `test_rung` `test_task_rung_default`, `test_rung_selection` |
| Activity rung = lowest rung of its linked tasks, 0 without tasks | ✓ | `test_activity_rung_is_min_of_tasks`, `test_activity_without_tasks_is_zero` |
| Activity rung follows task changes (rung change, unlink) | ✓ | `test_activity_rung_follows_task_changes` |
| A task can implement several activities (both sides linked) | ✓ | `test_task_links_both_ways` |
| Scenario rung = lowest rung of its activities, 0 when empty | ✓ | `test_scenario_rung_*`, `test_scenario_without_steps_is_zero` |
| Scenario tasks and task count | ✓ | `test_scenario_tasks` |
| Cancelled tasks (state `1_canceled`) do not count; only cancelled tasks → 0 | ✓ | `test_cancelled_task_does_not_hold_back_the_rung`, `test_only_cancelled_tasks_gives_zero`, `test_cancelled_task_leaves_scenario_rung` |
| Rung, rung_state and hours are stored: search, filter, group by | ✓ | `test_rung_is_stored_and_searchable`, `test_hours_can_be_summed_in_a_group_by` |
| `rung_state` labels Open … Live on activity and scenario, follows the rung | ✓ | `test_rung_state_labels`, `test_rung_state_follows_rung` |
| Same rung and hours for every viewer, also with tasks the viewer cannot open | ✓ | `test_security` `test_rung_same_for_every_viewer`, `test_rung_recomputed_with_hidden_tasks_when_user_edits` |
| Cancelled tasks are left out of planned and spent hours | ✓ | `test_hours` `test_cancelled_tasks_left_out_of_hours` |
| Task form page "Blueprint" shows scenario, activities, rung | ✗ | view only; needs a UI tour / Playwright check |

## Scenarios

| Flow | Status | Test |
|---|---|---|
| `activity_ids` ordered by step sequence | ✓ | `test_scenario` `test_activity_ids_ordered_by_step_sequence` |
| Order follows a resequence of steps | ✓ | `test_activity_ids_follow_resequence` |
| Steps are deleted with their scenario | ✓ | `test_steps_cascade_with_scenario` |
| `scenario_ids` on activity (computed) | ✓ | `test_activity_scenario_ids` |
| Search activities by scenario (`in`, `=`, `not in`, by name) | ✓ | `test_search_activity_by_scenario*`, `test_search_activity_not_in_scenario` |
| "Scenarios is not set / is set" (`= False`, `!= False`, ids mixed with `False`) | ✓ | `test_search_activity_scenario_not_set`, `test_search_activity_scenario_set_counts_match`, `test_search_activity_scenario_ids_or_unset` |

## People (ADKAR)

| Flow | Status | Test |
|---|---|---|
| Each element must be 1..5 (create and write) | ✓ | `test_adkar` `test_range_accepted`, `test_range_refused`, `test_range_refused_on_write` |
| Defaults: round 1, date today | ✓ | `test_defaults` |
| Score shows the roles of its user | ✓ | `test_role_ids_from_role_users` |
| Role profile = average of each user's latest round, in ADKAR order | ✓ | `test_profile_uses_latest_round_per_user`, `test_profiles_batch_matches_single` |
| Profile only from 3 scored users of the role, else `False` | ✓ | `test_profile_hidden_below_three_users`, `test_minimum_users_for_profile` |
| Users without scores are left out; `False` when nobody has a score | ✓ | `test_profile_ignores_users_without_scores`, `test_profile_false_without_scores` |
| A user reads only their own scores; managers read and record all | ✓ | `test_security` `test_user_reads_only_own_scores`, `test_manager_reads_and_records_all_scores`, `test_user_cannot_write_scores` |
| The note is manager-only | ✓ | `test_note_is_manager_only` |
| A user still sees the role profile on the map (aggregate, computed with sudo) | ✓ | `test_profile_visible_to_user_only_as_aggregate` |

## Blueprint (open format)

| Flow | Status | Test |
|---|---|---|
| Export writes format, version and all sections with codes as references | ✓ | `test_blueprint` `test_export_header_and_content` |
| Export contains no personal data (no users, no ADKAR) | ✓ | `test_export_has_no_personal_data` |
| Export → wipe → import → import again: second import creates nothing; export matches | ✓ | `test_round_trip_into_clean_set_is_idempotent` |
| Import updates by code and never deletes | ✓ | `test_import_updates_and_never_deletes` |
| References may name codes already in the database | ✓ | `test_import_references_existing_database_codes` |
| Unknown reference code (chain, role, phase, process, step) raises `UserError` naming it | ✓ | `test_unknown_reference_code_names_the_code` |
| Unknown Odoo model (activity or phase) refused in strict import, naming the model | ✓ | `test_unknown_model_refused_in_strict_import`, `test_unknown_phase_model_refused_in_strict_import` |
| Wrong/missing format or version refused | ✓ | `test_wrong_format_or_version_refused`, `test_not_an_object_refused` |
| Template `generic_manufacturing` loads via the wizard, routes in file order, twice = no duplicates | ✓ | `test_template_generic_manufacturing_loads_via_wizard` |
| Template chains/phases update the default records instead of duplicating them | ✓ | `test_template_codes_match_default_structure` |
| Wizard export produces a file that re-imports without creating anything | ✓ | `test_wizard_export_then_import` |
| Wizard refuses a missing file, a missing template and invalid JSON | ✓ | `test_wizard_import_requires_file`, `test_wizard_template_required`, `test_wizard_import_invalid_json` |
| Wizard preselects the template when only one ships | ✓ | `test_wizard_preselects_the_only_template` |
| Loading a template again keeps company edits (choice, click path, open point, name, steps, external flag) | ✓ | `test_template_reload_keeps_company_edits` |
| Loading a template again fills empty fields (model link, click path, phase models added, steps of an empty scenario) | ✓ | `test_template_reload_fills_empty_fields` |
| A file import (strict) still overwrites | ✓ | `test_strict_import_still_overwrites` |
| Template on a database without the apps: model links left empty, missing apps named | ✓ | `test_template_lists_missing_apps` |
| Export is in English (`lang: en_US`) whatever the user language; re-import keeps both languages | ✓ | `test_export_is_in_english_whatever_the_user_language` |
| Import writes names in the file's `lang`; an inactive language is refused | ✓ | `test_import_writes_names_in_the_file_language`, `test_import_refuses_inactive_language` |
| Only managers can import (wizard create and `import_blueprint` refused for users) | ✓ | `test_security` `test_user_cannot_import` |
| Managers import, export and load the template | ✓ | `test_manager_imports_and_exports`, `test_manager_exports_phase_models`, `test_manager_loads_template` |

## Company map

| Flow | Status | Test |
|---|---|---|
| `get_map_data()` returns phases, roles, activities, scenarios with the contract keys | ✓ | `test_map_data` `test_structure_keys` |
| Phase apps as chips, role users and external flag, ADKAR profile or `False` | ✓ | `test_phase_and_role_values`, `test_role_adkar_profile` |
| Activity values (role, phase, choice, rung, open point, scenarios, model) | ✓ | `test_activity_values` |
| Scenario `activity_ids` in route order, scenario rung | ✓ | `test_scenario_activity_order` |
| No N+1: query count does not grow with the number of activities | ✓ | `test_query_count_does_not_grow_with_activities` (loose bound) |
| "Who still needs training": each activity lists its role's users with `trained` (rung ≥ 4), no ADKAR scores | ✓ | `test_training_list_per_activity`, `test_training_list_has_no_adkar_scores` |
| `get_map_details()`: one item per activity `{id, tasks:[{id,name,rung}], click_path}`, a task under each of its activities | ✓ | `test_map_details_shape` |
| First line of a click path (list, nested div, plain text, empty) | ✓ | `test_map_first_line` |
| `get_map_details()` has no N+1 | ✓ | `test_map_details_query_count_does_not_grow` (loose bound) |
| `get_map_details()` does not show names of tasks the user cannot open | ✓ | `test_security` `test_map_details_do_not_leak_hidden_task_names` |
| A plain Blueprint user can call `get_map_data` / `get_map_details` (also with Odoo models set) | ✓ | `test_user_opens_the_map`, `test_user_opens_the_map_with_odoo_models` |
| Client action loads for a Blueprint user and draws the company stop | ✓ | `test_map_ui` `test_map_renders_for_a_blueprint_user` (browser) |
| Empty state offers "Load a template" | ✓ | `test_map_empty_state_offers_template` (browser) |
| Four zoom stops, each with its own content | ◐ | `tools/ui_check.mjs` |
| Scenario select draws the numbered route badges, jumps to stop 2 | ◐ | `tools/ui_check.mjs` |
| Click a chip opens the side panel; Esc closes it | ◐ | `tools/ui_check.mjs` |
| Keyboard: Tab reaches every chip, arrows pan, +/- zoom, Home fits | ◐ | `tools/ui_check.mjs` |
| State restore after opening an activity and coming back by breadcrumb | ◐ | `tools/ui_check.mjs` |
| Mobile: no horizontal page scroll; no black fills | ◐ | `tools/ui_check.mjs` |
| Colour by Choices / Progress / People ADKAR | ✗ | UI, not asserted |
| Light and dark mode via Odoo CSS variables | ✗ | UI, not asserted |

## Menus, security, translations

| Flow | Status | Test |
|---|---|---|
| Menu Blueprint → Company map (default), Model, People, Blueprint | ✗ | not tested |
| Managers edit the model and import; users see the map and read the model | ✓ | `test_security` `test_user_reads_the_model`, `test_user_cannot_change_the_model`, `test_manager_edits_the_model` |
| An internal user without a Blueprint group sees nothing | ✓ | `test_internal_user_without_group_sees_nothing` |
| A deleted default chain/phase stays deleted on upgrade (`forcecreate="0"`) | ✗ | needs an upgrade run, not a TransactionCase |
| Dutch translations in `i18n/nl.po` | ✗ | not tested |
