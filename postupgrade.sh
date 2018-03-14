#!/bin/bash

echo "<INFO> Copy back existing config files"
cp -v -r /tmp/REPLACELBPPLUGINDIR/* REPLACELBPCONFIGDIR/

echo "<INFO> Remove temporary folders"
rm -rf /tmp/REPLACELBPPLUGINDIR

echo "<INFO> Trigger re-install "
touch REPLACELBPCONFIGDIR/modify.me

# Exit with Status 0
exit 0
