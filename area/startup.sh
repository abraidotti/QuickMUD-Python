#!/bin/sh
# POSIX sh port of area/startup (csh), which was
# written by Furey, with additions from Tony and Alander.
#
# Usage: ./startup.sh [port]   (default 4000)
# Runs the game from area/, logging each run to ../log/NNNN.log, and restarts it
# after a crash. The game is python3 -m charm, with game/ on PYTHONPATH (the C
# game's ../area/rom until cut-over; see the c-final tag). A 'shutdown' in game (which writes shutdown.txt) stops the loop.
# SIGTERM or SIGINT stops the game and the loop (for 'docker stop'); the game
# saves everyone first, and the script exits with the game's exit status.

port="${1:-4000}"

# Change to the area directory (the csh script did 'cd ../area').
cd "$(dirname "$0")" || exit 1

rm -f shutdown.txt

pid=
trap 'status=0; if [ -n "$pid" ]; then kill -TERM "$pid" 2>/dev/null; wait "$pid"; status=$?; fi; exit "$status"' TERM INT

while :; do
    index=1000
    while [ -e "../log/$index.log" ]; do
        index=$((index + 1))
    done
    logfile="../log/$index.log"

    python3 -m charm --port "$port" --root .. >"$logfile" 2>&1 &
    pid=$!
    wait "$pid"
    pid=

    # Restart, giving old connections a chance to die.
    if [ -e shutdown.txt ]; then
        # Keep a record of who shut the game down before removing the file.
        echo "startup.sh: shutdown.txt: $(cat shutdown.txt)" >>"$logfile"
        rm -f shutdown.txt
        exit 0
    fi
    sleep 10
done
