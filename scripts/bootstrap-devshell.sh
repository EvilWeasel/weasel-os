#!/usr/bin/env bash
set -euo pipefail

repo_url="${WEASEL_OS_REPO:-https://github.com/EvilWeasel/weasel-os.git}"
branch="${WEASEL_OS_BRANCH:-main}"
root="${WEASEL_OS_ROOT:-$HOME/weasel-os}"
bashrc="${WEASEL_BASHRC:-$HOME/.bashrc}"
marker_begin="# >>> weasel-os devshell auto-enter >>>"

export NIX_CONFIG="${NIX_CONFIG:-experimental-features = nix-command flakes}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

fetch_to_stdout() {
  if need_cmd curl; then
    curl -fsSL "$1"
  elif need_cmd wget; then
    wget -qO- "$1"
  else
    echo "Need curl or wget to download the Nix installer." >&2
    exit 1
  fi
}

source_nix_profile() {
  if [[ -f "$HOME/.nix-profile/etc/profile.d/nix.sh" ]]; then
    # shellcheck disable=SC1091
    . "$HOME/.nix-profile/etc/profile.d/nix.sh"
  elif [[ -f /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh ]]; then
    # shellcheck disable=SC1091
    . /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
  elif [[ -f /nix/var/nix/profiles/default/etc/profile.d/nix.sh ]]; then
    # shellcheck disable=SC1091
    . /nix/var/nix/profiles/default/etc/profile.d/nix.sh
  fi
}

install_nix() {
  if need_cmd nix; then
    return
  fi

  echo "Installing Nix package manager..."
  if [[ "$(uname -s)" == "Linux" ]]; then
    sh <(fetch_to_stdout "https://nixos.org/nix/install") --daemon
  else
    sh <(fetch_to_stdout "https://nixos.org/nix/install")
  fi

  source_nix_profile

  if ! need_cmd nix; then
    echo "Nix installed, but this shell cannot see nix yet. Open a new shell and rerun this script." >&2
    exit 1
  fi
}

git_cmd() {
  if need_cmd git; then
    git "$@"
  else
    nix shell nixpkgs#git -c git "$@"
  fi
}

write_bashrc_block() {
  local root_literal repo_literal branch_literal

  printf -v root_literal "%q" "$root"
  printf -v repo_literal "%q" "$repo_url"
  printf -v branch_literal "%q" "$branch"

  mkdir -p "$(dirname "$bashrc")"
  touch "$bashrc"

  if grep -Fq "$marker_begin" "$bashrc"; then
    return
  fi

  cat >>"$bashrc" <<'EOF'

# >>> weasel-os devshell auto-enter >>>
# Auto-enter the latest weasel-os dev shell on interactive SSH login.
if [[ -n "${SSH_CONNECTION:-}" \
  && -t 0 \
  && $- == *i* \
  && -z "${IN_NIX_SHELL:-}" \
  && -z "${WEASEL_DEV_AUTOENTER:-}" ]]; then

  export WEASEL_DEV_AUTOENTER=1
  export NIX_CONFIG="${NIX_CONFIG:-experimental-features = nix-command flakes}"

  if ! command -v nix >/dev/null 2>&1; then
    if [[ -f "$HOME/.nix-profile/etc/profile.d/nix.sh" ]]; then
      . "$HOME/.nix-profile/etc/profile.d/nix.sh"
    elif [[ -f /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh ]]; then
      . /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
    elif [[ -f /nix/var/nix/profiles/default/etc/profile.d/nix.sh ]]; then
      . /nix/var/nix/profiles/default/etc/profile.d/nix.sh
    fi
  fi

EOF

  cat >>"$bashrc" <<EOF
  WEASEL_OS_DEFAULT_ROOT=$root_literal
  WEASEL_OS_DEFAULT_REPO=$repo_literal
  WEASEL_OS_DEFAULT_BRANCH=$branch_literal
EOF

  cat >>"$bashrc" <<'EOF'

  WEASEL_OS_ROOT="${WEASEL_OS_ROOT:-$WEASEL_OS_DEFAULT_ROOT}"
  WEASEL_OS_REPO="${WEASEL_OS_REPO:-$WEASEL_OS_DEFAULT_REPO}"
  WEASEL_OS_BRANCH="${WEASEL_OS_BRANCH:-$WEASEL_OS_DEFAULT_BRANCH}"

  weasel_git() {
    if command -v git >/dev/null 2>&1; then
      git "$@"
    else
      nix shell nixpkgs#git -c git "$@"
    fi
  }

  if command -v nix >/dev/null 2>&1; then
    if [[ ! -d "$WEASEL_OS_ROOT/.git" ]]; then
      mkdir -p "$(dirname "$WEASEL_OS_ROOT")"
      weasel_git clone --branch "$WEASEL_OS_BRANCH" "$WEASEL_OS_REPO" "$WEASEL_OS_ROOT"
    else
      weasel_git -C "$WEASEL_OS_ROOT" fetch origin "$WEASEL_OS_BRANCH"
      weasel_git -C "$WEASEL_OS_ROOT" checkout "$WEASEL_OS_BRANCH"
      weasel_git -C "$WEASEL_OS_ROOT" pull --ff-only origin "$WEASEL_OS_BRANCH"
    fi

    cd "$WEASEL_OS_ROOT" && exec nix develop .#dev
  fi
fi
# <<< weasel-os devshell auto-enter <<<
EOF
}

install_nix
source_nix_profile

if [[ ! -d "$root/.git" ]]; then
  mkdir -p "$(dirname "$root")"
  git_cmd clone --branch "$branch" "$repo_url" "$root"
else
  git_cmd -C "$root" fetch origin "$branch"
  git_cmd -C "$root" checkout "$branch"
  git_cmd -C "$root" pull --ff-only origin "$branch"
fi

write_bashrc_block

echo "Installed weasel-os devshell bootstrap in $bashrc"
echo "Repo: $root"

if [[ "${WEASEL_ENTER_NOW:-1}" == "1" ]]; then
  cd "$root"
  exec nix develop .#dev
fi
