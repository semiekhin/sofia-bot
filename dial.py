#!/usr/bin/env python3
"""dial.py — outbound dialer for Sofia voice (RIZALTA).

V1: single call per invocation, CDR-based result tracking.

Usage:
    python3 dial.py 8XXXXXXXXXX
    python3 dial.py 7XXXXXXXXXX
    python3 dial.py +7XXXXXXXXXX
    python3 dial.py XXXXXXXXXX   (10 digits, +7 prepended)

Flow:
    1. Normalize phone number to E.164 (+7XXXXXXXXXX)
    2. Snapshot Master.csv size and active channel uniqueids
    3. Run `asterisk -rx 'channel originate PJSIP/<phone>@telphin-endpoint
       extension s@outbound-audiosocket'`
    4. Poll `core show channels concise` for the new telphin-endpoint channel
       → capture its uniqueid (primary CDR match key)
    5. Poll Master.csv until the matching uniqueid row appears
       (fallback: match by dcontext=outbound-audiosocket + phone in channel)
    6. Write one JSONL line to /var/log/sofia-voice/outbound_YYYY-MM-DD.jsonl
    7. Print summary + exit with code per disposition

Exit codes:
    0 = ANSWERED with billsec >= 5 seconds (real conversation)
    1 = NO ANSWER / BUSY / ANSWERED with billsec < 5 (hangup-after-hello)
    2 = invalid phone format / argparse error
    3 = FAILED / originate error / no CDR within timeout
"""

import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import sys
import time

CDR_PATH = "/var/log/asterisk/cdr-csv/Master.csv"
METRICS_DIR = "/var/log/sofia-voice"
CALL_TIMEOUT_SEC = 600  # 10 min: allows 3-5 min RIZALTA conversations
POLL_INTERVAL_SEC = 2
CHANNEL_APPEAR_WAIT_SEC = 5
ORIGINATE_CMD_TIMEOUT = 10
MIN_BILLSEC_SUCCESS = 5  # ANSWERED with billsec < 5 => still a hangup

CDR_FIELDS = [
    "accountcode",
    "src",
    "dst",
    "dcontext",
    "clid",
    "channel",
    "dstchannel",
    "lastapp",
    "lastdata",
    "start",
    "answer",
    "end",
    "duration",
    "billsec",
    "disposition",
    "amaflags",
    "uniqueid",
    "userfield",
]


def normalize_phone(raw: str) -> str | None:
    s = raw.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if s.startswith("+") and len(s) == 12 and s[1:].isdigit() and s[1] == "7":
        return s
    if s.startswith("8") and len(s) == 11 and s.isdigit():
        return "+7" + s[1:]
    if s.startswith("7") and len(s) == 11 and s.isdigit():
        return "+" + s
    if len(s) == 10 and s.isdigit():
        return "+7" + s
    return None


def run_asterisk_cli(cmd_str: str, timeout: int = 5) -> tuple[int, str, str]:
    """Run asterisk -rx and return (rc, stdout, stderr)."""
    result = subprocess.run(
        ["asterisk", "-rx", cmd_str],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def snapshot_channel_uniqueids() -> set[str]:
    """Return set of uniqueids of currently active channels."""
    try:
        rc, out, _ = run_asterisk_cli("core show channels concise")
    except subprocess.TimeoutExpired:
        return set()
    if rc != 0:
        return set()
    ids = set()
    for line in out.splitlines():
        # concise fields separated by '!', uniqueid is last field
        parts = line.strip().split("!")
        if len(parts) >= 13 and parts[0].startswith("PJSIP/"):
            ids.add(parts[12])
    return ids


def find_new_telphin_uniqueid(before: set[str]) -> str | None:
    """Poll core show channels concise for a new telphin-endpoint channel."""
    deadline = time.monotonic() + CHANNEL_APPEAR_WAIT_SEC
    while time.monotonic() < deadline:
        try:
            rc, out, _ = run_asterisk_cli("core show channels concise")
        except subprocess.TimeoutExpired:
            time.sleep(0.5)
            continue
        if rc == 0:
            for line in out.splitlines():
                parts = line.strip().split("!")
                if len(parts) >= 13 and "telphin-endpoint" in parts[0]:
                    uid = parts[12]
                    if uid and uid not in before:
                        return uid
        time.sleep(0.5)
    return None


def find_cdr_by_uniqueid(uniqueid: str) -> dict | None:
    try:
        with open(CDR_PATH, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reversed(list(reader)):
                if len(row) < len(CDR_FIELDS):
                    continue
                if row[16] == uniqueid:  # uniqueid is field #16
                    return dict(zip(CDR_FIELDS, row))
    except FileNotFoundError:
        return None
    return None


def find_cdr_fallback(initial_lines: int, ts_start: dt.datetime) -> dict | None:
    """Fallback match when uniqueid wasn't captured (ring longer than
    CHANNEL_APPEAR_WAIT_SEC). Newest row past initial_lines with
    dcontext=outbound-audiosocket and start >= ts_start - 5s tolerance.
    Works only for sequential single calls — concurrent outbounds can
    confuse this matcher.

    CDR timestamps are UTC (cdr.conf usegmtime=yes). Phone number is
    intentionally NOT used: Asterisk outbound originate does not populate
    CDR src/dst with the dialled number — channel name is just the endpoint
    (PJSIP/telphin-endpoint-XXXXX), phone digits never land in channel
    or dstchannel fields."""
    try:
        with open(CDR_PATH, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
    except FileNotFoundError:
        return None
    tol = dt.timedelta(seconds=5)
    for row in reversed(rows[initial_lines:]):
        if len(row) < len(CDR_FIELDS):
            continue
        rec = dict(zip(CDR_FIELDS, row))
        if rec["dcontext"] != "outbound-audiosocket":
            continue
        try:
            rec_start = dt.datetime.strptime(rec["start"], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=dt.timezone.utc
            )
        except ValueError:
            continue
        if rec_start >= ts_start - tol:
            return rec
    return None


def cdr_line_count() -> int:
    """Number of CSV rows (not newline count — CDR rows may contain
    embedded newlines in quoted CallerID fields, which breaks byte-line
    counting. Observed 17.04: 256 newlines vs 254 csv rows — off-by-2
    made `rows[initial_lines:]` slice empty, fallback matcher saw nothing."""
    try:
        with open(CDR_PATH, newline="", encoding="utf-8") as f:
            return sum(1 for _ in csv.reader(f))
    except FileNotFoundError:
        return 0


def wait_for_cdr(
    uniqueid: str | None, initial_lines: int, ts_start: dt.datetime, timeout_sec: int
) -> dict | None:
    """Poll until CDR row appears. Primary: uniqueid match (fast short-circuit
    when capture worked). Fallback: timestamp+dcontext match — ALWAYS tried
    as safety net, because `core show channels concise` parsing can return
    a wrong value on Asterisk 20 (observed on call 1776446150.338: uniqueid
    was captured but didn't match CDR row). See P3 backlog `dial.py concise
    parser — field index bug`."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_SEC)
        if uniqueid:
            rec = find_cdr_by_uniqueid(uniqueid)
            if rec:
                return rec
        rec = find_cdr_fallback(initial_lines, ts_start)
        if rec:
            return rec
    return None


def write_jsonl(record: dict) -> str:
    os.makedirs(METRICS_DIR, exist_ok=True)
    day = dt.datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(METRICS_DIR, f"outbound_{day}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def disposition_to_exit(disposition: str, billsec: int) -> int:
    if disposition == "ANSWERED":
        return 0 if billsec >= MIN_BILLSEC_SUCCESS else 1
    if disposition in ("NO ANSWER", "NOANSWER", "BUSY"):
        return 1
    return 3


def main() -> int:
    p = argparse.ArgumentParser(
        description="Outbound dialer for Sofia voice",
        epilog="Phone formats: 8XXXXXXXXXX, 7XXXXXXXXXX, +7XXXXXXXXXX, or 10-digit",
    )
    p.add_argument("phone_number", help="Phone number to call")
    args = p.parse_args()

    phone = normalize_phone(args.phone_number)
    if not phone:
        print(f"Error: invalid phone format {args.phone_number!r}", file=sys.stderr)
        print(
            "Expected 10 digits, 11 digits starting with 7 or 8, or +7XXXXXXXXXX",
            file=sys.stderr,
        )
        return 2

    ts_start = dt.datetime.now(dt.timezone.utc)
    initial_lines = cdr_line_count()
    channels_before = snapshot_channel_uniqueids()
    uniqueid: str | None = None  # what concise parser captured (may differ from CDR)

    originate_cmd = (
        f"channel originate PJSIP/{phone}@telphin-endpoint "
        f"extension s@outbound-audiosocket"
    )
    try:
        rc, _stdout, stderr = run_asterisk_cli(
            originate_cmd, timeout=ORIGINATE_CMD_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        rec_err = {
            "ts_start": ts_start.isoformat(),
            "ts_end": dt.datetime.now(dt.timezone.utc).isoformat(),
            "phone": phone,
            "uuid": None,
            "captured_uniqueid": uniqueid,
            "disposition": "FAILED",
            "duration": 0,
            "billsec": 0,
            "exit_code": 3,
            "error": "originate_cli_timeout",
        }
        path = write_jsonl(rec_err)
        print(f"Call: {phone}\nUUID: -\nStatus: FAILED (CLI timeout)\nLog: {path}")
        return 3

    if rc != 0:
        rec_err = {
            "ts_start": ts_start.isoformat(),
            "ts_end": dt.datetime.now(dt.timezone.utc).isoformat(),
            "phone": phone,
            "uuid": None,
            "captured_uniqueid": uniqueid,
            "disposition": "FAILED",
            "duration": 0,
            "billsec": 0,
            "exit_code": 3,
            "error": f"originate_rc={rc}",
            "stderr": stderr[:200],
        }
        path = write_jsonl(rec_err)
        print(
            f"Call: {phone}\nUUID: -\nStatus: FAILED (originate rc={rc})\nLog: {path}"
        )
        return 3

    # Capture uniqueid of the newly created telphin-endpoint channel.
    # Known-unreliable on Asterisk 20 — value is persisted to JSONL as
    # "captured_uniqueid" for post-mortem comparison with CDR.uniqueid.
    uniqueid = find_new_telphin_uniqueid(channels_before)

    # Poll CDR until row appears
    rec = wait_for_cdr(uniqueid, initial_lines, ts_start, CALL_TIMEOUT_SEC)
    ts_end = dt.datetime.now(dt.timezone.utc)

    if not rec:
        rec_err = {
            "ts_start": ts_start.isoformat(),
            "ts_end": ts_end.isoformat(),
            "phone": phone,
            "uuid": None,
            "captured_uniqueid": uniqueid,
            "disposition": "FAILED",
            "duration": 0,
            "billsec": 0,
            "exit_code": 3,
            "error": f"no_cdr_after_{CALL_TIMEOUT_SEC}s",
        }
        path = write_jsonl(rec_err)
        print(
            f"Call: {phone}\nUUID: {uniqueid or '-'}\n"
            f"Status: FAILED (no CDR after {CALL_TIMEOUT_SEC}s)\nLog: {path}"
        )
        return 3

    disposition = rec["disposition"]
    duration = int(rec["duration"]) if rec["duration"].isdigit() else 0
    billsec = int(rec["billsec"]) if rec["billsec"].isdigit() else 0
    exit_code = disposition_to_exit(disposition, billsec)

    record = {
        "ts_start": ts_start.isoformat(),
        "ts_end": ts_end.isoformat(),
        "phone": phone,
        "uuid": rec["uniqueid"],
        "captured_uniqueid": uniqueid,
        "disposition": disposition,
        "duration": duration,
        "billsec": billsec,
        "exit_code": exit_code,
    }
    path = write_jsonl(record)
    print(f"Call: {phone}")
    print(f"UUID: {rec['uniqueid']}")
    print(f"Status: {disposition}")
    print(f"Duration: {duration}s (billsec: {billsec}s)")
    print(f"Log: {path}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
