# Security Audit Report - Nanobot

**Date:** February 18, 2026  
**Version Audited:** 0.1.4  
**Audit Type:** Comprehensive Security Review  
**Auditor:** GitHub Copilot Security Agent

---

## Executive Summary

This report documents the findings of a comprehensive security audit of the nanobot codebase. The audit examined authentication, authorization, input validation, command execution, data handling, and third-party integrations.

**Overall Assessment:** The codebase demonstrates good security awareness with multiple protection mechanisms in place. However, several areas require attention for production deployments.

### Risk Summary

| Severity | Count | Status |
|----------|-------|--------|
| 🔴 Critical | 2 | Documented |
| 🟡 Medium | 4 | Documented |
| 🟢 Low | 3 | Documented |
| ✅ Good Practice | 5 | Noted |

---

## Critical Findings

### 🔴 C-1: MCP Server Command Injection Risk

**File:** `nanobot/agent/tools/mcp.py` (lines 56-58)  
**Severity:** Critical  
**Impact:** Remote code execution if MCP server configuration is compromised

**Description:**  
The MCP (Model Context Protocol) integration directly passes user-configurable command and arguments to `StdioServerParameters` without validation or sanitization. If an attacker can modify the configuration file or inject malicious MCP server configurations, they can execute arbitrary commands.

```python
params = StdioServerParameters(
    command=cfg.command, args=cfg.args, env=cfg.env or None
)
```

**Attack Vector:**
1. Attacker modifies `~/.nanobot/config.json` with malicious MCP server config
2. Configuration includes: `{"command": "bash", "args": ["-c", "rm -rf /"]}`
3. On agent startup, arbitrary command executes with bot's privileges

**Recommendation:**
- Implement whitelist of allowed MCP commands (e.g., `npx`, `node`, `python`)
- Validate command paths are absolute and exist
- Sanitize all arguments to prevent shell injection
- Consider sandboxing MCP server execution
- Document security requirements in MCP server setup guide

**Mitigation Priority:** HIGH - This should be addressed before production use

---

### 🔴 C-2: Default Open Access Control

**File:** `nanobot/channels/base.py` (lines 61-84)  
**Severity:** Critical (for production deployments)  
**Impact:** Unauthorized users can control the bot if `allowFrom` not configured

**Description:**  
The default behavior allows ANY user to interact with the bot if the `allow_from` list is empty. While this is documented as "open by default for personal use," it poses significant risk if deployed without proper configuration.

```python
def is_allowed(self, sender_id: str) -> bool:
    allow_list = getattr(self.config, "allow_from", [])
    
    # If no allow list, allow everyone
    if not allow_list:
        return True
```

**Attack Scenarios:**
1. Bot deployed to public Telegram bot without `allow_from` configuration
2. Anyone can send messages and execute commands via exec tool
3. Sensitive data exposure through conversation history
4. Resource exhaustion from unlimited requests

**Recommendation:**
- Add startup warning if any enabled channel has empty `allow_from`
- Consider making `allow_from` required (fail-safe default)
- Implement rate limiting per user
- Add audit logging for all access attempts (allowed and denied)
- Document this clearly in deployment guides

**Current State:** Well documented in SECURITY.md, but easy to overlook

---

## Medium Severity Findings

### 🟡 M-1: Shell Command Execution Deny-List Bypass

**File:** `nanobot/agent/tools/shell.py` (lines 25-34, 111-144)  
**Severity:** Medium  
**Impact:** Potential bypass of command safety guards

**Description:**  
The shell execution tool uses regex-based deny-list patterns to block dangerous commands. This approach has known limitations:

1. **Command obfuscation:** `r''m -rf /` bypasses `\brm\s+-[rf]{1,2}\b`
2. **Variable expansion:** `EVIL='rm -rf'; $EVIL /` bypasses pattern matching
3. **Subshell execution:** `$(rm -rf /)` or backticks evade detection
4. **Encoded commands:** Base64 encoded payloads bypass all patterns
5. **Shell built-ins:** Many dangerous operations aren't blocked

**Current Protections:**
✅ Timeout enforcement (60s default)  
✅ Output truncation (10KB)  
✅ Path traversal detection when `restrict_to_workspace=True`  
⚠️ Deny-list is incomplete and bypassable

**Recommendation:**
- Switch to allow-list approach for production environments
- Use `restrict_to_workspace=True` by default
- Consider using `subprocess` with list of arguments (not shell)
- Add command logging for audit trail
- Document limitations clearly

**Risk Level:** MEDIUM - Mitigated by proper configuration and monitoring

---

### 🟡 M-2: Plain Text API Key Storage

**File:** `nanobot/config/schema.py` (entire file)  
**Severity:** Medium  
**Impact:** API keys exposed if config file is compromised

**Description:**  
All API keys and secrets are stored in plain text in `~/.nanobot/config.json`:
- LLM provider API keys (OpenAI, Anthropic, etc.)
- Telegram bot tokens
- Discord bot tokens
- Email passwords
- Brave Search API key
- Various platform credentials

**Current Protections:**
✅ Documentation recommends `chmod 600` for config file  
✅ Keys not in version control (`.gitignore` configured)  
⚠️ No encryption at rest  
⚠️ Keys visible in memory and backups

**Recommendation:**
- Implement OS keyring integration (macOS Keychain, Linux Secret Service, Windows Credential Manager)
- Support environment variables as primary method
- Add config file encryption option
- Implement secret rotation mechanism
- Add warning if config file permissions are too open

**Risk Level:** MEDIUM - Acceptable for personal use with proper file permissions

---

### 🟡 M-3: Session Data Privacy

**File:** `nanobot/session/manager.py`  
**Severity:** Medium  
**Impact:** Conversation history exposed if file system is compromised

**Description:**  
Session data (conversation history, context) is stored in JSONL files without encryption:
- Location: `~/.nanobot/sessions/{session_id}.jsonl`
- Contains: Full conversation history, user queries, agent responses
- Sensitive data may accumulate over time

**Current Protections:**
✅ Safe filename generation prevents directory traversal  
✅ Files stored in user home directory  
⚠️ No encryption at rest  
⚠️ No automatic cleanup of old sessions

**Recommendation:**
- Implement session data encryption
- Add session expiry/cleanup mechanism
- Document data retention policy
- Allow users to delete session history
- Consider in-memory only mode for sensitive deployments

**Risk Level:** MEDIUM - Privacy concern for sensitive conversations

---

### 🟡 M-4: WebSocket Bridge Token Security

**File:** `bridge/src/server.ts` (lines 25-32, 43-63)  
**Severity:** Medium  
**Impact:** Unauthorized access to WhatsApp bridge if token not configured

**Description:**  
The WhatsApp bridge supports optional token authentication. When disabled, any process on localhost can connect:

```typescript
if (this.token) {
    // Token auth enabled
} else {
    console.log('🔗 Python client connected');
    this.setupClient(ws);
}
```

**Current Protections:**
✅ Binds to 127.0.0.1 only (not exposed to network)  
✅ Token auth available and documented  
⚠️ Token optional, not enforced  
⚠️ Token transmitted in plain text over WebSocket

**Recommendation:**
- Make `BRIDGE_TOKEN` required (fail-safe default)
- Add startup warning if token not configured
- Consider TLS for production deployments
- Implement token rotation mechanism

**Risk Level:** MEDIUM - Low risk on single-user systems, higher in multi-user environments

---

## Low Severity Findings

### 🟢 L-1: No Rate Limiting

**Impact:** Resource exhaustion from excessive requests  
**Location:** All channel implementations

**Description:**  
No rate limiting is implemented on incoming messages or API calls. While acceptable for personal use, production deployments may be vulnerable to:
- Excessive LLM API costs from spam
- Resource exhaustion from rapid requests
- DoS from malicious users (if access control bypassed)

**Recommendation:**
- Implement per-user rate limiting
- Add global rate limiting for API calls
- Monitor for unusual activity patterns
- Set spending limits on LLM providers

**Risk Level:** LOW - Primarily a cost/availability concern

---

### 🟢 L-2: Limited Audit Logging

**Impact:** Difficult to detect and investigate security incidents  
**Location:** Throughout codebase

**Description:**  
Security events are logged at warning level but lack comprehensive audit trail:
- Access denials logged but no successful access tracking
- No command execution audit log
- No API key usage tracking
- Limited metadata in security logs

**Recommendation:**
- Implement structured security audit logging
- Log all access attempts (successful and failed)
- Log all command executions with full details
- Add correlation IDs for incident investigation
- Consider sending security logs to external system

**Risk Level:** LOW - Reduces incident response capabilities

---

### 🟢 L-3: Dependency Version Pinning

**Impact:** Potential security vulnerabilities in dependencies  
**Location:** `pyproject.toml`, `bridge/package.json`

**Description:**  
Dependencies use minimum version constraints (e.g., `>=1.0.0`) rather than pinned versions. This is flexible but may introduce vulnerabilities from transitive dependencies.

**Current State:**
✅ `ws` updated to `^8.17.1` to fix DoS vulnerability (CVE-2024-37890)  
✅ Dependencies fairly up-to-date  
⚠️ No automated dependency scanning in CI/CD  
⚠️ Transitive dependencies not pinned

**Recommendation:**
- Add `pip-audit` to CI/CD pipeline
- Add `npm audit` to CI/CD pipeline
- Consider using lock files (`poetry.lock`, `package-lock.json`)
- Set up automated dependency update PRs (Dependabot)
- Subscribe to security advisories for key dependencies

**Risk Level:** LOW - Good practices already in place, room for improvement

---

## Good Security Practices Identified

### ✅ G-1: Input Validation and Sanitization

**Location:** `nanobot/agent/tools/web.py`

**Strengths:**
- URL validation enforces http/https schemes
- Redirect limit (5 max) prevents DoS
- HTML sanitization before parsing
- Script and style tag removal
- Entity encoding and escaping

```python
def _validate_url(url: str) -> tuple[bool, str]:
    """Validate URL: must be http(s) with valid domain."""
    try:
        p = urlparse(url)
        if p.scheme not in ('http', 'https'):
            return False, f"Only http/https allowed"
        if not p.netloc:
            return False, "Missing domain"
        return True, ""
    except Exception as e:
        return False, str(e)
```

---

### ✅ G-2: Timeout Enforcement

**Location:** Multiple files

**Strengths:**
- Shell command execution: 60s timeout
- HTTP requests: 10-30s timeouts
- WebSocket auth: 5s timeout
- Process communication timeouts

Prevents resource exhaustion from hanging operations.

---

### ✅ G-3: Output Truncation

**Location:** `nanobot/agent/tools/shell.py`

**Strengths:**
- Command output limited to 10KB
- Large responses truncated gracefully
- Prevents memory exhaustion

---

### ✅ G-4: Path Traversal Protection

**Location:** `nanobot/agent/tools/shell.py`, `nanobot/session/manager.py`

**Strengths:**
- Detects `../` and `..\` patterns
- Validates absolute paths against workspace
- Safe filename generation for sessions
- Path resolution and validation

---

### ✅ G-5: Secure Defaults in Documentation

**Location:** `SECURITY.md`

**Strengths:**
- Comprehensive security best practices guide
- Clear documentation of security limitations
- Production deployment checklist
- Incident response procedures
- Regular security updates in release notes

The SECURITY.md file is exceptionally thorough and demonstrates security awareness.

---

## Recommendations Summary

### Immediate Actions (Before Production Use)

1. **Add MCP command validation** - Whitelist allowed commands
2. **Enforce `allow_from` configuration** - Add startup warnings
3. **Enable bridge token authentication** - Make required
4. **Implement audit logging** - Track all security events

### Short-term Improvements

1. **Add rate limiting** - Prevent abuse and cost overruns
2. **Implement keyring support** - Encrypt API keys at rest
3. **Add dependency scanning** - Automate vulnerability detection
4. **Enhance command filtering** - Consider allow-list approach

### Long-term Enhancements

1. **Session encryption** - Protect conversation history
2. **Sandboxed tool execution** - Isolate command execution
3. **Security monitoring** - Automated anomaly detection
4. **Regular security audits** - Quarterly reviews

---

## Testing Recommendations

### Security Test Suite

Create tests for:
1. MCP command injection attempts
2. Shell command bypass techniques
3. Access control enforcement
4. Path traversal attacks
5. Rate limiting effectiveness
6. Token authentication validation

### Penetration Testing

Consider testing:
1. Configuration file manipulation
2. Message flooding and DoS
3. Command injection vectors
4. Session hijacking attempts
5. API key extraction

---

## Compliance Notes

### Data Privacy (GDPR, CCPA)

- ⚠️ Conversation history stored locally (inform users)
- ⚠️ No data deletion mechanism (implement on request)
- ⚠️ LLM providers process user data (document in privacy policy)
- ✅ No telemetry or analytics by default

### API Provider Terms

- Review terms of service for all LLM providers
- Ensure compliance with rate limits
- Respect usage restrictions
- Monitor for policy changes

---

## Conclusion

The nanobot codebase demonstrates strong security awareness with multiple layers of protection. The SECURITY.md documentation is comprehensive and shows good security practices.

**Key Strengths:**
- Good input validation and sanitization
- Comprehensive security documentation
- Timeout and resource protection mechanisms
- Regular security updates

**Areas for Improvement:**
- MCP command validation (critical for production)
- Enforce access control configuration (critical for production)
- Enhanced audit logging
- API key encryption

**Production Readiness:**  
With the recommended critical fixes implemented, nanobot can be safely deployed in production environments following the security best practices outlined in SECURITY.md.

---

## Appendix: Security Checklist for Deployment

Before deploying nanobot to production, verify:

- [ ] All `allow_from` lists configured for enabled channels
- [ ] Config file permissions set to 0600
- [ ] Running as non-root user with limited privileges
- [ ] Bridge token authentication enabled
- [ ] Dependencies updated to latest secure versions
- [ ] Rate limits configured on LLM provider accounts
- [ ] Audit logging enabled and monitored
- [ ] Regular backup of configuration and sessions
- [ ] Incident response plan documented
- [ ] MCP server commands validated (if MCP enabled)
- [ ] File system permissions properly restricted
- [ ] Network firewall configured (if applicable)

---

## References

- SECURITY.md - Comprehensive security guide
- CVE-2024-37890 - ws DoS vulnerability (fixed in 8.17.1)
- OWASP Top 10 - Web application security risks
- CWE-78 - OS Command Injection
- CWE-22 - Path Traversal

---

**Report Version:** 1.0  
**Last Updated:** February 18, 2026
