# E2E Tests

## Setup

1. Start Router: `cd router && python run.py`
2. Start Plugin: `cd plugin && npm start`
3. Run tests: `pytest tests/e2e/`

## Test Scenarios

### Scenario 1: No Prefix
- Send: `Hello world`
- Expected: Forwarded to OpenClaw Gateway

### Scenario 2: hm: Prefix
- Send: `hm: local task`
- Expected: Routed to Hermes Agent

### Scenario 3: gpt: Prefix
- Send: `gpt: cloud task`
- Expected: Routed to GPT Agent

### Scenario 4: both: Prefix
- Send: `both: complex task`
- Expected: Routed to Both Agent

### Scenario 5: oc: Prefix
- Send: `oc: openclaw task`
- Expected: Handled by OpenClaw directly
