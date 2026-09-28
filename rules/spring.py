"""
rules/spring.py
---------------
Deterministic rule-based detection of Spring Boot change patterns.
Kept intentionally separate from LLM and RAG logic.
"""

import re
from dataclasses import dataclass


@dataclass
class Finding:
    category: str    # endpoint | dto | entity | security | config
    severity: str    # low | medium | high
    description: str
    file: str = ""
    detail: str = ""


# Patterns
_ENDPOINT = re.compile(
    r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)"
    r"(\([^)]*\))?"
)
_SECURITY = re.compile(
    r"@(PreAuthorize|PostAuthorize|Secured|RolesAllowed|EnableWebSecurity"
    r"|EnableMethodSecurity|FilterChain|SecurityFilterChain|csrf|CorsConfiguration"
    r"|authorizeHttpRequests|permitAll|authenticated)"
    r"(\([^)]*\))?"
)
_ENTITY = re.compile(
    r"@(Entity|Table|Column|Id|GeneratedValue|ManyToOne|OneToMany|ManyToMany"
    r"|OneToOne|JoinColumn|JoinTable)"
    r"(\([^)]*\))?"
)
_DTO_NAME = re.compile(r"(Request|Response|Dto|DTO|Payload|Body)")
_CONFIG = re.compile(
    r"@(Configuration|Bean|ConfigurationProperties|Value|PropertySource|Profile"
    r"|ConditionalOnProperty|EnableAutoConfiguration)"
    r"(\([^)]*\))?"
)
_FIELD = re.compile(r"^\s*(private|public|protected)\s+\S+\s+\w+")


def analyse(diff_text: str) -> list:
    """Parse unified diff and return list of Finding objects."""
    findings = []
    current_file = ""

    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            current_file = _extract_filename(line)
            continue
        if not current_file.endswith(".java"):
            continue

        is_added = line.startswith("+") and not line.startswith("+++")
        is_removed = line.startswith("-") and not line.startswith("---")
        if not (is_added or is_removed):
            continue

        code = line[1:]
        change_type = "added" if is_added else "removed"

        m = _ENDPOINT.search(code)
        if m:
            findings.append(Finding(
                category="endpoint", severity="high",
                description=f"HTTP endpoint {change_type}: @{m.group(1)}{m.group(2) or ''} in {current_file}",
                file=current_file, detail=code.strip(),
            ))

        m = _SECURITY.search(code)
        if m:
            findings.append(Finding(
                category="security", severity="high",
                description=f"Security annotation {change_type}: @{m.group(1)} in {current_file}",
                file=current_file, detail=code.strip(),
            ))

        m = _ENTITY.search(code)
        if m:
            sev = "high" if m.group(1) in ("Entity", "Table", "Column", "Id") else "medium"
            findings.append(Finding(
                category="entity", severity=sev,
                description=(
                    f"JPA/Entity annotation {change_type}: @{m.group(1)} in {current_file}. "
                    "A database migration may be needed."
                ),
                file=current_file, detail=code.strip(),
            ))

        if _DTO_NAME.search(current_file) or _DTO_NAME.search(code):
            if _FIELD.match(code):
                findings.append(Finding(
                    category="dto", severity="medium",
                    description=f"DTO field {change_type} in {current_file}. API consumers may need updating.",
                    file=current_file, detail=code.strip(),
                ))

        m = _CONFIG.search(code)
        if m:
            findings.append(Finding(
                category="config", severity="medium",
                description=f"Configuration annotation {change_type}: @{m.group(1)} in {current_file}",
                file=current_file, detail=code.strip(),
            ))

    return _dedup(findings)


def summarise(findings: list) -> dict:
    by_cat = {}
    sev_order = {"low": 0, "medium": 1, "high": 2}
    highest = "low"
    for f in findings:
        by_cat[f.category] = by_cat.get(f.category, 0) + 1
        if sev_order.get(f.severity, 0) > sev_order.get(highest, 0):
            highest = f.severity
    return {"highest_severity": highest, "by_category": by_cat, "total": len(findings)}


def _extract_filename(header):
    m = re.search(r"b/(.+)$", header)
    return m.group(1) if m else ""


def _dedup(findings):
    seen = set()
    out = []
    for f in findings:
        key = (f.category, f.description, f.file)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out
