# PlanWise Navigator Documentation

Welcome to the PlanWise Navigator documentation! This guide will help you find the information you need quickly and efficiently.

## 📁 Documentation Structure

Our documentation is organized into logical sections by purpose and audience:

### 📋 [requirements/](requirements/)
**Business requirements and specifications**
- Product Requirements Document (PRD)
- Business logic documentation
- Workforce modeling process specifications
- Target audience: Product managers, business analysts, stakeholders

### 🏗️ [architecture/](architecture/)
**Technical design and architecture**
- System architecture overview
- Technical implementation guides
- Dagster and DuckDB patterns
- Target audience: Software architects, senior developers

### 📊 [epics/](epics/)
**Epic documentation and planning**
- Epic specifications (E001-E014)
- Validation frameworks
- High-level feature planning
- Target audience: Project managers, tech leads

### 📚 [guides/](guides/)
**Implementation and developer guides**
- [developer/](guides/developer/) - Developer setup and workflows
- [deployment/](guides/deployment/) - Deployment and operations
- [migration/](guides/migration/) - Migration procedures
- Target audience: Developers, DevOps engineers

### 📖 [reference/](reference/)
**Quick reference and lookup materials**
- Project backlog
- Code structure documentation
- File tree reference
- Target audience: All team members

### 📝 [sessions/](sessions/)
**Historical session notes and records**
- Session summaries organized by year
- Story completion records
- Analysis findings
- Target audience: Project historians, audit purposes

### 🗄️ [archive/](archive/)
**Deprecated and historical content**
- Outdated documentation
- Legacy implementation notes
- Target audience: Reference only

## 🚀 Quick Start

### New Team Members
1. Start with [requirements/overview.md](requirements/overview.md) for project context
2. Read [architecture/overview.md](architecture/overview.md) for technical understanding
3. Follow [guides/developer/environment_setup.md](guides/developer/environment_setup.md) for local setup

### Developers
- **Setup**: [guides/developer/environment_setup.md](guides/developer/environment_setup.md)
- **Workflows**: [guides/developer/modular_pipeline.md](guides/developer/modular_pipeline.md)
- **Troubleshooting**: [guides/deployment/troubleshooting.md](guides/deployment/troubleshooting.md)

### Project Managers
- **Current Status**: [reference/backlog.csv](reference/backlog.csv)
- **Epic Planning**: [epics/](epics/) folder
- **Requirements**: [requirements/](requirements/) folder

## 📚 Documentation Standards

### Naming Conventions
- **Files**: snake_case.md (e.g., `environment_setup.md`)
- **Folders**: lowercase with underscores (e.g., `story_completions/`)
- **Epics**: E### format (e.g., `E014_layered_defense.md`)

### Content Guidelines
- Each document should have a clear purpose and audience
- Include creation/modification dates in frontmatter when relevant
- Use consistent markdown formatting
- Include navigation links to related documents

## 🔍 Finding Information

### By Topic
- **Business Logic**: [requirements/business_logic.md](requirements/business_logic.md)
- **Technical Patterns**: [architecture/](architecture/) folder
- **Development Workflows**: [guides/developer/](guides/developer/) folder
- **Operational Procedures**: [guides/deployment/](guides/deployment/) folder

### By Epic/Story
- **Epic Documentation**: [epics/](epics/) folder
- **Individual Stories**: [stories/](stories/) folder
- **Completion Records**: [sessions/story_completions/](sessions/story_completions/) folder

### By Date
- **2024 Sessions**: [sessions/2024/](sessions/2024/) folder
- **2025 Sessions**: [sessions/2025/](sessions/2025/) folder
- **Historical**: [archive/](archive/) folder

## 🤝 Contributing

When adding new documentation:

1. **Choose the right location** based on purpose and audience
2. **Follow naming conventions** for consistency
3. **Add navigation links** to help others find related content
4. **Update this README** if adding new top-level sections

## 📞 Questions?

- **Technical Questions**: Check [guides/developer/](guides/developer/) first
- **Project Questions**: Review [epics/](epics/) and [requirements/](requirements/)
- **Operational Issues**: See [guides/deployment/troubleshooting.md](guides/deployment/troubleshooting.md)

---

*This documentation structure was reorganized in 2025 to improve discoverability and maintainability. If you can't find what you're looking for, check the [archive/](archive/) folder for historical content.*
