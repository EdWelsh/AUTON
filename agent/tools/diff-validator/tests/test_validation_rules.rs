//! Integration tests for the validation rules.

use diff_validator::{has_errors, validate, Severity};

#[test]
fn hosted_header_is_an_error() {
    let diff = "+++ b/kernel/mm/pmm.c\n@@ -0,0 +1,1 @@\n+#include <stdlib.h>";
    let findings = validate(diff);
    assert!(has_errors(&findings));
    assert_eq!(findings[0].severity, Severity::Error);
    assert_eq!(findings[0].rule, "hosted-libc-header");
}

#[test]
fn freestanding_local_include_is_clean() {
    let diff = "+++ b/kernel/mm/pmm.c\n@@ -0,0 +1,1 @@\n+#include \"kernel.h\"";
    assert!(validate(diff).is_empty());
}

#[test]
fn todo_is_warning_not_error() {
    let diff = "+++ b/x.c\n@@ -0,0 +1,1 @@\n+\tx(); // FIXME later";
    let findings = validate(diff);
    assert!(!has_errors(&findings));
    assert!(findings.iter().any(|f| f.severity == Severity::Warning));
}

#[test]
fn multiple_findings_on_one_line() {
    // trailing whitespace + TODO on the same added line.
    let diff = "+++ b/x.c\n@@ -0,0 +1,1 @@\n+\tTODO fix ";
    let findings = validate(diff);
    assert!(findings.iter().any(|f| f.rule == "todo-marker"));
    assert!(findings.iter().any(|f| f.rule == "trailing-whitespace"));
}
