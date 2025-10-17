import pytest
import os
from server.agents import review_diff, enforce_rules, majority_vote

@pytest.fixture
def mock_mode():
    """Set MOCK_MODE=1 for tests"""
    os.environ["MOCK_MODE"] = "1"
    yield
    os.environ.pop("MOCK_MODE", None)

def test_basic_review(mock_mode):
    """Test basic review functionality returns expected structure"""
    diff = "def hello():\n    return 'world'"
    meta = {"repo": "test"}
    
    result = review_diff(diff, meta)
    
    # Check required keys
    assert "verdict" in result
    assert "summary" in result
    assert "findings" in result
    
    # Check verdict is valid
    assert result["verdict"] in {"approve", "needs_changes", "block"}
    
    # Check findings structure
    assert isinstance(result["findings"], list)
    assert len(result["findings"]) == 3  # Three agents

def test_rules_block_on_security_high(mock_mode):
    """Test that security:high issues trigger blocking regardless of majority"""
    # Create findings where majority would approve but security:high exists
    findings = [
        type('AgentFinding', (), {"agent": "linter", "verdict": "approve", "summary": "Good style", "issues": []})(),
        type('AgentFinding', (), {"agent": "complexity", "verdict": "approve", "summary": "Simple code", "issues": []})(),
        type('AgentFinding', (), {
            "agent": "security", 
            "verdict": "needs_changes", 
            "summary": "Security issue", 
            "issues": [{"type": "security", "severity": "high", "message": "SQL injection risk", "line": 10}]
        })()
    ]
    
    majority = majority_vote(findings)
    meta = {"repo": "test"}
    
    result = enforce_rules(findings, majority, meta)
    
    # Should block due to security:high despite majority approve
    assert result == "block"

def test_rules_auto_approve_only_docs(mock_mode):
    """Test auto-approval for documentation-only changes"""
    # Create findings that would normally need changes
    findings = [
        type('AgentFinding', (), {"agent": "linter", "verdict": "needs_changes", "summary": "Style issues", "issues": []})(),
        type('AgentFinding', (), {"agent": "complexity", "verdict": "needs_changes", "summary": "Complex code", "issues": []})(),
        type('AgentFinding', (), {"agent": "security", "verdict": "needs_changes", "summary": "Security concerns", "issues": []})()
    ]
    
    majority = majority_vote(findings)  # Would be "needs_changes"
    meta = {"only_docs": True}
    
    result = enforce_rules(findings, majority, meta)
    
    # Should auto-approve due to only_docs=true
    assert result == "approve"
