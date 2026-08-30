### Finding

src/flask/ctx.py may be affected by the change: "Refactor request context handling."

### Root Cause

The context-handling refactor changes how AppContext/RequestContext push and
pop behavior interacts with copy_current_request_context, but no existing
test in tests/test_reqctx.py exercises the new code path directly.

### Proposed Change

Add a regression test that exercises the refactored context-push behavior
directly, asserting the request context is correctly restored after nested
pushes.

### Files to Modify

- tests/test_reqctx.py

### Tests

- tests/test_reqctx.py::test_nested_context_push_restore

### Validation

Run `pytest tests/test_reqctx.py -k test_nested_context_push_restore`.
