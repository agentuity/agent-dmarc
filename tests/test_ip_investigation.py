"""
Unit tests for IP investigation utilities.

Tests cover:
1. IP extraction from DMARC XML
2. Risk scoring algorithm
3. IP filtering logic
4. Whitelist checking
5. Error handling and edge cases
"""

import pytest
from utils.ip_investigation import (
    extract_failed_ips_from_xml,
    calculate_risk_score,
    filter_high_risk_ips,
    IPRecord,
)


class TestIPExtraction:
    """Test extraction of failed IPs from DMARC XML"""

    def test_extract_failed_ips_from_valid_xml(self):
        """Should extract IPs with authentication failures"""
        xml = """<?xml version="1.0"?>
        <feedback>
            <record>
                <row>
                    <source_ip>192.168.1.100</source_ip>
                    <count>5</count>
                    <policy_evaluated>
                        <disposition>none</disposition>
                    </policy_evaluated>
                </row>
                <identifiers>
                    <header_from>example.com</header_from>
                </identifiers>
                <auth_results>
                    <spf>
                        <result>fail</result>
                    </spf>
                    <dkim>
                        <result>fail</result>
                    </dkim>
                </auth_results>
            </record>
        </feedback>
        """

        failed_ips = extract_failed_ips_from_xml(xml)

        assert len(failed_ips) == 1
        assert failed_ips[0].ip == "192.168.1.100"
        assert failed_ips[0].count == 5
        assert failed_ips[0].spf_result == "fail"
        assert failed_ips[0].dkim_result == "fail"

    def test_extract_ignores_passing_ips(self):
        """Should not extract IPs where both SPF and DKIM pass"""
        xml = """<?xml version="1.0"?>
        <feedback>
            <record>
                <row>
                    <source_ip>192.168.1.200</source_ip>
                    <count>100</count>
                </row>
                <identifiers>
                    <header_from>example.com</header_from>
                </identifiers>
                <auth_results>
                    <spf>
                        <result>pass</result>
                    </spf>
                    <dkim>
                        <result>pass</result>
                    </dkim>
                </auth_results>
            </record>
        </feedback>
        """

        failed_ips = extract_failed_ips_from_xml(xml)

        assert len(failed_ips) == 0

    def test_extract_handles_malformed_xml(self):
        """Should return empty list for malformed XML"""
        xml = "not valid xml at all"

        failed_ips = extract_failed_ips_from_xml(xml)

        assert len(failed_ips) == 0

    def test_extract_handles_multiple_records(self):
        """Should extract all failed IPs from multiple records"""
        xml = """<?xml version="1.0"?>
        <feedback>
            <record>
                <row>
                    <source_ip>10.0.0.1</source_ip>
                    <count>3</count>
                </row>
                <identifiers><header_from>test.com</header_from></identifiers>
                <auth_results>
                    <spf><result>fail</result></spf>
                    <dkim><result>pass</result></dkim>
                </auth_results>
            </record>
            <record>
                <row>
                    <source_ip>10.0.0.2</source_ip>
                    <count>7</count>
                </row>
                <identifiers><header_from>test.com</header_from></identifiers>
                <auth_results>
                    <spf><result>pass</result></spf>
                    <dkim><result>fail</result></dkim>
                </auth_results>
            </record>
        </feedback>
        """

        failed_ips = extract_failed_ips_from_xml(xml)

        assert len(failed_ips) == 2
        assert failed_ips[0].ip == "10.0.0.1"
        assert failed_ips[1].ip == "10.0.0.2"


class TestRiskScoring:
    """Test risk score calculation logic"""

    def test_both_fail_high_score(self):
        """Both SPF and DKIM fail should give high score (50+ points)"""
        record = IPRecord(
            ip="1.2.3.4",
            count=1,
            spf_result="fail",
            dkim_result="fail",
            spf_aligned=False,
            dkim_aligned=False,
            disposition="none",
            source_domain="test.com"
        )

        score = calculate_risk_score(record)

        assert score >= 50

    def test_single_fail_medium_score(self):
        """Only one failure should give medium score (25 points)"""
        record = IPRecord(
            ip="1.2.3.4",
            count=1,
            spf_result="fail",
            dkim_result="pass",
            spf_aligned=False,
            dkim_aligned=True,
            disposition="none",
            source_domain="test.com"
        )

        score = calculate_risk_score(record)

        assert score == 25

    def test_high_volume_adds_points(self):
        """High message count should increase risk score"""
        record = IPRecord(
            ip="1.2.3.4",
            count=15,  # High volume
            spf_result="fail",
            dkim_result="fail",
            spf_aligned=False,
            dkim_aligned=False,
            disposition="none",
            source_domain="test.com"
        )

        score = calculate_risk_score(record)

        # 50 (both fail) + 15 (high volume) = 65
        assert score >= 65

    def test_quarantine_disposition_adds_points(self):
        """Quarantine/reject disposition should add 20 points"""
        record = IPRecord(
            ip="1.2.3.4",
            count=1,
            spf_result="fail",
            dkim_result="fail",
            spf_aligned=False,
            dkim_aligned=False,
            disposition="quarantine",
            source_domain="test.com"
        )

        score = calculate_risk_score(record)

        # 50 (both fail) + 20 (quarantine) = 70
        assert score == 70

    def test_score_never_exceeds_100(self):
        """Risk score should be capped at 100"""
        record = IPRecord(
            ip="1.2.3.4",
            count=100,  # Extremely high volume
            spf_result="fail",
            dkim_result="fail",
            spf_aligned=False,
            dkim_aligned=False,
            disposition="reject",
            source_domain="test.com"
        )

        score = calculate_risk_score(record)

        assert score <= 100


class TestIPFiltering:
    """Test filtering of high-risk IPs"""

    def test_filter_returns_high_risk_only(self):
        """Should only return IPs with score >= threshold"""
        records = [
            IPRecord("1.1.1.1", 1, "fail", "pass", False, True, "none", "test.com"),  # Score: 25
            IPRecord("2.2.2.2", 1, "fail", "fail", False, False, "none", "test.com"),  # Score: 50
            IPRecord("3.3.3.3", 15, "fail", "fail", False, False, "none", "test.com"),  # Score: 65
        ]

        high_risk, excessive = filter_high_risk_ips(records, max_ips=20, min_risk_score=40)

        # Only IPs with score >= 40 should be returned
        assert len(high_risk) == 2
        assert high_risk[0].ip == "3.3.3.3"  # Highest score first
        assert high_risk[1].ip == "2.2.2.2"

    def test_filter_respects_max_ips(self):
        """Should limit results to max_ips"""
        records = [
            IPRecord(f"{i}.{i}.{i}.{i}", 20, "fail", "fail", False, False, "none", "test.com")
            for i in range(1, 31)  # 30 high-risk IPs
        ]

        high_risk, excessive = filter_high_risk_ips(records, max_ips=10, min_risk_score=40)

        assert len(high_risk) == 10

    def test_filter_detects_excessive_failures(self):
        """Should set excessive flag when failures exceed max"""
        records = [
            IPRecord(f"{i}.{i}.{i}.{i}", 20, "fail", "fail", False, False, "none", "test.com")
            for i in range(1, 31)  # 30 IPs
        ]

        high_risk, excessive = filter_high_risk_ips(records, max_ips=20, min_risk_score=40)

        assert excessive is True

    def test_filter_sorts_by_risk_score(self):
        """Should return IPs sorted by risk score (descending)"""
        records = [
            IPRecord("1.1.1.1", 1, "fail", "fail", False, False, "none", "test.com"),   # Score: 50
            IPRecord("2.2.2.2", 15, "fail", "fail", False, False, "none", "test.com"),  # Score: 65
            IPRecord("3.3.3.3", 5, "fail", "fail", False, False, "none", "test.com"),   # Score: 60
        ]

        high_risk, excessive = filter_high_risk_ips(records, max_ips=20, min_risk_score=40)

        # Should be ordered: 2.2.2.2 (65) > 3.3.3.3 (60) > 1.1.1.1 (50)
        assert high_risk[0].ip == "2.2.2.2"
        assert high_risk[1].ip == "3.3.3.3"
        assert high_risk[2].ip == "1.1.1.1"


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_empty_xml(self):
        """Should handle empty XML gracefully"""
        xml = """<?xml version="1.0"?><feedback></feedback>"""

        failed_ips = extract_failed_ips_from_xml(xml)

        assert len(failed_ips) == 0

    def test_missing_source_ip(self):
        """Should skip records without source_ip"""
        xml = """<?xml version="1.0"?>
        <feedback>
            <record>
                <row>
                    <count>5</count>
                </row>
                <identifiers><header_from>test.com</header_from></identifiers>
                <auth_results>
                    <spf><result>fail</result></spf>
                    <dkim><result>fail</result></dkim>
                </auth_results>
            </record>
        </feedback>
        """

        failed_ips = extract_failed_ips_from_xml(xml)

        assert len(failed_ips) == 0

    def test_no_high_risk_ips(self):
        """Should return empty list when no IPs meet threshold"""
        records = [
            IPRecord("1.1.1.1", 1, "fail", "pass", False, True, "none", "test.com"),  # Score: 25
            IPRecord("2.2.2.2", 1, "pass", "fail", True, False, "none", "test.com"),  # Score: 25
        ]

        high_risk, excessive = filter_high_risk_ips(records, max_ips=20, min_risk_score=50)

        assert len(high_risk) == 0
        assert excessive is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
