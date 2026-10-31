// Command bump finds new upstream releases and opens one pull request for each.
// It writes only through the GitHub API, so GitHub signs each commit.
package main

import (
	"errors"
	"flag"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"regexp"
	"time"
)

type bumper struct {
	root, baseSHA string
	dryRun        bool
	run           command
	upstream      *upstream
	github        *gitHub
}

func main() {
	root := flag.String("root", os.Getenv("BUILD_WORKSPACE_DIRECTORY"), "repository root")
	repo := flag.String("repo", "", "owner/name of the repository")
	baseSHA := flag.String("base-sha", "", "the commit of the checkout, which is the parent of each new commit")
	dryRun := flag.Bool("dry-run", false, "print the updates, and write nothing")
	flag.Parse()

	token := os.Getenv("GITHUB_TOKEN")
	if !*dryRun && (token == "" || !repoPattern.MatchString(*repo) || !commitPattern.MatchString(*baseSHA)) {
		fatal(errors.New("a real run needs GITHUB_TOKEN, --repo, and a full --base-sha"))
	}
	client := &http.Client{Timeout: 15 * time.Minute}
	b := &bumper{
		root:     *root,
		baseSHA:  *baseSHA,
		dryRun:   *dryRun,
		run:      runCommand,
		upstream: &upstream{client: client, token: token},
		github:   &gitHub{client: client, repo: *repo, token: token},
	}
	if err := b.runAll(); err != nil {
		fatal(err)
	}
}

var commitPattern = regexp.MustCompile(`^[0-9a-f]{40}$`)

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "bump:", err)
	os.Exit(1)
}

func runCommand(dir string, args ...string) error {
	command := exec.Command(args[0], args[1:]...)
	command.Dir = dir
	command.Stdout, command.Stderr = os.Stdout, os.Stderr
	return command.Run()
}

// runAll visits each runtime. One failure stops nothing, and the run still ends with an error.
func (b *bumper) runAll() error {
	runtimes, err := readRuntimes(b.root)
	if err != nil {
		return err
	}
	var failures []error
	for _, r := range runtimes {
		updates, err := b.upstream.check(r)
		if err != nil {
			fmt.Println("failed:", err)
			failures = append(failures, err)
		}
		for _, u := range updates {
			if err := b.propose(r, u); err != nil {
				err = fmt.Errorf("%s: %w", branchName(r.Name, u.Line, u.New), err)
				fmt.Println("failed:", err)
				failures = append(failures, err)
			}
		}
	}
	return errors.Join(failures...)
}

func (b *bumper) propose(r runtime, u update) error {
	branch := branchName(r.Name, u.Line, u.New)
	if b.dryRun {
		fmt.Printf("update: %s %s (%s)\n", branch, u.SHA256, u.Source)
		return nil
	}
	state, err := b.github.state(branch)
	if err != nil {
		return err
	}
	if state == stateHasPull {
		fmt.Println("skip, a pull request exists:", branch)
		return nil
	}
	result, err := apply(b.root, b.run, r, u)
	if err != nil {
		return err
	}
	p := proposal{
		Branch:  branch,
		Title:   title(r, u),
		Body:    body(r, u),
		BaseSHA: b.baseSHA,
		Changes: result.Changes,
		Flags:   result.Flags,
	}
	open := b.github.create
	if state == stateHasBranch {
		open = b.github.openPull
	}
	address, err := open(p)
	if err != nil {
		return err
	}
	fmt.Println("opened:", address)
	return nil
}

func title(r runtime, u update) string {
	if u.NewLine {
		return fmt.Sprintf("%s %s: add the new line at %s", r.Name, u.Line, u.New)
	}
	return fmt.Sprintf("%s %s: %s to %s", r.Name, u.Line, u.Old, u.New)
}

func body(r runtime, u update) string {
	return fmt.Sprintf(`The daily version check found a new upstream release.

- Runtime: %s
- Line: %s
- Version: %s
- sha256: %s
- Source: %s

CI has not run this version. A person with write access must select "Approve workflows to run". The pr-approval environment then asks for its own approval.
`, r.Name, u.Line, u.New, u.SHA256, u.Source)
}
