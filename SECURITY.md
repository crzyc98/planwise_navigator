# filename: SECURITY.md

# PlanWise Navigator Security Model

## Threat Model Analysis

| Threat ID | Category | Description | Impact | Likelihood | Risk Level | Mitigation |
|-----------|----------|-------------|---------|------------|------------|------------|
| T001 | Data Exposure | Unauthorized access to employee PII in DuckDB files | High | Medium | High | File system permissions, encryption at rest |
| T002 | Injection | SQL injection via user-supplied parameters | High | Low | Medium | Parameterized queries, Pydantic validation |
| T003 | Access Control | Unauthorized dashboard access | Medium | Medium | Medium | OS-level authentication, session management |
| T004 | Data Integrity | Tampering with simulation parameters | High | Low | Medium | Config validation, audit logging |
| T005 | Resource Exhaustion | DoS via large simulation requests | Medium | Medium | Medium | Resource limits, query timeouts |
| T006 | Information Disclosure | Error messages revealing system details | Low | High | Medium | Generic error messages, structured logging |
| T007 | Privilege Escalation | User accessing higher-level data | High | Low | Medium | Role-based access control |
| T008 | Data Leakage | Export of sensitive data | High | Medium | High | Export logging, data masking |
| T009 | Supply Chain | Vulnerable dependencies | Medium | Medium | Medium | Dependency scanning, version pinning |
| T010 | Insider Threat | Malicious internal user | High | Low | Medium | Audit trails, least privilege |

## Security Controls

### Implemented
- [x] Input validation via Pydantic schemas
- [x] Parameterized SQL queries (no string concatenation)
- [x] Dependency version pinning
- [x] Error handling without stack traces in production
- [x] File system permissions for DuckDB files

### Planned (TODO)
- [ ] Encryption at rest for DuckDB files
- [ ] Role-based access control in Streamlit
- [ ] Audit logging for all data access
- [ ] PII masking for exports
- [ ] Security scanning in CI/CD

## Compliance Considerations

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| PII Protection | Partial | File permissions, planned encryption |
| Access Logging | TODO | Audit trail implementation needed |
| Data Retention | TODO | Automated cleanup policies needed |
| Right to Delete | TODO | PII removal procedures needed |

## Incident Response

1. **Detection**: Monitor logs for anomalies
2. **Containment**: Disable affected user accounts
3. **Investigation**: Review audit logs
4. **Remediation**: Apply fixes, update controls
5. **Recovery**: Restore from backups if needed
6. **Lessons Learned**: Update threat model

## Security Contacts

- Security Team: security@company.com
- Data Protection Officer: dpo@company.com
- Incident Response: incident-response@company.com