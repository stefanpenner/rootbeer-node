package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
)

// An update is one proposed change: one runtime, one line, one version.
type update struct {
	Line, Old, New string
	NewLine        bool
	SHA256         string
	Source         string // The URL that the checksum describes. The pull request names it.
	Shasums        string // Node only: the checksum file, which add_node_version.py reads.
}

// A release is a version that upstream offers. resolve finds its checksum, and runs only for a real update.
type release struct {
	line, version string
	resolve       func(*update) error
}

type upstream struct {
	client *http.Client
	token  string
}

const metadataLimit = 64 << 20

var (
	sha256Pattern = regexp.MustCompile(`^[0-9a-f]{64}$`)
	tagPattern    = regexp.MustCompile(`^(?:[a-z-]*-)?v?([0-9]+\.[0-9]+\.[0-9]+)$`)
	sourcePattern = regexp.MustCompile(`(?:[_-]src|source).*\.tar\.(?:gz|xz)$`)
)

// check gives the updates for one runtime. An error for one line leaves the updates of the other lines.
func (u *upstream) check(r runtime) ([]update, error) {
	releases, err := u.releases(r)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", r.Name, err)
	}
	var updates []update
	var failures []error
	for _, found := range plan(r.Pins, releases) {
		if err := found.release.resolve(&found.update); err != nil {
			failures = append(failures, fmt.Errorf("%s %s: %w", r.Name, found.update.New, err))
			continue
		}
		updates = append(updates, found.update)
	}
	return updates, errors.Join(failures...)
}

type planned struct {
	update  update
	release release
}

// plan picks the newest release of each pinned line, then the newest release above the newest pin.
// A lower unpinned line stays out: a line that upstream replaced gets no pull request.
func plan(pins []pin, releases []release) []planned {
	newest := map[string]release{}
	for _, r := range releases {
		if current, ok := newest[r.line]; !ok || newerVersion(r.version, current.version) {
			newest[r.line] = r
		}
	}
	var result []planned
	top := -1
	for _, p := range pins {
		if major, err := strconv.Atoi(p.Line); err == nil && major > top {
			top = major
		}
		found, ok := newest[p.Line]
		if ok && newerVersion(found.version, p.Version) {
			result = append(result, planned{update{Line: p.Line, Old: p.Version, New: found.version}, found})
		}
	}
	var above *release
	for line, r := range newest {
		major, err := strconv.Atoi(line)
		if err != nil || major <= top {
			continue
		}
		if above == nil || newerVersion(r.version, above.version) {
			copied := r
			above = &copied
		}
	}
	if above != nil {
		result = append(result, planned{update{Line: above.line, New: above.version, NewLine: true}, *above})
	}
	return result
}

func (u *upstream) releases(r runtime) ([]release, error) {
	switch r.Kind {
	case kindNode:
		return u.nodeReleases()
	case kindGitHubRelease:
		return u.gitHubReleases(r.Repo)
	case kindPyPI:
		return u.pypiReleases(r)
	case kindAdoptium:
		return u.adoptiumReleases(r)
	}
	return nil, fmt.Errorf("unknown upstream kind %q", r.Kind)
}

func (u *upstream) nodeReleases() ([]release, error) {
	var index []struct {
		Version string `json:"version"`
	}
	if err := u.getJSON("https://nodejs.org/dist/index.json", &index); err != nil {
		return nil, err
	}
	var releases []release
	for _, entry := range index {
		version, found := strings.CutPrefix(entry.Version, "v")
		if !found || !validVersion(version) {
			continue
		}
		line, _, _ := strings.Cut(version, ".")
		releases = append(releases, release{line, version, u.resolveNode(version)})
	}
	return releases, nil
}

func (u *upstream) resolveNode(version string) func(*update) error {
	return func(out *update) error {
		base := "https://nodejs.org/dist/v" + version + "/"
		text, err := u.getText(base + "SHASUMS256.txt")
		if err != nil {
			return err
		}
		tarball := "node-v" + version + ".tar.gz"
		for _, row := range strings.Split(text, "\n") {
			sum, name, _ := strings.Cut(row, "  ")
			if name == tarball && sha256Pattern.MatchString(sum) {
				out.SHA256, out.Source, out.Shasums = sum, base+tarball, text
				return nil
			}
		}
		return fmt.Errorf("SHASUMS256.txt has no valid checksum for %s", tarball)
	}
}

func (u *upstream) gitHubReleases(repo string) ([]release, error) {
	var listed []struct {
		Tag        string `json:"tag_name"`
		Draft      bool   `json:"draft"`
		Prerelease bool   `json:"prerelease"`
		Assets     []gitHubAsset
	}
	if err := u.getJSON("https://api.github.com/repos/"+repo+"/releases?per_page=100", &listed); err != nil {
		return nil, err
	}
	var releases []release
	for _, entry := range listed {
		match := tagPattern.FindStringSubmatch(entry.Tag)
		if entry.Draft || entry.Prerelease || match == nil || !validVersion(match[1]) {
			continue
		}
		line, _, _ := strings.Cut(match[1], ".")
		releases = append(releases, release{line, match[1], u.resolveGitHub(repo, entry.Tag, entry.Assets)})
	}
	return releases, nil
}

type gitHubAsset struct {
	Name   string `json:"name"`
	URL    string `json:"browser_download_url"`
	Digest string `json:"digest"`
}

// resolveGitHub prefers a source asset and the digest that GitHub records for it.
// With no source asset, it hashes the archive of the tag, because the assets hold only binaries.
func (u *upstream) resolveGitHub(repo, tag string, assets []gitHubAsset) func(*update) error {
	return func(out *update) error {
		for _, asset := range assets {
			if !sourcePattern.MatchString(asset.Name) {
				continue
			}
			if !strings.HasPrefix(asset.URL, "https://") {
				return fmt.Errorf("asset URL %q is not https", asset.URL)
			}
			out.Source = asset.URL
			if sum, found := strings.CutPrefix(asset.Digest, "sha256:"); found {
				return setChecksum(out, sum)
			}
			return u.hashSource(out)
		}
		out.Source = "https://github.com/" + repo + "/archive/refs/tags/" + url.PathEscape(tag) + ".tar.gz"
		return u.hashSource(out)
	}
}

func (u *upstream) pypiReleases(r runtime) ([]release, error) {
	var project struct {
		Info struct {
			Version string `json:"version"`
			Yanked  bool   `json:"yanked"`
		} `json:"info"`
		URLs []struct {
			PackageType string `json:"packagetype"`
			URL         string `json:"url"`
			Digests     struct {
				SHA256 string `json:"sha256"`
			} `json:"digests"`
		} `json:"urls"`
	}
	if err := u.getJSON("https://pypi.org/pypi/"+r.Repo+"/json", &project); err != nil {
		return nil, err
	}
	if project.Info.Yanked || !validVersion(project.Info.Version) {
		return nil, nil
	}
	var releases []release
	for _, p := range r.Pins {
		releases = append(releases, release{p.Line, project.Info.Version, func(out *update) error {
			for _, file := range project.URLs {
				if file.PackageType == "sdist" {
					if !strings.HasPrefix(file.URL, "https://") {
						return fmt.Errorf("sdist URL %q is not https", file.URL)
					}
					out.Source = file.URL
					return setChecksum(out, file.Digests.SHA256)
				}
			}
			return fmt.Errorf("the release has no sdist")
		}})
	}
	return releases, nil
}

func (u *upstream) adoptiumReleases(r runtime) ([]release, error) {
	var available struct {
		LTS []int `json:"available_lts_releases"`
	}
	if err := u.getJSON("https://api.adoptium.net/v3/info/available_releases", &available); err != nil {
		return nil, err
	}
	lines := map[string]bool{}
	for _, p := range r.Pins {
		lines[p.Line] = true
	}
	top := 0
	for _, lts := range available.LTS {
		top = max(top, lts)
	}
	lines[strconv.Itoa(top)] = true

	var releases []release
	for line := range lines {
		found, err := u.adoptiumRelease(line)
		if err != nil {
			return nil, err
		}
		if found != nil {
			releases = append(releases, *found)
		}
	}
	return releases, nil
}

func (u *upstream) adoptiumRelease(line string) (*release, error) {
	query := url.Values{"image_type": {"sources"}, "vendor": {"eclipse"}, "page_size": {"1"}, "sort_order": {"DESC"}}
	var assets []struct {
		ReleaseName string `json:"release_name"`
		Binaries    []struct {
			ImageType string `json:"image_type"`
			Package   struct {
				Link     string `json:"link"`
				Checksum string `json:"checksum"`
			} `json:"package"`
		} `json:"binaries"`
	}
	address := "https://api.adoptium.net/v3/assets/feature_releases/" + url.PathEscape(line) + "/ga?" + query.Encode()
	if err := u.getJSON(address, &assets); err != nil {
		return nil, err
	}
	if len(assets) == 0 {
		return nil, nil
	}
	version, found := strings.CutPrefix(assets[0].ReleaseName, "jdk-")
	if !found || !validVersion(version) {
		return nil, nil
	}
	binaries := assets[0].Binaries
	return &release{line, version, func(out *update) error {
		for _, binary := range binaries {
			if binary.ImageType == "sources" && strings.HasPrefix(binary.Package.Link, "https://") {
				out.Source = binary.Package.Link
				return setChecksum(out, binary.Package.Checksum)
			}
		}
		return fmt.Errorf("the release has no https source package")
	}}, nil
}

func setChecksum(out *update, sum string) error {
	if !sha256Pattern.MatchString(sum) {
		return fmt.Errorf("upstream checksum %q is not sha256", sum)
	}
	out.SHA256 = sum
	return nil
}

// hashSource downloads out.Source and hashes the stream. It keeps no bytes.
func (u *upstream) hashSource(out *update) error {
	body, err := u.open(out.Source)
	if err != nil {
		return err
	}
	defer body.Close()
	digest := sha256.New()
	if _, err := io.Copy(digest, body); err != nil {
		return err
	}
	out.SHA256 = hex.EncodeToString(digest.Sum(nil))
	return nil
}

func (u *upstream) getJSON(address string, into any) error {
	text, err := u.getText(address)
	if err != nil {
		return err
	}
	return json.Unmarshal([]byte(text), into)
}

func (u *upstream) getText(address string) (string, error) {
	body, err := u.open(address)
	if err != nil {
		return "", err
	}
	defer body.Close()
	text, err := io.ReadAll(io.LimitReader(body, metadataLimit))
	return string(text), err
}

func (u *upstream) open(address string) (io.ReadCloser, error) {
	request, err := http.NewRequest(http.MethodGet, address, nil)
	if err != nil {
		return nil, err
	}
	// The token only raises the rate limit. net/http drops this header on a redirect to another host.
	if u.token != "" && request.URL.Host == "api.github.com" {
		request.Header.Set("Authorization", "Bearer "+u.token)
	}
	response, err := u.client.Do(request)
	if err != nil {
		return nil, err
	}
	if response.StatusCode != http.StatusOK {
		response.Body.Close()
		return nil, fmt.Errorf("GET %s: status %d", address, response.StatusCode)
	}
	return response.Body, nil
}
