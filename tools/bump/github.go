package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
)

const (
	baseBranch  = "main"
	flagPrefix  = "[human work] "
	settingName = "Allow GitHub Actions to create and approve pull requests"
)

type gitHub struct {
	client      *http.Client
	repo, token string
}

// A proposal is one pull request: one branch, one commit on BaseSHA.
type proposal struct {
	Branch, Title, Body, BaseSHA string
	Changes                      []fileChange
	Flags                        []string
}

type branchState int

const (
	stateNew       branchState = iota // Make the commit, the branch, and the pull request.
	stateHasBranch                    // An earlier run made the branch but not the pull request. Open it only.
	stateHasPull                      // Do nothing. A closed pull request stays closed.
)

type statusError struct {
	status  int
	message string
}

func (e *statusError) Error() string {
	return fmt.Sprintf("status %d: %s", e.status, e.message)
}

func hasStatus(err error, status int) bool {
	var failure *statusError
	return errors.As(err, &failure) && failure.status == status
}

// state reads the pull requests first. Any unknown answer is an error, not a second pull request.
func (g *gitHub) state(branch string) (branchState, error) {
	owner, _, _ := strings.Cut(g.repo, "/")
	query := url.Values{"head": {owner + ":" + branch}, "state": {"all"}, "per_page": {"1"}}
	var pulls []struct{}
	if err := g.call(http.MethodGet, "/pulls?"+query.Encode(), nil, &pulls); err != nil {
		return stateNew, err
	}
	if len(pulls) > 0 {
		return stateHasPull, nil
	}
	err := g.call(http.MethodGet, "/git/ref/heads/"+branch, nil, nil)
	if err == nil {
		return stateHasBranch, nil
	}
	if hasStatus(err, http.StatusNotFound) {
		return stateNew, nil
	}
	return stateNew, err
}

// create sends no author, committer, or signature. GitHub signs a commit only in that case.
func (g *gitHub) create(p proposal) (string, error) {
	var base struct {
		Tree struct {
			SHA string `json:"sha"`
		} `json:"tree"`
	}
	if err := g.call(http.MethodGet, "/git/commits/"+p.BaseSHA, nil, &base); err != nil {
		return "", err
	}
	entries, err := g.treeEntries(p.Changes)
	if err != nil {
		return "", err
	}
	var tree struct {
		SHA string `json:"sha"`
	}
	treeRequest := map[string]any{"base_tree": base.Tree.SHA, "tree": entries}
	if err := g.call(http.MethodPost, "/git/trees", treeRequest, &tree); err != nil {
		return "", err
	}
	var commit struct {
		SHA          string `json:"sha"`
		Verification struct {
			Verified bool   `json:"verified"`
			Reason   string `json:"reason"`
		} `json:"verification"`
	}
	commitRequest := map[string]any{"message": p.Title, "tree": tree.SHA, "parents": []string{p.BaseSHA}}
	if err := g.call(http.MethodPost, "/git/commits", commitRequest, &commit); err != nil {
		return "", err
	}
	if !commit.Verification.Verified {
		return "", fmt.Errorf("GitHub did not sign commit %s (%s). The branch was not made", commit.SHA, commit.Verification.Reason)
	}
	ref := map[string]any{"ref": "refs/heads/" + p.Branch, "sha": commit.SHA}
	if err := g.call(http.MethodPost, "/git/refs", ref, nil); err != nil && !hasStatus(err, http.StatusUnprocessableEntity) {
		return "", err
	}
	return g.openPull(p)
}

type treeEntry struct {
	Path string  `json:"path"`
	Mode string  `json:"mode"`
	Type string  `json:"type"`
	SHA  *string `json:"sha"` // null deletes the path.
}

func (g *gitHub) treeEntries(changes []fileChange) ([]treeEntry, error) {
	var entries []treeEntry
	for _, change := range changes {
		entry := treeEntry{Path: change.Path, Mode: change.Mode, Type: "blob"}
		if !change.Deleted {
			var blob struct {
				SHA string `json:"sha"`
			}
			request := map[string]any{"content": base64.StdEncoding.EncodeToString(change.Content), "encoding": "base64"}
			if err := g.call(http.MethodPost, "/git/blobs", request, &blob); err != nil {
				return nil, err
			}
			entry.SHA = &blob.SHA
		}
		entries = append(entries, entry)
	}
	return entries, nil
}

// openPull makes a draft for a flagged proposal, so a flag cannot pass unseen.
func (g *gitHub) openPull(p proposal) (string, error) {
	title, body := p.Title, p.Body
	if len(p.Flags) > 0 {
		title = flagPrefix + title
		body = "## Human work\n\n- " + strings.Join(p.Flags, "\n- ") + "\n\n" + body
	}
	var pull struct {
		URL string `json:"html_url"`
	}
	request := map[string]any{"title": title, "head": p.Branch, "base": baseBranch, "body": body, "draft": len(p.Flags) > 0}
	err := g.call(http.MethodPost, "/pulls", request, &pull)
	if hasStatus(err, http.StatusForbidden) {
		return "", fmt.Errorf("GitHub refused the pull request. A repository admin must turn on %q: %w", settingName, err)
	}
	return pull.URL, err
}

func (g *gitHub) call(method, path string, request, response any) error {
	var body io.Reader
	if request != nil {
		text, err := json.Marshal(request)
		if err != nil {
			return err
		}
		body = bytes.NewReader(text)
	}
	r, err := http.NewRequest(method, "https://api.github.com/repos/"+g.repo+path, body)
	if err != nil {
		return err
	}
	r.Header.Set("Authorization", "Bearer "+g.token)
	r.Header.Set("Accept", "application/vnd.github+json")
	r.Header.Set("X-GitHub-Api-Version", "2022-11-28")
	answer, err := g.client.Do(r)
	if err != nil {
		return err
	}
	defer answer.Body.Close()
	text, err := io.ReadAll(io.LimitReader(answer.Body, metadataLimit))
	if err != nil {
		return err
	}
	if answer.StatusCode < 200 || answer.StatusCode > 299 {
		return &statusError{answer.StatusCode, method + " " + path + ": " + string(text)}
	}
	if response == nil {
		return nil
	}
	return json.Unmarshal(text, response)
}
