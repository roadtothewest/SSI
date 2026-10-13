package record

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadMarksReadsTheSessionMetadata(t *testing.T) {
	dir := t.TempDir()
	js := `{"blockSize": 538, "blocks": 900, "marks": [{"block": 0, "cond": "reposo"}, {"block": 300, "cond": "vocal"}]}`
	if err := os.WriteFile(filepath.Join(dir, "20261013-150000.json"), []byte(js), 0o644); err != nil {
		t.Fatal(err)
	}
	marks, err := LoadMarks(dir, "20261013-150000.avx")
	if err != nil {
		t.Fatal(err)
	}
	want := []Mark{{0, "reposo"}, {300, "vocal"}}
	if len(marks) != len(want) || marks[0] != want[0] || marks[1] != want[1] {
		t.Fatalf("marks = %v, want %v", marks, want)
	}
}

func TestLoadMarksWithoutMetadataIsEmpty(t *testing.T) {
	marks, err := LoadMarks(t.TempDir(), "sin-json.avx")
	if err != nil || len(marks) != 0 {
		t.Fatalf("marks = %v, err = %v; want none and no error", marks, err)
	}
}

func TestCondAtReportsOnlyTheBlocksWhereTheConditionChanges(t *testing.T) {
	marks := []Mark{{0, "reposo"}, {300, "vocal"}}
	for _, c := range []struct {
		block uint64
		cond  string
		ok    bool
	}{{0, "reposo", true}, {1, "", false}, {299, "", false}, {300, "vocal", true}, {301, "", false}} {
		cond, ok := CondAt(marks, c.block)
		if cond != c.cond || ok != c.ok {
			t.Errorf("CondAt(%d) = %q, %v; want %q, %v", c.block, cond, ok, c.cond, c.ok)
		}
	}
}
