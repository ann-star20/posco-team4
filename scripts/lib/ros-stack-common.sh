#!/usr/bin/env bash

source_setup_safely() {
  local setup_file="$1" restore_nounset=false rc
  case "$-" in *u*) restore_nounset=true ;; esac
  set +u
  if source "$setup_file"; then rc=0; else rc=$?; fi
  $restore_nounset && set -u
  return "$rc"
}

valid_ipv4() {
  local ip="$1" part
  [[ "$ip" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || return 1
  IFS=. read -r -a parts <<< "$ip"
  for part in "${parts[@]}"; do
    ((10#$part <= 255)) || return 1
  done
}

detect_lan_ip() {
  local peer_ip="$1" ip candidate="" peer_prefix
  peer_prefix="${peer_ip%.*}."
  for ip in ${FAB_HOST_IPS:-$(hostname -I)}; do
    valid_ipv4 "$ip" || continue
    case "$ip" in
      127.*|169.254.*|172.17.*|192.168.55.*) continue ;;
    esac
    [[ -z "$candidate" ]] && candidate="$ip"
    if [[ "$ip" == "$peer_prefix"* ]]; then
      printf '%s\n' "$ip"
      return 0
    fi
  done
  [[ -n "$candidate" ]] || return 1
  printf '%s\n' "$candidate"
}

write_fastdds_profile() {
  local output="$1" profile="$2" local_ip="$3" peer_ip="$4"
  mkdir -p "$(dirname "$output")"
  cat > "$output" <<EOF
<?xml version="1.0" encoding="UTF-8" ?>
<profiles xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles">
  <participant profile_name="$profile" is_default_profile="true">
    <rtps>
      <builtin>
        <initialPeersList>
          <locator><udpv4><address>$peer_ip</address></udpv4></locator>
          <locator><udpv4><address>$local_ip</address></udpv4></locator>
          <locator><udpv4><address>127.0.0.1</address></udpv4></locator>
        </initialPeersList>
      </builtin>
    </rtps>
  </participant>
</profiles>
EOF
}

pid_is_running() {
  local pid_file="$1" pid
  [[ -f "$pid_file" ]] || return 1
  read -r pid < "$pid_file"
  [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null
}

start_managed_process() {
  local name="$1" runtime="$2"
  shift 2
  local pid_file="$runtime/$name.pid" log_file="$runtime/$name.log"
  if pid_is_running "$pid_file"; then
    echo "$name: 이미 실행 중 (PID $(cat "$pid_file"))"
    return 0
  fi
  # setsid detaches into a new session/process group so a terminal Ctrl+C
  # (e.g. while breaking out of `logs`/`tail -f`) cannot deliver SIGINT to
  # this worker and trigger rclpy's ExternalShutdownException.
  setsid nohup "$@" >> "$log_file" 2>&1 < /dev/null &
  echo "$!" > "$pid_file"
  echo "$name: 시작됨 (PID $!, 로그 $log_file)"
}

stop_managed_process() {
  local name="$1" runtime="$2" pid_file pid
  pid_file="$runtime/$name.pid"
  if ! pid_is_running "$pid_file"; then
    rm -f "$pid_file"
    echo "$name: 실행 중이 아님"
    return 0
  fi
  read -r pid < "$pid_file"
  kill "$pid"
  for _ in 1 2 3 4 5; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  kill -0 "$pid" 2>/dev/null && kill -TERM "$pid" 2>/dev/null || true
  rm -f "$pid_file"
  echo "$name: 종료됨"
}

show_managed_status() {
  local name="$1" runtime="$2" pid_file
  pid_file="$runtime/$name.pid"
  if pid_is_running "$pid_file"; then
    echo "$name: RUNNING (PID $(cat "$pid_file"))"
  else
    echo "$name: STOPPED"
  fi
}

check_python_imports() {
  local python_bin="$1"
  shift
  "$python_bin" -c '
import importlib.util, sys
missing = [m for m in sys.argv[1:] if importlib.util.find_spec(m) is None]
if missing:
    print("누락된 Python 패키지: " + ", ".join(missing), file=sys.stderr)
    sys.exit(1)
' "$@"
}

ensure_windows_firewall_rule() {
  # WSL에서만 의미가 있다. powershell.exe interop이 없으면 건너뛴다(예: 순수 Linux 호스트).
  local display_name="$1" remote_ip="$2" port_range="$3" current_remote
  command -v powershell.exe >/dev/null 2>&1 || return 0
  current_remote="$(powershell.exe -NoProfile -Command \
    "(Get-NetFirewallRule -DisplayName '$display_name' -ErrorAction SilentlyContinue | Get-NetFirewallAddressFilter -ErrorAction SilentlyContinue).RemoteAddress" \
    2>/dev/null | tr -d '\r')"
  if [[ "$current_remote" == "$remote_ip" ]]; then
    echo "방화벽 규칙 '$display_name' 확인됨 (RemoteAddress=$remote_ip)"
    return 0
  fi
  if [[ -z "$current_remote" ]]; then
    echo "방화벽 규칙 '$display_name' 없음. 관리자 권한으로 생성 시도(UAC 승인 창이 뜨면 승인하세요)..."
    if powershell.exe -NoProfile -Command \
      "Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile -Command \"New-NetFirewallRule -DisplayName ''$display_name'' -Direction Inbound -Protocol UDP -LocalPort $port_range -RemoteAddress $remote_ip -Action Allow\"'" \
      2>/dev/null
    then
      echo "방화벽 규칙 생성 완료"
    else
      echo "경고: 방화벽 규칙을 자동으로 만들지 못했습니다. 관리자 PowerShell에서 직접 추가하세요:" >&2
      echo "  New-NetFirewallRule -DisplayName \"$display_name\" -Direction Inbound -Protocol UDP -LocalPort $port_range -RemoteAddress $remote_ip -Action Allow" >&2
    fi
    return 0
  fi
  echo "방화벽 규칙 '$display_name'의 RemoteAddress가 변경됨 ($current_remote -> $remote_ip). 관리자 권한으로 갱신 시도(UAC 승인 창이 뜨면 승인하세요)..."
  if powershell.exe -NoProfile -Command \
    "Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile -Command \"Set-NetFirewallRule -DisplayName ''$display_name'' -RemoteAddress $remote_ip\"'" \
    2>/dev/null
  then
    echo "방화벽 규칙 RemoteAddress 갱신 완료 ($remote_ip)"
  else
    echo "경고: 방화벽 규칙을 자동으로 갱신하지 못했습니다. 관리자 PowerShell에서 직접 갱신하세요:" >&2
    echo "  Set-NetFirewallRule -DisplayName \"$display_name\" -RemoteAddress $remote_ip" >&2
  fi
}

show_ros_graph() {
  echo '=== ROS 노드 ==='
  ros2 node list --no-daemon || true
  local topic
  for topic in /fab/events /fab/event_acks /fab/surrogate_requests /fab/diagnosis_requests; do
    echo "=== $topic ==="
    ros2 topic info "$topic" --verbose --no-daemon || true
  done
}
