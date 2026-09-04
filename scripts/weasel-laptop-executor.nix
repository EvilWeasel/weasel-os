{ pkgs, codexPackage }:

pkgs.writeShellApplication {
  name = "weasel-laptop-executor";
  runtimeInputs = with pkgs; [
    coreutils
    gnugrep
    systemd
    util-linux
  ];
  text = ''
    set -euo pipefail
    umask 077

    state_root="$HOME/.local/state/weasel-laptop-executor"
    inbox="$state_root/inbox"
    runs="$state_root/runs"
    mkdir -p "$inbox" "$runs"
    chmod 0700 "$state_root" "$inbox" "$runs"

    usage() {
      echo "usage: weasel-laptop-executor {submit <id> <workdir> <prompt-file>|status <id>|collect <id>|stop <id>}" >&2
      exit 2
    }

    valid_id() {
      [[ $1 =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]]
    }

    unit_for() {
      printf 'weasel-laptop-executor-%s.service\n' "$1"
    }

    validate_workdir() {
      local resolved
      resolved="$(realpath -e -- "$1")"
      case "$resolved/" in
        "$HOME/weasel-os/"*|"$HOME/business-burrow/"*) printf '%s\n' "$resolved" ;;
        *) echo "workdir is outside the approved laptop repositories" >&2; exit 1 ;;
      esac
    }

    command="''${1:-}"
    case "$command" in
      submit)
        [[ $# -eq 4 ]] || usage
        task_id=$2
        valid_id "$task_id" || { echo "invalid task id" >&2; exit 1; }
        workdir="$(validate_workdir "$3")"
        prompt="$(realpath -e -- "$4")"
        case "$prompt" in "$inbox/"*) ;; *) echo "prompt must be under $inbox" >&2; exit 1 ;; esac
        [[ -f $prompt && ! -L $prompt ]] || { echo "prompt must be a regular non-symlink file" >&2; exit 1; }
        mode="$(stat -c %a -- "$prompt")"
        (( (8#$mode & 077) == 0 )) || { echo "prompt must not be group/world accessible" >&2; exit 1; }
        run_dir="$runs/$task_id"
        mkdir -p "$run_dir"
        chmod 0700 "$run_dir"
        cp --reflink=auto -- "$prompt" "$run_dir/prompt.txt"
        chmod 0600 "$run_dir/prompt.txt"
        unit="$(unit_for "$task_id")"
        systemctl --user reset-failed "$unit" 2>/dev/null || true
        systemd-run --user --collect --unit="''${unit%.service}" \
          --property="WorkingDirectory=$workdir" \
          --property="RuntimeMaxSec=4h" \
          --property="TimeoutStopSec=20s" \
          --setenv="WEASEL_EXECUTOR_RUN_DIR=$run_dir" \
          "$0" _run "$task_id" "$workdir" "$run_dir/prompt.txt"
        printf '%s\n' "$unit"
        ;;
      _run)
        [[ $# -eq 4 ]] || usage
        task_id=$2
        workdir="$(validate_workdir "$3")"
        prompt=$4
        run_dir="''${WEASEL_EXECUTOR_RUN_DIR:?missing run directory}"
        started="$(date --iso-8601=seconds)"
        printf '%s\n' "$started" > "$run_dir/started-at"
        set +e
        ${codexPackage}/bin/codex exec \
          --sandbox workspace-write \
          --cd "$workdir" \
          --json \
          --output-last-message "$run_dir/final.md" \
          -c 'mcp_servers={}' \
          - < "$prompt" > "$run_dir/events.jsonl" 2> "$run_dir/stderr.log"
        rc=$?
        set -e
        printf '%s\n' "$rc" > "$run_dir/exit-code"
        date --iso-8601=seconds > "$run_dir/ended-at"
        chmod 0600 "$run_dir"/*
        exit "$rc"
        ;;
      status)
        [[ $# -eq 2 ]] || usage
        valid_id "$2" || exit 1
        systemctl --user --no-pager --full status "$(unit_for "$2")" || true
        test -f "$runs/$2/exit-code" && printf 'exit-code=%s\n' "$(cat "$runs/$2/exit-code")"
        ;;
      collect)
        [[ $# -eq 2 ]] || usage
        valid_id "$2" || exit 1
        test -f "$runs/$2/final.md"
        cat "$runs/$2/final.md"
        ;;
      stop)
        [[ $# -eq 2 ]] || usage
        valid_id "$2" || exit 1
        systemctl --user stop "$(unit_for "$2")"
        ;;
      *) usage ;;
    esac
  '';
}
