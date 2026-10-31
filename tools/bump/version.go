package main

import (
	"regexp"
	"strconv"
	"strings"
)

// A version is dotted numbers with an optional +build, as in 21.0.13+9.
// Upstream text must match this before it reaches a branch name, a file, or a pull request.
// A prerelease does not match, so the tool never proposes one.
var versionPattern = regexp.MustCompile(`^[0-9]{1,9}(\.[0-9]{1,9})*(\+[0-9]{1,9})?$`)

func validVersion(version string) bool {
	return versionPattern.MatchString(version)
}

// newerVersion reports a > b. The dotted part decides first, then the build.
// So the JDK hotfix 21.0.12.1+1 is newer than 21.0.12+9.
func newerVersion(a, b string) bool {
	aDots, aBuild, _ := strings.Cut(a, "+")
	bDots, bBuild, _ := strings.Cut(b, "+")
	if order := compareDotted(aDots, bDots); order != 0 {
		return order > 0
	}
	return compareDotted(aBuild, bBuild) > 0
}

func compareDotted(a, b string) int {
	aParts, bParts := strings.Split(a, "."), strings.Split(b, ".")
	for i := 0; i < len(aParts) || i < len(bParts); i++ {
		if order := partAt(aParts, i) - partAt(bParts, i); order != 0 {
			return order
		}
	}
	return 0
}

func partAt(parts []string, i int) int {
	if i >= len(parts) {
		return 0
	}
	value, _ := strconv.Atoi(parts[i])
	return value
}

// branchName gives one name for one update, so a second run finds the first.
func branchName(runtime, line, version string) string {
	return "bump/" + runtime + "-" + line + "-" + strings.ReplaceAll(version, "+", "_")
}
