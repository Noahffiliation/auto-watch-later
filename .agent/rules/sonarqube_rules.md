---
alwaysApply: true
always_on: true
trigger: always_on
applyTo: "**"
description: SonarQube Quality and Security Best Practices
---

# SonarQube Quality and Security Rules

- **Check Project Status**: After making significant changes (e.g., refactoring, new features, or fixing security issues), always check the SonarQube Quality Gate status and project measures.
- **Clean as You Go**: Focus on resolving issues introduced in the current branch or recently modified code. Use `sonarqube_search_sonar_issues_in_projects` with appropriate filters (e.g., `branch`) to identify new issues.
- **Vulnerability Remediation**: Priority should be given to security vulnerabilities (BLOCKER, HIGH, MEDIUM). Use the context provided by SonarQube to implement fixes and re-verify.
- **Maintain Code Coverage**: Ensure that new code meets the project's coverage requirements (typically 80%+). Verify that coverage report paths are correctly configured in `sonar-project.properties`.
- **Pre-commit Analysis**: When possible, use `sonarqube_analyze_code_snippet` to catch issues before committing code.
- **Quality Gate Compliance**: Ensure that the Quality Gate is always "PASSED" before finalizing work. If a Quality Gate fails, investigate the specific metrics (e.g., coverage, duplicated lines, new vulnerabilities) and address them.
