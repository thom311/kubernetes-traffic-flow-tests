#!/bin/bash

LOGFILE="$(mktemp -t simple-exec-output.XXXXXXXXXX)"
exec > >(tee "$LOGFILE") 2>&1

ORIG_ARGS=()
for i in $(seq 1 "$((ORIG_ARGS_N - 1))") ; do
    v="ORIG_ARGS_$i"
    ORIG_ARGS+=("${!v}")
done
unset v

echo "output redirected to $LOGFILE"

set -x

env
ip -4 a
ip -4 r
ping -c4 "$ADDR"

rc=0
"$ORIG_ARGS_0" "${ORIG_ARGS[@]}" "--exec" "" -v || rc="$?"

if [ "$rc" -ne 0 ] ; then
    ping -c1000 "$ADDR"
    exit $rc
fi
