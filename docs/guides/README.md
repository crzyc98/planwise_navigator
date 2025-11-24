# Implementation Guides

This folder contains practical guides for developers, operators, and contributors working with Fidelity PlanAlign Engine.

## 📚 Guide Categories

### 👨‍💻 [developer/](developer/) - Developer Guides
Essential guides for developers working on Fidelity PlanAlign Engine:

- **[environment_setup.md](developer/environment_setup.md)** - Development Environment Setup
  - Local development prerequisites
  - Python environment configuration
  - Database setup and initialization
  - IDE configuration recommendations

- **[modular_pipeline.md](developer/modular_pipeline.md)** - Modular Pipeline Development
  - Working with Dagster assets and operations
  - Pipeline debugging and testing
  - Code organization patterns
  - Best practices for maintainable code

- **[employee_identifier_strategy.md](developer/employee_identifier_strategy.md)** - Employee ID Management
  - ID generation patterns and uniqueness
  - Data quality validation
  - Migration strategies for legacy data
  - Troubleshooting ID conflicts

- **[layered_defense_implementation.md](developer/layered_defense_implementation.md)** - Layered Defense Implementation
  - CI/CD safeguards and testing
  - Pre-commit hook setup
  - Data quality validation
  - Regression testing strategies

### 🚀 [deployment/](deployment/) - Deployment & Operations
Guides for deploying and operating Fidelity PlanAlign Engine:

- **[troubleshooting.md](deployment/troubleshooting.md)** - Troubleshooting Guide
  - Common issues and solutions
  - Performance debugging
  - Error message reference
  - Escalation procedures

### 🔄 [migration/](migration/) - Migration Procedures
Guides for system migrations and upgrades:

- **[pipeline_refactoring.md](migration/pipeline_refactoring.md)** - Pipeline Refactoring Migration
  - Migration from legacy pipeline to modular architecture
  - Step-by-step migration procedure
  - Rollback strategies
  - Validation checkpoints

- **[duckdb_serialization_fix.md](migration/duckdb_serialization_fix.md)** - DuckDB Serialization Fix
  - Resolving DuckDB object serialization issues
  - Best practices for DuckDB integration
  - Connection management patterns
  - Performance optimization

## 🎯 Target Audiences

### New Team Members
**Start Here**: [developer/environment_setup.md](developer/environment_setup.md)
1. Set up development environment
2. Read [../architecture/overview.md](../architecture/overview.md) for system understanding
3. Review [developer/modular_pipeline.md](developer/modular_pipeline.md) for development patterns

### Experienced Developers
- **Pipeline Development**: [developer/modular_pipeline.md](developer/modular_pipeline.md)
- **Data Quality**: [developer/employee_identifier_strategy.md](developer/employee_identifier_strategy.md)
- **Testing**: [developer/layered_defense_implementation.md](developer/layered_defense_implementation.md)

### Operations Team
- **Troubleshooting**: [deployment/troubleshooting.md](deployment/troubleshooting.md)
- **Migrations**: [migration/](migration/) folder

### DevOps Engineers
- **Deployment**: [deployment/](deployment/) folder
- **CI/CD**: [developer/layered_defense_implementation.md](developer/layered_defense_implementation.md)

## 🔗 Related Documentation

- **Requirements**: [../requirements/](../requirements/) - Understanding business context
- **Architecture**: [../architecture/](../architecture/) - Technical design decisions
- **Epics**: [../epics/](../epics/) - Feature development planning
- **Reference**: [../reference/](../reference/) - Quick lookup information

## 💡 Guide Principles

### Practical Focus
- **Actionable**: Step-by-step procedures
- **Tested**: All instructions verified in real environments
- **Current**: Regularly updated for latest versions

### Developer Experience
- **Clear Examples**: Code samples and command examples
- **Context**: Why certain approaches are recommended
- **Troubleshooting**: Common issues and solutions

### Maintainability
- **Version Aware**: Specify tool and library versions
- **Cross-referenced**: Links to related documentation
- **Feedback Loop**: Regular review and updates

## 📝 Guide Status

| Guide | Last Updated | Reviewer | Status |
|-------|-------------|----------|--------|
| environment_setup.md | 2024 | DevOps Team | Current |
| modular_pipeline.md | 2025 | Platform Team | Current |
| employee_identifier_strategy.md | 2025 | Data Team | Current |
| layered_defense_implementation.md | 2025 | QA Team | Current |
| troubleshooting.md | 2024 | Support Team | Current |
| pipeline_refactoring.md | 2025 | Platform Team | Current |
| duckdb_serialization_fix.md | 2024 | Data Team | Current |

## 🤝 Contributing

When creating or updating guides:

1. **Audience Focus**: Write for specific user personas
2. **Testing**: Verify all steps work in clean environment
3. **Screenshots**: Include visual aids where helpful
4. **Maintenance**: Keep guides current with codebase changes
5. **Feedback**: Incorporate user feedback and common questions

## 🆘 Need Help?

If these guides don't answer your question:

1. **Check**: [deployment/troubleshooting.md](deployment/troubleshooting.md)
2. **Search**: [../reference/](../reference/) for additional resources
3. **Ask**: Team lead or designated guide maintainer

---

*These guides reflect current best practices. For historical context, see [../sessions/](../sessions/) and [../archive/](../archive/).*
