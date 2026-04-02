# Build Report: Битрикс — запуск БП раздачи

## Changes
- **core/bitrix.py**: Added `start_distribution_bp(lead_id)` — calls `bizproc.workflow.start` with TEMPLATE_ID from env; `finalize_lead(db_path, lead_id)` — wrapper that calls `restore_assigned()` then `start_distribution_bp()`; `build_qualification_summary(state)` — formats qualification result for COMMENTS; integrated summary into `build_lead_comments()` for final updates
- **bot_server.py**: Replaced `restore_assigned()` with `finalize_lead()` in two places: `_finalize_timeout()` (timeout scenarios) and `delayed_response()` (meeting_agreed / dialog_finished); updated imports
- **.env**: Added `BITRIX_BP_TEMPLATE_ID=152`

## Self-Assessment
| AC    | Status  | Notes |
|-------|---------|-------|
| AC-1: BP starts after restore_assigned | PASS | `finalize_lead()` calls `restore_assigned()` then `start_distribution_bp()` |
| AC-2: TEMPLATE_ID from env | PASS | `os.getenv("BITRIX_BP_TEMPLATE_ID")`, graceful skip if not set |
| AC-3: DOCUMENT_ID format | PASS | `["crm", "CCrmDocumentLead", "LEAD_{lead_id}"]` per Bitrix REST docs |
| AC-4: Telegram channel covered | PASS | Both `_finalize_timeout()` and `delayed_response()` use `finalize_lead()` |
| AC-5: Radist channel | N/A | Radist has no Bitrix integration (no `restore_assigned` calls) — nothing to hook into |
| AC-6: web_api.py untouched | PASS | `git diff web_api.py` empty |
| AC-7: voice_api.py untouched | PASS | `git diff voice_api.py` empty |
| AC-8: Qualification summary in COMMENTS | PASS | `build_qualification_summary()` added to `build_lead_comments()` for final updates |
| AC-9: Logging | PASS | BP start/fail/exception logged with lead_id and workflow_id |
| AC-10: Error handling | PASS | All errors caught, logged as warnings, never crashes the dialog flow |

## Known Limitations
- Radist gateway (`sofia_radist_gateway.py`) has NO Bitrix integration at all — no lead creation, no `restore_assigned`, no finalization. BP start was not added there because there is no finalization point to hook into. This is a prerequisite task (noted as P1 in CLAUDE.md).
- BP DOCUMENT_ID format `["crm", "CCrmDocumentLead", "LEAD_{id}"]` is the standard Bitrix REST format. If the BP template expects a different document type, this will need adjustment.
- No end-to-end test was performed (would require a real Telegram dialog flow to trigger finalization).

## Open Questions
- Should Radist get Bitrix integration first before BP start can be added there?
- Is TEMPLATE_ID=152 correct for the dev environment, or is there a separate dev BP?
