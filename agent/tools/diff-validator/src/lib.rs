//! Static validation of agent-proposed C-kernel diffs.
//!
//! Parses unified diffs into the set of *added* lines (with file + new line
//! number) and applies freestanding-kernel coding rules. Pure functions — the
//! binary in `main.rs` only handles I/O.

use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Severity {
    Error,
    Warning,
    Info,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Finding {
    pub severity: Severity,
    pub file: String,
    pub line: usize,
    pub rule: String,
    pub message: String,
}

/// An added (`+`) line in a unified diff, with its file and new-file line number.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AddedLine {
    pub file: String,
    pub line: usize,
    pub content: String,
}

/// Parse the `+c,d` new-file start line from a hunk header `@@ -a,b +c,d @@`.
fn parse_hunk_start(header: &str) -> Option<usize> {
    let plus = header.split('+').nth(1)?;
    let num: String = plus.chars().take_while(|c| c.is_ascii_digit()).collect();
    num.parse().ok()
}

/// Strip a `+++ b/path` (or `a/path`) prefix to the bare path.
fn strip_path_prefix(raw: &str) -> String {
    let raw = raw.trim();
    raw.strip_prefix("a/")
        .or_else(|| raw.strip_prefix("b/"))
        .unwrap_or(raw)
        .to_string()
}

/// Extract every added line from a unified diff.
pub fn parse_added_lines(diff: &str) -> Vec<AddedLine> {
    let mut added = Vec::new();
    let mut current_file = String::new();
    let mut new_lineno = 0usize;

    for line in diff.lines() {
        if let Some(rest) = line.strip_prefix("+++ ") {
            current_file = strip_path_prefix(rest);
        } else if line.starts_with("@@") {
            if let Some(start) = parse_hunk_start(line) {
                new_lineno = start;
            }
        } else if let Some(rest) = line.strip_prefix('+') {
            // Ignore the file header line "+++"; handled above.
            if !line.starts_with("+++") {
                added.push(AddedLine {
                    file: current_file.clone(),
                    line: new_lineno,
                    content: rest.to_string(),
                });
                new_lineno += 1;
            }
        } else if line.starts_with('-') && !line.starts_with("---") {
            // Removed line: does not advance the new-file counter.
        } else {
            // Context line (or other): advances the new-file counter.
            new_lineno += 1;
        }
    }
    added
}

const HOSTED_HEADERS: &[&str] = &[
    "<stdio.h>",
    "<stdlib.h>",
    "<string.h>",
    "<stdio>",
    "<assert.h>",
    "<math.h>",
];

/// Apply freestanding-kernel rules to the added lines of a diff.
pub fn validate(diff: &str) -> Vec<Finding> {
    let mut findings = Vec::new();

    for added in parse_added_lines(diff) {
        let content = &added.content;
        let trimmed = content.trim_start();

        // ERROR: hosted libc headers are unavailable in a freestanding kernel.
        if trimmed.starts_with("#include") {
            for h in HOSTED_HEADERS {
                if content.contains(h) {
                    findings.push(Finding {
                        severity: Severity::Error,
                        file: added.file.clone(),
                        line: added.line,
                        rule: "hosted-libc-header".into(),
                        message: format!(
                            "hosted libc header {h} not available in freestanding kernel"
                        ),
                    });
                }
            }
        }

        // WARNING: leftover TODO/FIXME markers.
        if content.contains("TODO") || content.contains("FIXME") {
            findings.push(Finding {
                severity: Severity::Warning,
                file: added.file.clone(),
                line: added.line,
                rule: "todo-marker".into(),
                message: "added line contains a TODO/FIXME marker".into(),
            });
        }

        // INFO: trailing whitespace.
        if content.ends_with(' ') || content.ends_with('\t') {
            findings.push(Finding {
                severity: Severity::Info,
                file: added.file.clone(),
                line: added.line,
                rule: "trailing-whitespace".into(),
                message: "added line has trailing whitespace".into(),
            });
        }
    }

    findings
}

/// True if any finding is an error (used to set the process exit code).
pub fn has_errors(findings: &[Finding]) -> bool {
    findings.iter().any(|f| f.severity == Severity::Error)
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = "\
--- a/kernel/mm/pmm.c
+++ b/kernel/mm/pmm.c
@@ -10,3 +10,6 @@ void pmm_init(void)
 	int existing = 0;
+	int fresh = 1;
-	int removed = 2;
+	int trailing = 3; \n+#include <stdlib.h>
";

    #[test]
    fn parses_added_lines_with_correct_numbers() {
        let added = parse_added_lines(SAMPLE);
        assert_eq!(added.len(), 3);
        assert_eq!(added[0].file, "kernel/mm/pmm.c");
        assert_eq!(added[0].line, 11); // line 10 is context, 11 is first add
        assert_eq!(added[0].content, "\tint fresh = 1;");
    }

    #[test]
    fn flags_hosted_header_as_error() {
        let findings = validate(SAMPLE);
        assert!(findings
            .iter()
            .any(|f| f.rule == "hosted-libc-header" && f.severity == Severity::Error));
        assert!(has_errors(&findings));
    }

    #[test]
    fn flags_trailing_whitespace_as_info() {
        let findings = validate("+++ b/x.c\n@@ -0,0 +1,1 @@\n+int x = 1; ");
        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].severity, Severity::Info);
        assert_eq!(findings[0].rule, "trailing-whitespace");
    }

    #[test]
    fn flags_todo_marker_as_warning() {
        let findings = validate("+++ b/x.c\n@@ -0,0 +1,1 @@\n+/* TODO: implement */");
        assert!(findings.iter().any(|f| f.rule == "todo-marker"));
        assert!(!has_errors(&findings));
    }

    #[test]
    fn clean_diff_has_no_findings() {
        let findings = validate("+++ b/x.c\n@@ -0,0 +1,1 @@\n+int answer = 42;");
        assert!(findings.is_empty());
    }
}
