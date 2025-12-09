# Test Suite for DMARC IP Investigation

This directory contains unit tests and integration tests for the DMARC email processing agent with IP investigation capabilities.

## Structure

```
tests/
├── README.md                      # This file
├── test_ip_investigation.py       # Unit tests for IP investigation logic
├── test_dmarc_agent.py            # Integration tests for DMARC agent (TODO)
├── fixtures/                      # Sample DMARC XML reports
│   ├── sample_dmarc_clean.xml     # Clean report (all passes)
│   └── sample_dmarc_high_risk.xml # Report with suspicious IPs
└── conftest.py                    # pytest configuration and fixtures (TODO)
```

## Running Tests

### Install test dependencies:
```bash
uv add --dev pytest pytest-asyncio pytest-mock
```

### Run all tests:
```bash
uv run pytest tests/ -v
```

### Run specific test file:
```bash
uv run pytest tests/test_ip_investigation.py -v
```

### Run with coverage:
```bash
uv run pytest tests/ --cov=utils --cov=agentuity_agents --cov-report=html
```

## Test Coverage

### Current Tests (`test_ip_investigation.py`)

#### IP Extraction Tests
- ✅ Extract IPs with authentication failures from valid XML
- ✅ Ignore IPs where both SPF and DKIM pass
- ✅ Handle malformed XML gracefully
- ✅ Extract multiple failed IPs from one report

#### Risk Scoring Tests
- ✅ Both SPF & DKIM fail → High score (50+ points)
- ✅ Single failure → Medium score (25 points)
- ✅ High volume adds points (+15 for >10 messages)
- ✅ Quarantine/reject disposition adds points (+20)
- ✅ Score never exceeds 100

#### Filtering Tests
- ✅ Filter returns only high-risk IPs (score >= threshold)
- ✅ Respects max_ips limit
- ✅ Detects excessive failures flag
- ✅ Sorts IPs by risk score (descending)

#### Edge Cases
- ✅ Empty XML
- ✅ Missing source_ip field
- ✅ No high-risk IPs (all below threshold)

### TODO: Integration Tests (`test_dmarc_agent.py`)

#### End-to-End Workflow Tests
- [ ] Test complete DMARC processing with clean report
- [ ] Test with high-risk IPs (mock IP analyzer responses)
- [ ] Test with excessive failures (>20 IPs)
- [ ] Test graceful degradation when IP analyzer fails
- [ ] Test timeout handling (60s timeout)

#### Mock IP Analyzer Agent
- [ ] Create mock responses for different IP types:
  - Legitimate infrastructure (Google, Microsoft, etc.)
  - Suspicious residential IPs
  - Cloud VPS providers
  - Unknown/timeout scenarios

## Test Fixtures

### `sample_dmarc_clean.xml`
- 2 records, both passing SPF and DKIM
- Total: 237 messages, 0 failures
- Expected: No IP investigations, "healthy" report

### `sample_dmarc_high_risk.xml`
- 5 records total:
  - 1 passing (Google infrastructure)
  - 2 high-risk (both SPF & DKIM fail, high volume)
  - 1 medium-risk (SPF fail only)
  - 1 low-risk (DKIM fail, low volume)
- Total: 498 messages, 48 failures
- Expected: Investigate 2 high-risk IPs (scores >= 40)

### TODO: Additional Fixtures
- [ ] `sample_dmarc_excessive.xml` - 50+ failed IPs
- [ ] `sample_dmarc_forwarding.xml` - Email forwarding scenarios
- [ ] `sample_dmarc_malformed.xml` - Various malformed XML cases

## Risk Score Examples

### Test Case Scenarios:

| IP | SPF | DKIM | Count | Disposition | Score | Should Investigate? |
|----|-----|------|-------|-------------|-------|---------------------|
| 181.196.28.68 | fail | fail | 23 | quarantine | 85 | ✅ Yes (critical) |
| 103.224.182.251 | fail | fail | 15 | reject | 85 | ✅ Yes (critical) |
| 45.123.67.89 | fail | pass | 8 | none | 35 | ❌ No (below threshold) |
| 192.178.142.200 | pass | fail | 2 | none | 25 | ❌ No (low risk) |
| 192.178.142.113 | pass | pass | 450 | none | 0 | ❌ No (all pass) |

### Scoring Breakdown:
- **181.196.28.68**: 50 (both fail) + 20 (quarantine) + 15 (>10 msgs) = 85
- **103.224.182.251**: 50 (both fail) + 20 (reject) + 15 (>10 msgs) = 85
- **45.123.67.89**: 25 (SPF fail) + 10 (5-10 msgs) = 35
- **192.178.142.200**: 25 (DKIM fail) = 25
- **192.178.142.113**: 0 (all pass) = 0

## Mocking Strategy

### Mocking the IP Analyzer Agent

For integration tests, we mock the IP analyzer agent's responses:

```python
@pytest.fixture
def mock_ip_analyzer(mocker):
    """Mock IP analyzer agent responses"""
    mock_agent = mocker.AsyncMock()

    # Google IP - legitimate, low risk
    mock_agent.run.return_value.data.text.return_value = """
    Investigation Results: This IP belongs to Google LLC (AS15169).
    Legitimate infrastructure. No suspicious activity detected.
    Recommendation: No action needed.
    """

    return mock_agent
```

### Mock Response Templates

We'll create mock responses for common scenarios:
- Legitimate ESPs (Google, Microsoft, SendGrid)
- Residential ISPs (suspicious)
- Cloud VPS (medium risk)
- Unknown/private IPs
- Timeout/error scenarios

## Running Tests in CI/CD

### GitHub Actions Example:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Install uv
        run: curl -fsSL https://astral.sh/uv/install.sh | sh
      - name: Install dependencies
        run: uv sync
      - name: Run tests
        run: uv run pytest tests/ -v --cov
```

## Contributing Tests

When adding new functionality:
1. Write tests FIRST (TDD approach)
2. Ensure >80% code coverage
3. Add fixtures for new scenarios
4. Document test cases in this README
5. Run full test suite before committing

## Performance Benchmarks

### Target Performance:
- IP extraction: <50ms per XML
- Risk scoring: <1ms per IP
- Filtering: <10ms for 100 IPs
- Full workflow (mocked): <100ms

### Measuring Performance:
```bash
uv run pytest tests/ --durations=10
```

## Known Issues / TODO

- [ ] Add integration tests with mocked IP analyzer
- [ ] Add tests for whitelist management
- [ ] Add tests for parallel IP investigation
- [ ] Add performance benchmarks
- [ ] Add fixtures for edge cases (malformed XML, etc.)
- [ ] Mock OpenAI API calls for DMARC analysis
- [ ] Add tests for Slack notification formatting
