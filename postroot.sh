#!/bin/bash

logfile="REPLACELBPLOGDIR/Text2SIP.log"
date        >> $logfile
chown loxberry $logfile
chgrp loxberry $logfile
chmod 660      $logfile
echo "Start Text2SIP installation, for further infos see Plugin logfile" >>$logfile 2>&1
bash REPLACELBHOMEDIR/system/daemons/plugins/Text2SIP                    >>$logfile 2>&1 &
exit 0
