#!/usr/bin/env bash
# Pre-requisite check / installer for tracefinity-local-with-mcp (macOS + Linux).
#
#   scripts/preflight.sh          check; if run in a terminal and something is
#                                 missing, offer to install everything for you
#   scripts/preflight.sh --fix    go straight to installing missing items (asks each)
#   scripts/preflight.sh --fix -y install without any prompts (scripts / agents)
#   scripts/preflight.sh --check  only report, never install
#
# Exit 0 when every REQUIRED tool is usable, 1 otherwise.
set -uo pipefail

FIX=0 ; YES=0 ; NOFIX=0
for a in "$@"; do case "$a" in
  --fix) FIX=1 ;;
  -y|--yes) YES=1 ;;
  --check|--no-fix) NOFIX=1 ;;
  -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//' ; exit 0 ;;
  *) echo "unknown option: $a" >&2 ; exit 2 ;;
esac ; done

export PATH="$HOME/.docker/bin:$HOME/.local/bin:$PATH"
case "$(uname -s)" in Darwin) OS=macos ;; Linux) OS=linux ;; *) OS=other ;; esac

# package manager (linuxbrew counts; brew is preferred where present)
PKG=none
for p in brew apt-get dnf pacman zypper; do command -v "$p" >/dev/null 2>&1 && { PKG=$p; break; }; done

REQUIRED_MISSING=0

is_tty() { [ -t 0 ] && [ -t 1 ]; }
have()   { command -v "$1" >/dev/null 2>&1; }
ok()     { printf '  \033[32m ok \033[0m %-14s %s\n' "$1" "${2:-}"; }
miss()   { printf '  \033[31mMISS\033[0m %-14s %s\n' "$1" "${2:-}"; }
warn()   { printf '  \033[33mwarn\033[0m %-14s %s\n' "$1" "${2:-}"; }
skip()   { printf '  \033[90m --  \033[0m %-14s %s\n' "$1" "${2:-}"; }
say()    { printf '       %s\n' "$*"; }
sudo_()  { [ "$(id -u)" = 0 ] && printf '' || printf 'sudo '; }
run()    { echo "       + $*"; eval "$*"; }

# download / doc pages, referenced in the README too
URL_BREW='https://brew.sh'
URL_DOCKER_MAC='https://www.docker.com/products/docker-desktop/'
URL_DOCKER_LINUX='https://docs.docker.com/engine/install/'
URL_COMPOSE='https://docs.docker.com/compose/install/linux/'
URL_UV='https://docs.astral.sh/uv/getting-started/installation/'
URL_GIT='https://git-scm.com/downloads'
URL_GH='https://cli.github.com'
URL_JQ='https://jqlang.github.io/jq/download/'
BREW_INSTALL='/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'

confirm() {  # per-item yes/no; honours --fix / -y / --check / no-tty
  [ "$NOFIX" = 1 ] && return 1
  [ "$FIX" = 1 ]   || return 1
  [ "$YES" = 1 ]   && return 0
  is_tty || return 1
  printf '       install now? [y/N] '
  read -r r </dev/tty 2>/dev/null || return 1
  case "$r" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

brew_env() {
  for b in /opt/homebrew/bin/brew /usr/local/bin/brew /home/linuxbrew/.linuxbrew/bin/brew; do
    [ -x "$b" ] && eval "$("$b" shellenv)" 2>/dev/null
  done
  return 0
}

pkg_cmd() {  # $1 = package name -> install command for the detected manager
  case "$PKG" in
    brew)    echo "brew install $1" ;;
    apt-get) echo "$(sudo_)apt-get update && $(sudo_)apt-get install -y $1" ;;
    dnf)     echo "$(sudo_)dnf install -y $1" ;;
    pacman)  echo "$(sudo_)pacman -Sy --noconfirm $1" ;;
    zypper)  echo "$(sudo_)zypper install -y $1" ;;
    *)       echo "" ;;
  esac
}

# ── Homebrew — installs the rest on macOS (and optionally on Linux) ─────────
check_brew() {
  brew_env
  if have brew; then ok brew "$(brew --version 2>/dev/null | awk 'NR==1{print $2}')"; PKG=brew; return; fi
  if [ "$OS" = macos ]; then
    warn brew "Homebrew is the simplest way to install git / docker / uv on macOS"
  else
    skip brew "optional on Linux (your distro's package manager is used instead)"
    return
  fi
  say "$URL_BREW"
  say "$BREW_INSTALL"
  if confirm; then run "$BREW_INSTALL"; brew_env; have brew && PKG=brew; fi
}

# ── git — REQUIRED (clone the repo) ───────────────────────────────────────
check_git() {
  if have git; then ok git "$(git --version | awk '{print $3}')"; return; fi
  miss git "needed to clone the repo"
  say "$URL_GIT"
  local cmd
  if [ "$OS" = macos ] && ! have brew; then cmd="xcode-select --install"
  else cmd="$(pkg_cmd git)"; fi
  [ -n "$cmd" ] && say "$cmd" || say "install git with your OS package manager"
  if [ -n "$cmd" ] && confirm; then run "$cmd"; fi
  have git && ok git "$(git --version | awk '{print $3}')" || REQUIRED_MISSING=1
}

# ── curl — REQUIRED (scripts + installers) ────────────────────────────────
check_curl() {
  if have curl; then ok curl; return; fi
  miss curl "used by the setup scripts and installers"
  local cmd; cmd="$(pkg_cmd curl)"
  [ -n "$cmd" ] && { say "$cmd"; confirm && run "$cmd"; } || say "curl is normally preinstalled"
  have curl || REQUIRED_MISSING=1
}

# ── Docker + Compose v2 + daemon — REQUIRED ──────────────────────────────
check_docker() {
  if ! have docker; then
    miss docker "runs Tracefinity"
    local cmd=""
    if [ "$OS" = macos ]; then
      say "$URL_DOCKER_MAC   (Docker Desktop — you must launch it once after installing)"
      if have brew; then cmd='brew install --cask docker'; say "$cmd"; fi
    elif [ "$OS" = linux ]; then
      say "$URL_DOCKER_LINUX"
      cmd="curl -fsSL https://get.docker.com | sh ; $(sudo_)usermod -aG docker \"\$USER\""
      say "curl -fsSL https://get.docker.com | sh    # then log out/in for the 'docker' group"
    else
      say "install Docker + the compose v2 plugin for your OS: $URL_DOCKER_LINUX"
    fi
    if [ -n "$cmd" ] && confirm; then run "$cmd"; fi
    have docker || { REQUIRED_MISSING=1; return; }
  fi
  ok docker "$(docker --version | awk '{print $3}' | tr -d ,)"

  if docker compose version >/dev/null 2>&1; then
    ok compose "$(docker compose version --short 2>/dev/null)"
  else
    miss compose "the 'docker compose' v2 plugin is required"
    say "$URL_COMPOSE"
    if [ "$OS" = linux ]; then
      local cmd; cmd="$(pkg_cmd docker-compose-plugin)"
      [ -n "$cmd" ] && { say "$cmd"; confirm && run "$cmd"; }
    fi
    docker compose version >/dev/null 2>&1 || REQUIRED_MISSING=1
  fi

  if docker info >/dev/null 2>&1; then
    ok daemon "running"
  else
    warn daemon "installed but not running"
    if [ "$OS" = macos ]; then
      say "open -a Docker   (then wait ~30s)"
      if confirm; then
        open -a Docker 2>/dev/null || true
        for _ in $(seq 1 30); do docker info >/dev/null 2>&1 && break; sleep 2; done
      fi
    elif [ "$OS" = linux ]; then
      say "$(sudo_)systemctl start docker"
      confirm && run "$(sudo_)systemctl start docker"
    fi
    docker info >/dev/null 2>&1 && ok daemon "running" \
      || { REQUIRED_MISSING=1; say "start Docker, then re-run this script"; }
  fi
}

# ── uv — REQUIRED (MCP server + verify.py; bundles Python >= 3.10) ────────
check_uv() {
  if have uv; then ok uv "$(uv --version | awk '{print $2}')"; return; fi
  miss uv "runs the MCP server and verify.py"
  say "$URL_UV"
  local cmd
  if have brew; then cmd='brew install uv'
  else cmd='curl -LsSf https://astral.sh/uv/install.sh | sh'; fi
  say "$cmd"
  if confirm; then run "$cmd"; export PATH="$HOME/.local/bin:$PATH"; fi
  have uv && ok uv "$(uv --version | awk '{print $2}')" || REQUIRED_MISSING=1
}

# ── optional ────────────────────────────────────────────────────────────
check_optional() {
  if have jq; then ok jq
  elif have python3; then ok python3 "(covers the 'install-mcp.sh gemini' fallback; jq not needed)"
  else
    warn jq/python3 "one of them backs 'install-mcp.sh gemini' when the Gemini CLI is absent"
    say "$URL_JQ"
    local cmd; cmd="$(pkg_cmd jq)"
    [ -n "$cmd" ] && { say "$cmd"; confirm && run "$cmd"; }
  fi

  if   have claude; then ok claude "$(claude --version 2>/dev/null | awk '{print $1}')"
  elif have gemini; then ok gemini "$(gemini --version 2>/dev/null | head -1)"
  else warn "MCP client" "no 'claude' or 'gemini' CLI — the server still runs standalone; install one to wire it into an assistant"
  fi

  if have gh; then
    if gh auth status >/dev/null 2>&1; then ok gh "authenticated"
    else warn gh "installed, not logged in — 'gh auth login' only if this repo is PRIVATE"; fi
  else
    skip gh "optional — only to clone a PRIVATE repo or run 'gh' commands ($URL_GH)"
    if [ "$FIX" = 1 ] && [ "$NOFIX" != 1 ]; then
      local cmd; cmd="$(pkg_cmd gh)"
      [ -n "$cmd" ] && { say "$cmd"; confirm && run "$cmd"; }
    fi
  fi
}

# ── PATH advice for the user's shell profile ────────────────────────────
check_path() {
  local advise=0
  for d in "$HOME/.docker/bin" "$HOME/.local/bin"; do
    [ -d "$d" ] && ! echo ":$PATH:" | grep -q ":$d:" && advise=1
  done
  [ "$advise" = 1 ] && {
    warn PATH "add to your shell profile so new shells find these:"
    say 'export PATH="$HOME/.docker/bin:$HOME/.local/bin:$PATH"'
  }
  return 0
}

# ── top-level offer (interactive, no --fix given) ──────────────────────
if [ "$FIX" = 0 ] && [ "$NOFIX" = 0 ] && is_tty; then
  if ! { have git && have docker && have uv; }; then
    printf 'Some required tools are missing. Install them automatically now? [y/N] '
    read -r r </dev/tty 2>/dev/null || r=n
    case "$r" in y|Y|yes|YES) FIX=1; YES=1 ;; esac
    echo
  fi
fi

echo "preflight — os: $OS   pkg: $PKG   mode: $([ "$NOFIX" = 1 ] && echo check-only || { [ "$FIX" = 1 ] && echo fix || echo check; })"
echo
echo "required:"
check_brew
check_git
check_curl
check_docker
check_uv
echo
echo "optional:"
check_optional
echo
check_path
echo
if [ "$REQUIRED_MISSING" = 0 ]; then
  echo "toolchain OK — next:  bash scripts/init.sh"
  exit 0
else
  echo "missing required tools (marked MISS). Re-run with --fix to install them,"
  echo "or use the commands / links above, then run this again."
  exit 1
fi
