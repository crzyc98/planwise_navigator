# filename: docs/RACI.md

# PlanWise Navigator RACI Matrix

## Legend
- **R**: Responsible (Does the work)
- **A**: Accountable (Final decision maker)
- **C**: Consulted (Provides input)
- **I**: Informed (Kept in the loop)

## Stakeholder Key
- **DO**: Data Owner (Chief Data Officer)
- **PO**: Product Owner
- **TL**: Tech Lead
- **DE**: Data Engineer
- **DS**: Data Scientist
- **FE**: Frontend Engineer
- **QA**: QA Engineer
- **BA**: Business Analyst
- **PM**: Project Manager
- **SO**: Security Officer
- **EU**: End Users (HR/Finance)

## Phase 1: Planning & Design

| Activity | DO | PO | TL | DE | DS | FE | QA | BA | PM | SO | EU |
|----------|----|----|----|----|----|----|----|----|----|----|-----|
| Requirements Gathering | C | A | C | I | C | I | I | R | R | C | C |
| Technical Architecture | I | C | A | R | C | C | I | I | I | C | I |
| Data Model Design | C | C | A | R | R | I | I | C | I | I | C |
| UI/UX Design | I | A | C | I | I | R | C | C | I | I | C |
| Security Design | C | I | C | C | I | I | I | I | I | A/R | I |
| Project Planning | I | C | C | I | I | I | I | C | A | I | I |

## Phase 2: Development

| Activity | DO | PO | TL | DE | DS | FE | QA | BA | PM | SO | EU |
|----------|----|----|----|----|----|----|----|----|----|----|-----|
| dbt Model Development | I | I | C | R | C | I | C | I | I | I | I |
| Dagster Pipeline | I | I | A | R | C | I | C | I | I | I | I |
| Simulation Logic | C | C | C | C | R | I | C | A | I | I | C |
| Streamlit Dashboard | I | C | C | I | C | R | C | A | I | I | C |
| API Development | I | I | A | R | I | C | C | I | I | C | I |
| Testing Implementation | I | I | C | C | C | C | R | C | I | I | I |
| Documentation | I | C | C | R | R | R | R | R | C | C | I |

## Phase 3: Testing & Validation

| Activity | DO | PO | TL | DE | DS | FE | QA | BA | PM | SO | EU |
|----------|----|----|----|----|----|----|----|----|----|----|-----|
| Unit Testing | I | I | C | R | R | R | A | I | I | I | I |
| Integration Testing | I | I | C | R | C | R | A | C | I | I | I |
| Performance Testing | I | C | A | R | I | C | R | I | I | I | I |
| Security Testing | C | I | C | C | I | C | R | I | I | A | I |
| UAT Coordination | I | A | I | C | C | C | R | R | C | I | R |
| Data Validation | A | C | C | R | R | I | R | C | I | I | C |

## Phase 4: Deployment & Migration

| Activity | DO | PO | TL | DE | DS | FE | QA | BA | PM | SO | EU |
|----------|----|----|----|----|----|----|----|----|----|----|-----|
| Infrastructure Setup | I | I | A | R | I | I | I | I | C | C | I |
| Data Migration | A | C | C | R | C | I | C | C | I | I | I |
| Deployment Process | I | I | A | R | I | R | C | I | C | C | I |
| Monitoring Setup | I | I | A | R | I | C | C | I | I | C | I |
| Training Delivery | I | C | I | C | C | C | I | R | A | I | R |
| Go-Live Decision | A | A | R | I | I | I | I | C | R | C | C |

## Phase 5: Operations & Support

| Activity | DO | PO | TL | DE | DS | FE | QA | BA | PM | SO | EU |
|----------|----|----|----|----|----|----|----|----|----|----|-----|
| Production Support | I | C | A | R | C | R | C | C | I | I | I |
| Bug Fixes | I | C | A | R | R | R | C | I | I | I | I |
| Feature Requests | C | A | C | C | C | C | I | R | C | I | R |
| Performance Tuning | I | I | A | R | C | C | C | I | I | I | I |
| Security Patching | C | I | R | R | I | R | C | I | I | A | I |
| User Support | I | I | I | C | C | C | I | R | I | I | C |

## Decision Rights

| Decision Type | Final Approver | Key Consulted |
|---------------|----------------|---------------|
| Architecture Changes | Tech Lead | DO, PO, SO |
| Data Model Changes | Data Owner | TL, DE, DS |
| Feature Prioritization | Product Owner | PM, BA, EU |
| Security Policies | Security Officer | DO, TL |
| Release Decisions | Product Owner + Tech Lead | PM, QA |
| Budget Approvals | Data Owner | PO, PM |
| Tool Selection | Tech Lead | DE, DS, FE |
| User Access | Security Officer | DO, BA |

## Escalation Path

1. **Technical Issues**: DE/DS/FE → Tech Lead → Data Owner
2. **Business Issues**: BA/EU → Product Owner → Data Owner
3. **Security Issues**: Any → Security Officer → Data Owner
4. **Project Issues**: Any → Project Manager → Product Owner/Data Owner

## Communication Cadence

| Meeting | Frequency | Required Attendees | Optional |
|---------|-----------|-------------------|----------|
| Daily Standup | Daily | DE, DS, FE, QA | TL, BA |
| Sprint Planning | Bi-weekly | PO, TL, DE, DS, FE, QA, BA | PM |
| Sprint Review | Bi-weekly | All | - |
| Steering Committee | Monthly | DO, PO, TL, PM | SO |
| Architecture Review | Monthly | TL, DE, DS, FE | PO, SO |
| Security Review | Quarterly | SO, TL, DO | PO |

## Notes
- In case of absence, the Accountable person must delegate to an appropriate substitute
- Any changes to this RACI require approval from both the Data Owner and Product Owner
- This matrix will be reviewed and updated quarterly