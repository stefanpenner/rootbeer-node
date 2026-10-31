package main

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// fakeTransport serves recorded responses and records each request. It opens no socket.
type fakeTransport struct {
	responses map[string]fakeResponse
	requests  []recorded
}

type fakeResponse struct {
	status int
	body   string
}

type recorded struct {
	method, url, auth, body string
}

func (f *fakeTransport) RoundTrip(r *http.Request) (*http.Response, error) {
	body := ""
	if r.Body != nil {
		text, _ := io.ReadAll(r.Body)
		body = string(text)
	}
	f.requests = append(f.requests, recorded{r.Method, r.URL.String(), r.Header.Get("Authorization"), body})
	found, ok := f.responses[r.Method+" "+r.URL.String()]
	if !ok {
		return nil, errors.New("no recorded response for " + r.Method + " " + r.URL.String())
	}
	return &http.Response{
		StatusCode: found.status,
		Body:       io.NopCloser(strings.NewReader(found.body)),
		Header:     http.Header{},
		Request:    r,
	}, nil
}

func fixture(t *testing.T, name string) string {
	t.Helper()
	text, err := os.ReadFile(filepath.Join("testdata", name))
	if err != nil {
		t.Fatal(err)
	}
	return string(text)
}

func newUpstream(responses map[string]string) *upstream {
	transport := &fakeTransport{responses: map[string]fakeResponse{}}
	for key, body := range responses {
		transport.responses["GET "+key] = fakeResponse{200, body}
	}
	return &upstream{client: &http.Client{Transport: transport}}
}

func nodeRuntime(pins ...pin) runtime {
	return runtime{Name: "node", Kind: kindNode, File: "MODULE.bazel", Pins: pins}
}

func TestCheckNode(t *testing.T) {
	const index = "https://nodejs.org/dist/index.json"
	const shasums = "https://nodejs.org/dist/v26.13.0/SHASUMS256.txt"
	u := newUpstream(map[string]string{index: fixture(t, "node_index.json"), shasums: fixture(t, "node_shasums.txt")})

	tests := []struct {
		name string
		pins []pin
		want []update
	}{
		{
			name: "a new release of a pinned line",
			pins: []pin{{Line: "26", Version: "26.12.1"}},
			want: []update{{Line: "26", Old: "26.12.1", New: "26.13.0",
				SHA256: "986ead18ef18256831bae3e57d94aef680a7b84cfd4044f3e8471f833fbd7191",
				Source: "https://nodejs.org/dist/v26.13.0/node-v26.13.0.tar.gz"}},
		},
		{
			name: "no update when the pin is current, and the alpha of 27 is no new line",
			pins: []pin{{Line: "26", Version: "26.13.0"}},
			want: nil,
		},
		{
			name: "no downgrade",
			pins: []pin{{Line: "26", Version: "26.14.0"}},
			want: nil,
		},
		{
			name: "a major above the newest pin is a new line, and 25 under it is not",
			pins: []pin{{Line: "24", Version: "24.22.2"}, {Line: "22", Version: "22.23.4"}},
			want: []update{{Line: "26", New: "26.13.0", NewLine: true,
				SHA256: "986ead18ef18256831bae3e57d94aef680a7b84cfd4044f3e8471f833fbd7191",
				Source: "https://nodejs.org/dist/v26.13.0/node-v26.13.0.tar.gz"}},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := u.check(nodeRuntime(tt.pins...))
			if err != nil {
				t.Fatal(err)
			}
			assertUpdates(t, got, tt.want)
		})
	}
}

// assertUpdates compares the fields that a test states. The checksum text stays out.
func assertUpdates(t *testing.T, got, want []update) {
	t.Helper()
	if len(got) != len(want) {
		t.Fatalf("got %d updates %+v, want %d", len(got), got, len(want))
	}
	for i := range got {
		got[i].Shasums = ""
		if got[i] != want[i] {
			t.Errorf("update %d:\n got %+v\nwant %+v", i, got[i], want[i])
		}
	}
}

func TestCheckNodeRefusesABadChecksumFile(t *testing.T) {
	const index = `[{"version":"v26.13.0"}]`
	tests := []struct{ name, shasums string }{
		{"no line for the tarball", "abc  node-v26.13.0-linux-x64.tar.gz\n"},
		{"not hex", strings.Repeat("z", 64) + "  node-v26.13.0.tar.gz\n"},
		{"short", "abc  node-v26.13.0.tar.gz\n"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			u := newUpstream(map[string]string{
				"https://nodejs.org/dist/index.json":              index,
				"https://nodejs.org/dist/v26.13.0/SHASUMS256.txt": tt.shasums,
			})
			if _, err := u.check(nodeRuntime(pin{Line: "26", Version: "26.12.0"})); err == nil {
				t.Fatal("want an error")
			}
		})
	}
}

func TestCheckNodeSkipsHostileVersions(t *testing.T) {
	const index = `[{"version":"v26.99.0; rm -rf /"},{"version":"../../x"},{"version":"v99.0.0-rc.1"},{"version":"nope"}]`
	u := newUpstream(map[string]string{"https://nodejs.org/dist/index.json": index})
	got, err := u.check(nodeRuntime(pin{Line: "26", Version: "26.12.0"}))
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 0 {
		t.Fatalf("updates = %+v", got)
	}
}

func TestCheckGitHubReleaseUsesTheAssetDigest(t *testing.T) {
	u := newUpstream(map[string]string{
		"https://api.github.com/repos/denoland/deno/releases?per_page=100": fixture(t, "gh_deno.json"),
	})
	deno := runtime{Name: "deno", Kind: kindGitHubRelease, Repo: "denoland/deno", Pins: []pin{{Line: "2", Version: "2.9.7"}}}
	got, err := u.check(deno)
	if err != nil {
		t.Fatal(err)
	}
	assertUpdates(t, got, []update{{Line: "2", Old: "2.9.7", New: "2.9.8",
		SHA256: "b57d0281c1647effc735f242ba52bc409747fc6ed6ad4946e76f062c67e113eb",
		Source: "https://github.com/denoland/deno/releases/download/v2.9.8/deno_src.tar.gz"}})
}

func TestCheckGitHubReleaseHashesTheTagArchive(t *testing.T) {
	// Bun publishes no source asset. Its SHASUMS256.txt lists binaries only.
	const archive = "https://github.com/oven-sh/bun/archive/refs/tags/bun-v1.4.4.tar.gz"
	u := newUpstream(map[string]string{
		"https://api.github.com/repos/oven-sh/bun/releases?per_page=100": fixture(t, "gh_bun.json"),
		archive: "recorded archive bytes",
	})
	sum := sha256.Sum256([]byte("recorded archive bytes"))
	bun := runtime{Name: "bun", Kind: kindGitHubRelease, Repo: "oven-sh/bun", Pins: []pin{{Line: "1", Version: "1.4.3"}}}
	got, err := u.check(bun)
	if err != nil {
		t.Fatal(err)
	}
	assertUpdates(t, got, []update{{Line: "1", Old: "1.4.3", New: "1.4.4", SHA256: hex.EncodeToString(sum[:]), Source: archive}})
}

func TestCheckGitHubReleaseFilters(t *testing.T) {
	const releases = `[
	  {"tag_name":"v3.0.0","draft":true,"assets":[]},
	  {"tag_name":"v3.0.1","prerelease":true,"assets":[]},
	  {"tag_name":"v2.9.9-rc1","assets":[]},
	  {"tag_name":"$(id)","assets":[]},
	  {"tag_name":"v2.9.7","assets":[]}
	]`
	u := newUpstream(map[string]string{"https://api.github.com/repos/a/b/releases?per_page=100": releases})
	got, err := u.check(runtime{Name: "b", Kind: kindGitHubRelease, Repo: "a/b", Pins: []pin{{Line: "2", Version: "2.9.7"}}})
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 0 {
		t.Fatalf("updates = %+v", got)
	}
}

func TestCheckGitHubReleaseFindsANewMajor(t *testing.T) {
	const releases = `[{"tag_name":"v3.0.0","assets":[{"name":"deno_src.tar.gz",
	  "browser_download_url":"https://github.com/a/b/releases/download/v3.0.0/deno_src.tar.gz",
	  "digest":"sha256:` + "b57d0281c1647effc735f242ba52bc409747fc6ed6ad4946e76f062c67e113eb" + `"}]},
	  {"tag_name":"v2.9.7","assets":[]}]`
	u := newUpstream(map[string]string{"https://api.github.com/repos/a/b/releases?per_page=100": releases})
	got, err := u.check(runtime{Name: "b", Kind: kindGitHubRelease, Repo: "a/b", Pins: []pin{{Line: "2", Version: "2.9.7"}}})
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 || !got[0].NewLine || got[0].Line != "3" || got[0].New != "3.0.0" {
		t.Fatalf("updates = %+v", got)
	}
}

func TestCheckPyPI(t *testing.T) {
	const project = "https://pypi.org/pypi/certifi/json"
	u := newUpstream(map[string]string{project: fixture(t, "pypi_certifi.json")})
	certifi := runtime{Name: "certifi", Kind: kindPyPI, Repo: "certifi", Pins: []pin{{Line: "latest", Version: "2026.9.1"}}}
	got, err := u.check(certifi)
	if err != nil {
		t.Fatal(err)
	}
	assertUpdates(t, got, []update{{Line: "latest", Old: "2026.9.1", New: "2026.10.23",
		SHA256: "a9895e6e2758b371e0545e321a3a8fd1fcfd9829ada8824a936dfb16aaaf36cd",
		Source: "https://files.pythonhosted.org/packages/fd/11/b524cbd9bbdaca58608e4cf4053fd463417549e1959fa8d3aa18319f9555/certifi-2026.10.23.tar.gz"}})
}

func TestCheckPyPISkipsAYankedRelease(t *testing.T) {
	const yanked = `{"info":{"version":"2026.10.23","yanked":true},"urls":[]}`
	u := newUpstream(map[string]string{"https://pypi.org/pypi/certifi/json": yanked})
	got, err := u.check(runtime{Name: "certifi", Kind: kindPyPI, Repo: "certifi", Pins: []pin{{Line: "latest", Version: "2026.9.1"}}})
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 0 {
		t.Fatalf("updates = %+v", got)
	}
}

func adoptiumURL(line string) string {
	return "https://api.adoptium.net/v3/assets/feature_releases/" + line + "/ga?image_type=sources&page_size=1&sort_order=DESC&vendor=eclipse"
}

func TestCheckAdoptium(t *testing.T) {
	u := newUpstream(map[string]string{
		"https://api.adoptium.net/v3/info/available_releases": `{"available_lts_releases":[8,11,17,21]}`,
		adoptiumURL("21"): fixture(t, "adoptium_21.json"),
	})
	jdk := runtime{Name: "jdk", Kind: kindAdoptium, Pins: []pin{{Line: "21", Version: "21.0.12.1+1"}}}
	got, err := u.check(jdk)
	if err != nil {
		t.Fatal(err)
	}
	assertUpdates(t, got, []update{{Line: "21", Old: "21.0.12.1+1", New: "21.0.13+9",
		SHA256: "b5232c9980d8a0f0459676c084c41c6e2c771ed9e785890b03c6a438406ad1ca",
		Source: "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.13%2B9/OpenJDK21U-jdk-sources_21.0.13_9.tar.gz"}})
}

func TestCheckAdoptiumFindsANewLTSFromTheRecordedList(t *testing.T) {
	// The recorded list has LTS 25. The pin is on 21. 22 and 23 are not LTS, so no request asks for them.
	const lts25 = `[{"release_name":"jdk-25.0.3+9","binaries":[{"image_type":"sources","package":{
	  "link":"https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.3%2B9/src.tar.gz",
	  "checksum":"b5232c9980d8a0f0459676c084c41c6e2c771ed9e785890b03c6a438406ad1ca"}}]}]`
	u := newUpstream(map[string]string{
		"https://api.adoptium.net/v3/info/available_releases": fixture(t, "adoptium_releases.json"),
		adoptiumURL("21"): fixture(t, "adoptium_21.json"),
		adoptiumURL("25"): lts25,
	})
	jdk := runtime{Name: "jdk", Kind: kindAdoptium, Pins: []pin{{Line: "21", Version: "21.0.13+9"}}}
	got, err := u.check(jdk)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 || !got[0].NewLine || got[0].Line != "25" || got[0].New != "25.0.3+9" {
		t.Fatalf("updates = %+v", got)
	}
}

func TestSourceURLMustBeHTTPS(t *testing.T) {
	const releases = `[{"tag_name":"v2.9.8","assets":[{"name":"deno_src.tar.gz",
	  "browser_download_url":"http://evil.example/deno_src.tar.gz",
	  "digest":"sha256:b57d0281c1647effc735f242ba52bc409747fc6ed6ad4946e76f062c67e113eb"}]}]`
	u := newUpstream(map[string]string{"https://api.github.com/repos/a/b/releases?per_page=100": releases})
	_, err := u.check(runtime{Name: "b", Kind: kindGitHubRelease, Repo: "a/b", Pins: []pin{{Line: "2", Version: "2.9.7"}}})
	if err == nil || !strings.Contains(err.Error(), "https") {
		t.Fatalf("err = %v", err)
	}
}
