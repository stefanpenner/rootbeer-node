package main

import "testing"

func TestNewerVersion(t *testing.T) {
	tests := []struct {
		name, a, b string
		want       bool
	}{
		{"patch", "26.13.1", "26.13.0", true},
		{"equal", "26.13.0", "26.13.0", false},
		{"older", "26.12.1", "26.13.0", false},
		{"numeric not text", "22.10.0", "22.9.0", true},
		{"jdk build", "21.0.13+10", "21.0.13+9", true},
		{"jdk hotfix beats lower build", "21.0.12.1+1", "21.0.12+9", true},
		{"jdk next update beats hotfix", "21.0.13+9", "21.0.12.1+1", true},
		{"calver", "2026.10.23", "2026.9.30", true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := newerVersion(tt.a, tt.b); got != tt.want {
				t.Errorf("newerVersion(%q, %q) = %v, want %v", tt.a, tt.b, got, tt.want)
			}
		})
	}
}

func TestValidVersionRefusesHostileText(t *testing.T) {
	tests := []struct {
		in   string
		want bool
	}{
		{"26.13.0", true},
		{"21.0.13+9", true},
		{"2026.10.23", true},
		{"", false},
		{"27.0.0-alpha.0.0.0", false},
		{"1.2.3\n", false},
		{"1.2.3; rm -rf /", false},
		{"../../etc/passwd", false},
		{"1.2.3$(id)", false},
		{"1..2", false},
		{"99999999999999999999.1.1", false},
	}
	for _, tt := range tests {
		if got := validVersion(tt.in); got != tt.want {
			t.Errorf("validVersion(%q) = %v, want %v", tt.in, got, tt.want)
		}
	}
}

func TestBranchName(t *testing.T) {
	tests := []struct {
		runtime, line, version, want string
	}{
		{"node", "26", "26.13.1", "bump/node-26-26.13.1"},
		{"jdk", "21", "21.0.13+9", "bump/jdk-21-21.0.13_9"},
		{"certifi", "latest", "2026.10.23", "bump/certifi-latest-2026.10.23"},
	}
	for _, tt := range tests {
		if got := branchName(tt.runtime, tt.line, tt.version); got != tt.want {
			t.Errorf("branchName(%q, %q, %q) = %q, want %q", tt.runtime, tt.line, tt.version, got, tt.want)
		}
	}
}
