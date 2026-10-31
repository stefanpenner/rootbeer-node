package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"strconv"
	"strings"
)

// A fileChange is one path of a commit. The GitHub API needs the content, not a working tree.
type fileChange struct {
	Path, Mode string
	Content    []byte
	Deleted    bool
}

type applied struct {
	Changes []fileChange
	Flags   []string // Work that this pull request cannot do. Each flag makes the pull request a draft.
}

type command func(dir string, args ...string) error

const workflowDir = ".github/workflows/"

// apply makes the edit in the tree, records the difference, and always restores the tree.
// So the next update starts from the same tree.
func apply(root string, run command, r runtime, u update) (applied, error) {
	before, err := snapshot(root)
	if err != nil {
		return applied{}, err
	}
	defer restore(root, before)

	var result applied
	if r.Kind == kindNode {
		result.Flags, err = applyNode(root, run, before, u)
	} else {
		err = applyManifest(root, r, u)
	}
	if err != nil {
		return applied{}, err
	}
	if u.NewLine {
		result.Flags = append(result.Flags, fmt.Sprintf(
			"This is a new line (%s). Add its build targets and tests, and regenerate its patches if they do not apply.", u.Line))
	}

	after, err := snapshot(root)
	if err != nil {
		return applied{}, err
	}
	for _, change := range difference(before, after) {
		if strings.HasPrefix(change.Path, workflowDir) {
			// GITHUB_TOKEN has no workflows permission, so GitHub refuses a ref that changes this file.
			result.Flags = append(result.Flags, "Edit "+change.Path+" by hand. GITHUB_TOKEN cannot write a workflow file.")
			continue
		}
		result.Changes = append(result.Changes, change)
	}
	if len(result.Changes) == 0 {
		return applied{}, fmt.Errorf("the update changes no file")
	}
	return result, nil
}

// applyNode tries with patches first. A patch failure must not drop the release,
// so the second try makes the version edit alone and flags the patch work.
func applyNode(root string, run command, before map[string]snapshotFile, u update) ([]string, error) {
	directory, err := os.MkdirTemp("", "bump")
	if err != nil {
		return nil, err
	}
	defer os.RemoveAll(directory)
	shasums := filepath.Join(directory, "SHASUMS256.txt")
	if err := os.WriteFile(shasums, []byte(u.Shasums), 0o600); err != nil {
		return nil, err
	}
	tool := []string{"python3", filepath.Join(root, "tools/add_node_version.py"), u.New, "--shasums", shasums}
	if err := run(root, tool...); err == nil {
		return nil, nil
	}
	if err := restore(root, before); err != nil {
		return nil, err
	}
	if err := run(root, append(tool, "--no-patches")...); err != nil {
		return nil, err
	}
	return []string{fmt.Sprintf("Run tools/make_patches.py for Node %s. The tool could not make the patches.", u.Line)}, nil
}

func applyManifest(root string, r runtime, u update) error {
	path := filepath.Join(root, r.File)
	text, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	edited, err := editManifest(string(text), u)
	if err != nil {
		return fmt.Errorf("%s: %w", r.File, err)
	}
	return os.WriteFile(path, []byte(edited), 0o644)
}

type manifestEntry map[string]string

func manifestEntries(text string) ([]manifestEntry, error) {
	var manifest struct {
		Versions []manifestEntry `json:"versions"`
	}
	err := json.Unmarshal([]byte(text), &manifest)
	return manifest.Versions, err
}

// editManifest changes only the values of one entry, so a diff stays one line for each value.
// It then parses its own result and refuses anything other than the intended change.
func editManifest(text string, u update) (string, error) {
	entries, err := manifestEntries(text)
	if err != nil {
		return "", err
	}
	edited, err := editedText(text, entries, u)
	if err != nil {
		return "", err
	}
	if err := checkEdit(entries, edited, u); err != nil {
		return "", err
	}
	return edited, nil
}

func editedText(text string, entries []manifestEntry, u update) (string, error) {
	if !u.NewLine {
		start, end, err := entrySpan(text, u.Line)
		if err != nil {
			return "", err
		}
		return text[:start] + setValues(text[start:end], u) + text[end:], nil
	}
	top := topEntry(entries)
	if top == nil {
		return "", fmt.Errorf("no numeric line to copy for new line %s", u.Line)
	}
	start, end, err := entrySpan(text, top["line"])
	if err != nil {
		return "", err
	}
	copied := strings.ReplaceAll(text[start:end], top["version"], u.New)
	copied = setValues(copied, u)
	token := regexp.MustCompile(`(^|[^0-9A-Za-z.])` + regexp.QuoteMeta(top["line"]) + `($|[^0-9A-Za-z.])`)
	copied = token.ReplaceAllString(copied, "${1}"+u.Line+"${2}")

	spaceStart := start
	for spaceStart > 0 && strings.ContainsRune(" \t\r\n", rune(text[spaceStart-1])) {
		spaceStart--
	}
	return text[:start] + copied + "," + text[spaceStart:start] + text[start:], nil
}

func entrySpan(text, line string) (int, int, error) {
	pattern := regexp.MustCompile(`"line"\s*:\s*"` + regexp.QuoteMeta(line) + `"`)
	found := pattern.FindStringIndex(text)
	if found == nil {
		return 0, 0, fmt.Errorf("no entry for line %s", line)
	}
	start := strings.LastIndexByte(text[:found[0]], '{')
	length := strings.IndexByte(text[found[1]:], '}')
	if start < 0 || length < 0 {
		return 0, 0, fmt.Errorf("no object around line %s", line)
	}
	return start, found[1] + length + 1, nil
}

var (
	versionField = regexp.MustCompile(`("version"\s*:\s*")[^"]*`)
	sha256Field  = regexp.MustCompile(`("sha256"\s*:\s*")[^"]*`)
)

func setValues(entry string, u update) string {
	entry = versionField.ReplaceAllString(entry, "${1}"+u.New)
	return sha256Field.ReplaceAllString(entry, "${1}"+u.SHA256)
}

func topEntry(entries []manifestEntry) manifestEntry {
	var top manifestEntry
	highest := -1
	for _, entry := range entries {
		if line, err := strconv.Atoi(entry["line"]); err == nil && line > highest {
			top, highest = entry, line
		}
	}
	return top
}

func checkEdit(before []manifestEntry, edited string, u update) error {
	after, err := manifestEntries(edited)
	if err != nil {
		return fmt.Errorf("the edit broke the file: %w", err)
	}
	seen := false
	var others []manifestEntry
	for _, entry := range after {
		if entry["line"] != u.Line {
			others = append(others, entry)
			continue
		}
		if entry["version"] != u.New || entry["sha256"] != u.SHA256 {
			return fmt.Errorf("the entry of line %s does not hold the new values", u.Line)
		}
		seen = true
	}
	var want []manifestEntry
	for _, entry := range before {
		if entry["line"] != u.Line {
			want = append(want, entry)
		}
	}
	sameEntry := func(a, b manifestEntry) bool { return fmt.Sprint(a) == fmt.Sprint(b) }
	if !seen || !slices.EqualFunc(others, want, sameEntry) {
		return fmt.Errorf("the edit changed an entry other than line %s", u.Line)
	}
	return nil
}

type snapshotFile struct {
	content []byte
	mode    fs.FileMode
}

func snapshot(root string) (map[string]snapshotFile, error) {
	files := map[string]snapshotFile{}
	err := filepath.WalkDir(root, func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		name := entry.Name()
		if entry.IsDir() && (name == ".git" || name == "__pycache__") {
			return filepath.SkipDir
		}
		if !entry.Type().IsRegular() {
			return nil // A symbolic link, such as bazel-bin, is not part of the tree.
		}
		relative, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		content, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		files[filepath.ToSlash(relative)] = snapshotFile{content, info.Mode()}
		return nil
	})
	return files, err
}

func restore(root string, before map[string]snapshotFile) error {
	now, err := snapshot(root)
	if err != nil {
		return err
	}
	for path := range now {
		if _, kept := before[path]; !kept {
			if err := os.Remove(filepath.Join(root, path)); err != nil {
				return err
			}
		}
	}
	for path, file := range before {
		if current, found := now[path]; found && bytes.Equal(current.content, file.content) && current.mode == file.mode {
			continue
		}
		full := filepath.Join(root, path)
		if err := os.MkdirAll(filepath.Dir(full), 0o755); err != nil {
			return err
		}
		if err := os.WriteFile(full, file.content, file.mode.Perm()); err != nil {
			return err
		}
		if err := os.Chmod(full, file.mode.Perm()); err != nil {
			return err
		}
	}
	return nil
}

func difference(before, after map[string]snapshotFile) []fileChange {
	var changes []fileChange
	for path, file := range after {
		old, found := before[path]
		if found && bytes.Equal(old.content, file.content) && old.mode == file.mode {
			continue
		}
		mode := "100644"
		if file.mode.Perm()&0o111 != 0 {
			mode = "100755"
		}
		changes = append(changes, fileChange{Path: path, Mode: mode, Content: file.content})
	}
	for path := range before {
		if _, found := after[path]; !found {
			changes = append(changes, fileChange{Path: path, Mode: "100644", Deleted: true})
		}
	}
	slices.SortFunc(changes, func(a, b fileChange) int { return strings.Compare(a.Path, b.Path) })
	return changes
}
