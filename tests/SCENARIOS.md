# Blueprint module: promised flows and test coverage

Module `pan_self_learning_blueprint`. Contract: `docs/blueprint-architecture.md`
and `docs/blueprint-format.md`. Tests live in
`pan_self_learning_blueprint/tests/` (`TransactionCase`, tagged
`post_install`, `-at_install`). ✓ = covered by an automated test,
✗ = gap (not covered yet).

Run: `odoo-bin -d <db> -i pan_self_learning_blueprint --test-tags /pan_self_learning_blueprint --stop-after-init`

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
| Codes without spaces are refused with a clear message | ✗ | not tested (implementation extra, not in the contract) |

## Progress (rungs)

| Flow | Status | Test |
|---|---|---|
| Task rung is a selection 0..5, default `"0"` | ✓ | `test_rung` `test_task_rung_default`, `test_rung_selection` |
| Activity rung = lowest rung of its linked tasks, 0 without tasks | ✓ | `test_activity_rung_is_min_of_tasks`, `test_activity_without_tasks_is_zero` |
| Activity rung follows task changes (rung change, unlink) | ✓ | `test_activity_rung_follows_task_changes` |
| A task can implement several activities (both sides linked) | ✓ | `test_task_links_both_ways` |
| Scenario rung = lowest rung of its activities, 0 when empty | ✓ | `test_scenario_rung_*`, `test_scenario_without_steps_is_zero` |
| Scenario tasks and task count | ✓ | `test_scenario_tasks` |
| Task form page "Blueprint" shows scenario, activities, rung | ✗ | view only; needs a UI tour / Playwright check |

## Scenarios

| Flow | Status | Test |
|---|---|---|
| `activity_ids` ordered by step sequence | ✓ | `test_scenario` `test_activity_ids_ordered_by_step_sequence` |
| Order follows a resequence of steps | ✓ | `test_activity_ids_follow_resequence` |
| Steps are deleted with their scenario | ✓ | `test_steps_cascade_with_scenario` |
| `scenario_ids` on activity (computed) | ✓ | `test_activity_scenario_ids` |
| Search activities by scenario (`in`, `=`, `not in`, by name) | ✓ | `test_search_activity_by_scenario*`, `test_search_activity_not_in_scenario` |

## People (ADKAR)

| Flow | Status | Test |
|---|---|---|
| Each element must be 1..5 (create and write) | ✓ | `test_adkar` `test_range_accepted`, `test_range_refused`, `test_range_refused_on_write` |
| Defaults: round 1, date today | ✓ | `test_defaults` |
| Score shows the roles of its user | ✓ | `test_role_ids_from_role_users` |
| Role profile = average of each user's latest round, in ADKAR order | ✓ | `test_profile_uses_latest_round_per_user`, `test_profile_single_user` |
| Users without scores are left out; `False` when nobody has a score | ✓ | `test_profile_ignores_users_without_scores`, `test_profile_false_without_scores` |
| Access: users see scores per role only as intended | ✗ | security rules not tested |

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
| Template on a database without the apps: model links left empty and listed | ✗ | only indirectly (the template loads); the listing is not asserted |
| Only managers can import | ✗ | access rights not tested |

## Company map

| Flow | Status | Test |
|---|---|---|
| `get_map_data()` returns phases, roles, activities, scenarios with the contract keys | ✓ | `test_map_data` `test_structure_keys` |
| Phase apps as chips, role users and external flag, ADKAR profile or `False` | ✓ | `test_phase_and_role_values`, `test_role_adkar_profile` |
| Activity values (role, phase, choice, rung, open point, scenarios, model) | ✓ | `test_activity_values` |
| Scenario `activity_ids` in route order, scenario rung | ✓ | `test_scenario_activity_order` |
| No N+1: query count does not grow with the number of activities | ✓ | `test_query_count_does_not_grow_with_activities` (loose bound) |
| Client action renders the SVG map with the fixed orientation | ✗ | needs a JS tour / Playwright check |
| Scenario select dims others and draws the numbered route, jumps to stop 2 | ✗ | UI |
| Colour by Choices / Progress / People ADKAR | ✗ | UI |
| Zoom slider with four semantic stops (wheel and pinch move the slider) | ✗ | UI |
| Click a chip opens the side panel with a button to the activity form | ✗ | UI |
| Empty state offers "Load a template" | ✗ | UI |
| Light and dark mode via Odoo CSS variables | ✗ | UI |

## Menus, security, translations

| Flow | Status | Test |
|---|---|---|
| Menu Blueprint → Company map (default), Model, People, Blueprint | ✗ | not tested |
| Managers edit the model and import; users see the map and read the model | ✗ | access rights per group not tested |
| Dutch translations in `i18n/nl.po` | ✗ | not tested |
