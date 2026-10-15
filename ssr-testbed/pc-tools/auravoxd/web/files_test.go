package web

import (
	"bytes"
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"testing"

	"auravoxd/record"
)

func (r *rig) do(t *testing.T, method, path string, body any) int {
	t.Helper()
	js, _ := json.Marshal(body)
	req, _ := http.NewRequest(method, r.srv.URL+path, bytes.NewReader(js))
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	return resp.StatusCode
}

func (r *rig) sessions(t *testing.T) []record.Session {
	t.Helper()
	resp, err := http.Get(r.srv.URL + "/api/files")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var ss []record.Session
	if err := json.NewDecoder(resp.Body).Decode(&ss); err != nil {
		t.Fatal(err)
	}
	return ss
}

func exists(dir, name string) bool {
	_, err := os.Stat(filepath.Join(dir, name))
	return err == nil
}

func TestTheHMIListsOneEntryPerSession(t *testing.T) {
	r := newRig(t)
	ss := r.sessions(t)
	if len(ss) != 1 || ss[0].Name != "s" || !ss[0].Meta || ss[0].Secs != 0.04 {
		t.Fatalf("sessions = %+v, want s with its .json and 4 blocks = 0.04 s", ss)
	}
}

func TestRenamingASessionMovesBothFiles(t *testing.T) {
	r := newRig(t)
	if code := r.post(t, "/api/files/s/rename", map[string]string{"to": " demo reposo "}); code != http.StatusOK {
		t.Fatalf("rename: %d", code)
	}
	dir := r.s.DataDir
	if exists(dir, "s.avx") || exists(dir, "s.json") || !exists(dir, "demo_reposo.avx") || !exists(dir, "demo_reposo.json") {
		t.Fatal("rename did not move the .avx and the .json together")
	}
	if code := r.post(t, "/api/source", map[string]string{"file": "demo_reposo.avx"}); code != http.StatusOK {
		t.Fatalf("play the renamed session: %d", code)
	}
	waitCond(t, r.s.An, "vocal") // its marks followed it
}

func TestRenameRejectsBadNamesAndNeverOverwrites(t *testing.T) {
	r := newRig(t)
	os.WriteFile(filepath.Join(r.s.DataDir, "otra.avx"), nil, 0o644)
	for _, c := range []struct {
		from, to string
		want     int
	}{
		{"s", "../x", http.StatusBadRequest},
		{"s", "x.avx", http.StatusBadRequest},
		{"s", "", http.StatusBadRequest},
		{"s", "otra", http.StatusConflict},
		{"nada", "x", http.StatusNotFound},
	} {
		if code := r.post(t, "/api/files/"+c.from+"/rename", map[string]string{"to": c.to}); code != c.want {
			t.Errorf("rename %q → %q: %d, want %d", c.from, c.to, code, c.want)
		}
	}
	if !exists(r.s.DataDir, "s.avx") || !exists(r.s.DataDir, "s.json") {
		t.Fatal("a rejected rename touched the session")
	}
}

func TestDeletingASessionRemovesBothFiles(t *testing.T) {
	r := newRig(t)
	for _, p := range []string{"..", "%2E%2E", "s.avx", "%2E%2E%2Fs"} {
		if code := r.do(t, http.MethodDelete, "/api/files/"+p, nil); code == http.StatusOK {
			t.Errorf("delete %q: 200", p)
		}
	}
	if !exists(r.s.DataDir, "s.avx") {
		t.Fatal("a bad name deleted the session")
	}
	if code := r.do(t, http.MethodDelete, "/api/files/s", nil); code != http.StatusOK {
		t.Fatalf("delete: %d", code)
	}
	if exists(r.s.DataDir, "s.avx") || exists(r.s.DataDir, "s.json") {
		t.Fatal("delete left files behind")
	}
	if code := r.do(t, http.MethodDelete, "/api/files/s", nil); code != http.StatusNotFound {
		t.Fatalf("delete again: %d, want 404", code)
	}
}

func TestTheSessionOnScreenOrOnDiskCannotBeEdited(t *testing.T) {
	r := newRig(t)
	if code := r.post(t, "/api/source", map[string]string{"file": "s.avx"}); code != http.StatusOK {
		t.Fatalf("play: %d", code)
	}
	if code := r.do(t, http.MethodDelete, "/api/files/s", nil); code != http.StatusConflict {
		t.Fatalf("delete while playing: %d, want 409", code)
	}
	if code := r.post(t, "/api/files/s/rename", map[string]string{"to": "x"}); code != http.StatusConflict {
		t.Fatalf("rename while playing: %d, want 409", code)
	}

	if code := r.post(t, "/api/source", map[string]string{"file": ""}); code != http.StatusOK {
		t.Fatalf("live: %d", code)
	}
	if code := r.post(t, "/api/record", map[string]bool{"on": true}); code != http.StatusOK {
		t.Fatalf("record: %d", code)
	}
	name := r.s.Rec.Status().Name
	if code := r.do(t, http.MethodDelete, "/api/files/"+name, nil); code != http.StatusConflict {
		t.Fatalf("delete while recording: %d, want 409", code)
	}
	if code := r.post(t, "/api/files/s/rename", map[string]string{"to": name}); code != http.StatusConflict {
		t.Fatalf("rename onto the recording: %d, want 409", code)
	}
	r.post(t, "/api/record", map[string]bool{"on": false})
	if code := r.post(t, "/api/files/"+name+"/rename", map[string]string{"to": "grabada"}); code != http.StatusOK {
		t.Fatalf("rename after stopping: %d", code)
	}
}
