# Blueprint module: promised flows and test coverage

Module `pan_self_learning_blueprint`. Contract: `docs/blueprint-architecture.md`
and `docs/blueprint-format.md`.

There are two kinds of checks, and only the first is part of the Odoo test suite:

- **Module suite** (`pan_self_learning_blueprint/tests/`): `TransactionCase`
  tests plus one `HttpCase` browser smoke test of the map (`test_map_ui`), all
  tagged `post_install`, `-at_install`.
- **UI check** (`tools/ui_check.mjs`): a Playwright script run by hand against
  a running server. It is not an Odoo test and no CI runs it.

Status: ✓ = asserted by the module suite, B = asserted by the browser smoke
test `test_map_ui` (skipped, not passed, when Chrome or the Python package
`websocket-client` is missing), ◐ = only checked by `tools/ui_check.mjs`,
✗ = not checked.

Run the suite: `odoo-bin -d <db> -i pan_self_learning_blueprint --test-enable --test-tags /pan_self_learning_blueprint --stop-after-init`

Run the UI check: restart the server, upgrade the module, then
`DB=<db> OUT=<dir> node tools/ui_check.mjs` (its header names the URL and
login it expects). It checks desktop and mobile.

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
| Codes without spaces are refused (chain, process, activity, scenario), also on rename | ✓ | `test_code_with_spaces_refused`, `test_code_rename_with_space_refused` |
| Process activity count and "Activities" button | ✓ | `test_process_activity_count_and_action` |
| No chains or phases from module data: they come only from the template | ✓ | `test_blueprint` `test_no_default_structure_xml_ids` |

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
| Planned and spent hours summed from tasks, each task once, cancelled left out | ✓ | `test_hours` `test_activity_sums_planned_and_spent`, `test_scenario_counts_each_task_once`, `test_cancelled_tasks_left_out_of_hours` |
| Project users without a Blueprint group open task views and a linked task; no Blueprint field in their arch | ✓ | `test_security` `test_task_views_hide_blueprint_without_group` |
| Views show `rung_state`, never the integer rung | ✗ | view only, not asserted |

## Scenarios

| Flow | Status | Test |
|---|---|---|
| `activity_ids` ordered by step sequence | ✓ | `test_scenario` `test_activity_ids_ordered_by_step_sequence` |
| Order follows a resequence of steps | ✓ | `test_activity_ids_follow_resequence` |
| Steps are deleted with their scenario | ✓ | `test_steps_cascade_with_scenario` |
| `scenario_ids` on activity (computed) | ✓ | `test_activity_scenario_ids` |
| Search activities by scenario (`in`, `=`, `not in`, by name) | ✓ | `test_search_activity_by_scenario*`, `test_search_activity_not_in_scenario` |
| "Scenarios is not set / is set" (`= False`, `!= False`, ids mixed with `False`) | ✓ | `test_search_activity_scenario_not_set`, `test_search_activity_scenario_set_counts_match`, `test_search_activity_scenario_ids_or_unset` |
| Progress = share of distinct activities that are Tested or further; 0 without activities; follows tasks and steps | ✓ | `test_progress_zero_without_activities`, `test_progress_is_share_of_tested_activities`, `test_progress_drops_with_a_new_untested_step` |
| Progress is stored, so the "Not tested" filter (`progress < 100`) works | ✓ | `test_progress_is_stored_and_searchable` |

## People (contacts and ADKAR)

| Flow | Status | Test |
|---|---|---|
| Role members and scores are contacts (`partner_ids`, `partner_id`); no user link left | ✓ | `test_adkar` `test_role_members_are_contacts` |
| A person without a login holds a role and is scored | ✓ | `test_person_without_login_can_be_scored`, `test_security` `test_manager_scores_person_without_login` |
| Each element must be 1..5 (create and write) | ✓ | `test_range_accepted`, `test_range_refused`, `test_range_refused_on_write` |
| Defaults: round 1, date today | ✓ | `test_defaults` |
| Score shows the roles of its person and can be searched by role | ✓ | `test_role_ids_from_role_people`, `test_scores_searchable_by_role` |
| Role band from the weakest element average of each person's latest score: ≤ 2 low, < 4 medium, ≥ 4 high | ✓ | `test_band_thresholds_on_weakest_element`, `test_band_uses_latest_round_per_person` |
| Band only from 3 scored people of the role, else `False`; people without a score do not count | ✓ | `test_minimum_people_for_band`, `test_band_hidden_below_three_people`, `test_band_ignores_people_without_scores`, `test_band_false_without_scores` |
| Only a band word or `False` leaves the server, never a number | ✓ | `test_band_is_a_word_never_a_number`, `test_map_data` `test_no_adkar_number_reaches_the_map` |
| A user reads only the scores on their own contact; managers read and record all | ✓ | `test_security` `test_user_reads_only_own_scores`, `test_manager_reads_and_records_all_scores`, `test_user_cannot_write_scores` |
| The note is manager-only | ✓ | `test_note_is_manager_only` |
| A user still sees the role band on the map (aggregate, computed with sudo) | ✓ | `test_band_visible_to_user_only_as_aggregate` |

## Upgrade to 19.0.1.2.0

| Flow | Status | Test |
|---|---|---|
| Pre-migration moves score `user_id` and role users to their contacts; default chains and phases keep their records but lose their XML ids | ✓ | `test_migration` `test_upgrade_moves_people_to_contacts` |
| Post-migration drops the old role-user table, its relation record and the `user_id` column | ✓ | `test_upgrade_moves_people_to_contacts` |
| The scripts do nothing on a fresh install and are safe to run twice | ✓ | `test_fresh_install_does_nothing`, `test_upgrade_is_safe_to_run_twice` |
| A real `-u` upgrade of a 19.0.1.1.0 database | ✗ | the tests call the scripts on a prepared cursor, not through Odoo's upgrade |

## Blueprint (open format)

| Flow | Status | Test |
|---|---|---|
| Export writes format, version and all sections with codes as references; phases have `apps`, no `models` | ✓ | `test_blueprint` `test_export_header_and_content` |
| Export contains no personal data (no people, no ADKAR) | ✓ | `test_export_has_no_personal_data` |
| Export → wipe → import → import again: second import creates nothing; export matches | ✓ | `test_round_trip_into_clean_set_is_idempotent` |
| Import updates by code and never deletes | ✓ | `test_import_updates_and_never_deletes` |
| References may name codes already in the database | ✓ | `test_import_references_existing_database_codes` |
| Unknown reference code (chain, role, phase, process, step) raises `UserError` naming it | ✓ | `test_unknown_reference_code_names_the_code` |
| Unknown activity model refused in strict import, naming the model | ✓ | `test_unknown_model_refused_in_strict_import` |
| Phase `models` in older files is accepted and ignored | ✓ | `test_phase_models_key_is_ignored` |
| More than 5,000 records (steps included) refused before anything is written | ✓ | `test_record_limit` |
| Wrong/missing format or version refused | ✓ | `test_wrong_format_or_version_refused`, `test_not_an_object_refused` |
| A file import (strict) still overwrites | ✓ | `test_strict_import_still_overwrites` |
| Export is in English (`lang: en_US`) whatever the user language; re-import keeps both languages | ✓ | `test_export_is_in_english_whatever_the_user_language` |
| Import writes names in the file's `lang`; an inactive language is refused | ✓ | `test_import_writes_names_in_the_file_language`, `test_import_refuses_inactive_language` |

## Load template, Import file, Export

| Flow | Status | Test |
|---|---|---|
| "Load template" is a manager-only server action that loads the bundled template and opens the map with a notification | ✓ | `test_blueprint` `test_load_template_action`, `test_security` `test_manager_loads_template` |
| The template loads every record and route; a second load creates nothing and says "Nothing to change." | ✓ | `test_template_generic_manufacturing_loads` |
| Loading again keeps company edits (choice, click path, open point, name, steps, external flag) | ✓ | `test_template_reload_keeps_company_edits` |
| Loading again fills empty fields (model link, click path, steps of an empty scenario) | ✓ | `test_template_reload_fills_empty_fields` |
| Without the apps: model links left empty, missing apps named in a sticky warning | ✓ | `test_template_lists_missing_apps` (skips when Sales is installed) |
| "Export" downloads a file that re-imports without creating anything | ✓ | `test_export_then_import_file` |
| "Import file" reports in a notification and opens the map | ✓ | `test_import_file_reports_and_opens_the_map` |
| "Import file" refuses a missing file, invalid JSON and files above 5 MB | ✓ | `test_import_file_requires_file`, `test_import_file_invalid_json`, `test_import_file_size_limit` |
| Users cannot import, load the template or export | ✓ | `test_security` `test_user_cannot_import` |
| Managers import and export | ✓ | `test_manager_imports_and_exports` |

## Company map

| Flow | Status | Test |
|---|---|---|
| `get_map_data()` returns phases, roles, activities, scenarios with the contract keys (no `training`) | ✓ | `test_map_data` `test_structure_keys`, `test_activity_values` |
| Phase apps as `{name, installed}` | ✓ | `test_phase_apps_with_installed_flag` |
| Role people (names only), external flag, ADKAR band or `False` | ✓ | `test_role_values`, `test_role_adkar_band` |
| Activity values (role, phase, choice, rung, open point, scenarios, model name) | ✓ | `test_activity_values` |
| Scenario `activity_ids` in route order, rung, progress as an int percentage | ✓ | `test_scenario_activity_order_and_progress` |
| No N+1: query count does not grow with the number of activities | ✓ | `test_query_count_does_not_grow_with_activities` (loose bound) |
| `get_map_details()`: one item per activity `{id, tasks:[{id,name,rung}], click_path}`, a task under each of its activities | ✓ | `test_map_details_shape` |
| `get_map_details()` leaves out cancelled tasks | ✓ | `test_map_details_leave_out_cancelled_tasks` |
| First line of a click path (list, nested div, plain text, empty) | ✓ | `test_map_first_line` |
| `get_map_details()` has no N+1 | ✓ | `test_map_details_query_count_does_not_grow` (loose bound) |
| `get_map_details()` does not show names of tasks the user cannot open | ✓ | `test_security` `test_map_details_do_not_leak_hidden_task_names` |
| A plain Blueprint user opens the map and sees the model name without ir.model access; only managers read ir.model | ✓ | `test_user_opens_the_map`, `test_user_sees_model_name_without_ir_model_access` |
| A plain user's activity form has `model_name`, not the `model_id` picker | ✓ | `test_activity_form_hides_model_picker_from_users` |
| Client action loads for a Blueprint user and draws the company stop | B | `test_map_ui` `test_map_renders_for_a_blueprint_user` |
| Empty state: managers get one "Load template" button, users one line without a button | B | `test_map_empty_state` |
| Four zoom stops, each with its own content; "not settled" counters on the Company stop | ◐ | `tools/ui_check.mjs` |
| Legend shows only the active colour-by mode, 1 to 3 items | ◐ | `tools/ui_check.mjs` |
| Scenario select draws the numbered route badges, jumps to stop 2 | ◐ | `tools/ui_check.mjs` |
| Click a chip opens the side panel; Esc closes it | ◐ | `tools/ui_check.mjs` |
| Keyboard: Tab reaches every chip, arrows pan, +/- zoom, Home fits | ◐ | `tools/ui_check.mjs` |
| State restore after opening an activity and coming back by breadcrumb | ◐ | `tools/ui_check.mjs` |
| Mobile: no horizontal page scroll; no black fills | ◐ | `tools/ui_check.mjs` |
| Choice colours (settled green, not settled amber), ADKAR band colours, apps not installed greyed out, scenario progress in the select | ✗ | UI, not asserted |
| Light and dark mode via Odoo CSS variables | ✗ | UI, not asserted |

## Menus, security, translations

| Flow | Status | Test |
|---|---|---|
| Menu Blueprint → Company map (default), Model, People, Import / export | ✗ | not tested |
| Managers edit the model; users see the map and read the model | ✓ | `test_security` `test_user_reads_the_model`, `test_user_cannot_change_the_model`, `test_manager_edits_the_model` |
| An internal user without a Blueprint group sees nothing | ✓ | `test_internal_user_without_group_sees_nothing` |
| Dutch translations in `i18n/nl.po` | ✗ | not tested |
