//! Integration tests for unified-diff parsing.

use diff_validator::parse_added_lines;

const DIFF: &str = "\
--- a/kernel/boot/kernel_main.c
+++ b/kernel/boot/kernel_main.c
@@ -5,2 +5,4 @@ void kernel_main(void)
 	serial_init();
+	kprintf(\"hi\\n\");
+	pci_scan();
 	halt();
";

#[test]
fn extracts_only_added_lines() {
    let added = parse_added_lines(DIFF);
    assert_eq!(added.len(), 2);
    assert_eq!(added[0].content, "\tkprintf(\"hi\\n\");");
    assert_eq!(added[1].content, "\tpci_scan();");
}

#[test]
fn tracks_file_and_line_numbers() {
    let added = parse_added_lines(DIFF);
    assert_eq!(added[0].file, "kernel/boot/kernel_main.c");
    // hunk starts at new line 5 (context), so first add is line 6.
    assert_eq!(added[0].line, 6);
    assert_eq!(added[1].line, 7);
}

#[test]
fn empty_diff_yields_no_lines() {
    assert!(parse_added_lines("").is_empty());
}
