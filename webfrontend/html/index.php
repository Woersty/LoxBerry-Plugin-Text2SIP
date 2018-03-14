<?php
// LoxBerry Text2SIP-Plugin
// Christian Woerstenfeld - git@loxberry.woerstenfeld.de
//14.03.2018 20:45:54

// Configuration parameters
error_reporting(~E_STRICT & ~E_NOTICE);     // Keine Strict / Notice Fehler reporten 
ini_set("display_errors", false);        // Fehler nicht direkt via PHP ausgeben
require_once "loxberry_system.php";
require_once "loxberry_log.php";
#$L = LBSystem::readlanguage("language.ini");
$plugindata = LBSystem::plugindata();
ini_set("log_errors", 1);
ini_set("error_log", $lbplogdir."/Text2SIP.log");
$psubdir              =array_pop(array_filter(explode('/',pathinfo($_SERVER["SCRIPT_FILENAME"],PATHINFO_DIRNAME))));
$mydir                =pathinfo($_SERVER["SCRIPT_FILENAME"],PATHINFO_DIRNAME);
$pluginlogfile        =$lbplogdir."/Text2SIP.log";
$sipcmdlogfile        =$lbplogdir."/Text2SIP.log";
$plugindatadir        =$mydir."/../../../../data/plugins/$psubdir/wav";
$plugincfgfile        =$mydir."/../../../../config/plugins/$psubdir/Text2SIP.cfg";
$pluginlanguagefile   =$mydir."/../../../../templates/plugins/$psubdir/de/language.dat";
$user                 ="Text2SIP";
$pass                 ="loxberry";
$pico2wave            = "/usr/bin/pico2wave";
$sox                  = "/usr/bin/sox";
$sipcmd               = $mydir."/../../../../webfrontend/htmlauth/plugins/$psubdir/bin/sipcmd";
$option_o             = ""; # Heavy sipcmd Debug 


$plugin_phrase_array  = parse_ini_file("$pluginlanguagefile");
$plugin_cfg_array     = parse_ini_file("$plugincfgfile");
$DEBUG_USE            = $plugin_cfg_array['DEBUG_USE'                            ];
$PLUGIN_USE           = $plugin_cfg_array['PLUGIN_USE'                           ];
if ( !$PLUGIN_USE == "on" ) { die( $PLUGIN_USE.$plugin_phrase_array['ERROR0003'] ); }

$datetime    = new DateTime;
function debug($message = "", $parameter = "", $loglevel = 7 )
{
	global $L,$plugindata, $DEBUG_USE,$plugin_phrase_array;
  
  if ( $DEBUG_USE == "1" ) { $loglevel = 7; }
  
  if ( isset($plugin_phrase_array[$message]) )
  {
    $message = $plugin_phrase_array[$message];
  }
  $message = $message . "" . $parameter;
  
	if ( $plugindata['PLUGINDB_LOGLEVEL'] >= intval($loglevel)   )
	{
		switch ($loglevel)
		{
		    case 0:
		        // OFF
		        break;
		    case 1:
		        error_log( strftime("%A") ." <ALERT> PHP: ".$message );
		        break;
		    case 2:
		        error_log( strftime("%A") ." <CRITICAL> PHP: ".$message );
		        break;
		    case 3:
		        error_log( strftime("%A") ." <ERROR> PHP: ".$message );
		        break;
		    case 4:
		        error_log( strftime("%A") ." <WARNING> PHP: ".$message );
		        break;
		    case 5:
		        error_log( strftime("%A") ." <OK> PHP: ".$message );
		        break;
		    case 6:
		        error_log( strftime("%A") ." <INFO> PHP: ".$message );
		        break;
		    case 7:
		    default:
		        error_log( strftime("%A") ." PHP: ".$message );
		        break;
		}
		if ( $loglevel < 4 ) 
		{
		  #if ( isset($message) && $message != "" ) notify ( LBPPLUGINDIR, $L['MY_NAME'], $message);
		}
	}
	return;
}









// Defaults for inexistent variables
if (!isset($_REQUEST["mode"])) {$_REQUEST["mode"] = 'normal';}

if($_REQUEST["mode"] == "download_logfile")
{
  if (file_exists($pluginlogfile))
  {
    error_log( date('Y-m-d H:i:s ')."[LOG] Download logfile\n", 3, $pluginlogfile);
    header('Content-Description: File Transfer');
    header('Content-Type: text/plain');
    header('Content-Disposition: attachment; filename="'.basename($pluginlogfile).'"');
    header('Expires: 0');
    header('Cache-Control: must-revalidate');
    header('Pragma: public');
    header('Content-Length: ' . filesize($pluginlogfile));
    readfile($pluginlogfile);
  }
  else
  {
    error_log( date('Y-m-d H:i:s ')."Error reading logfile!\n", 3, $pluginlogfile);
    die("Error reading logfile.");
  }
  exit;
}
else if($_REQUEST["mode"] == "empty_logfile")
{
  if (file_exists($pluginlogfile))
  {
        $f = @fopen("$pluginlogfile", "r+");
        if ($f !== false)
        {
            ftruncate($f, 0);
            fclose($f);
            debug( "Logfile content deleted", "", 6);
            $result = "\n<img src='/plugins/$psubdir/Text2SIP_ok.png'>";
        }
        else
        {
            debug( "Logfile content not deleted due to problems doing it.","", 3);
            $result = "\n<img src='/plugins/$psubdir/Text2SIP_fail.png'>";
        }
  }
  else
  {
    $result = "\n<img src='/plugins/$psubdir/Text2SIP_fail.png'>";
  }
}
else if($_REQUEST["mode"] == "make_call")
{
    error_log( date('Y-m-d H:i:s ').$plugin_phrase_array['DBG_VG_REQUEST'].$_REQUEST["vg"]."\n", 3, $pluginlogfile);
    if ( $_REQUEST["vg"] == "" )
    {
      error_log( date('Y-m-d H:i:s ').$plugin_phrase_array['ERROR0001']."\n", 3, $pluginlogfile);
      die($plugin_phrase_array['ERROR0001']);
    }
    $guide                              = intval($_REQUEST["vg"]);
    if ( $guide == 0 )
    {
      error_log( date('Y-m-d H:i:s ').$plugin_phrase_array['ERROR0002']."\n", 3, $pluginlogfile);
      die($plugin_phrase_array['ERROR0002']);
    }

    $P2W_lang                       = $plugin_cfg_array['P2W_lang'.$guide];
    $P2W_Text                       = $plugin_cfg_array['P2W_Text'.$guide                      ];
    $SIPCMD_CALLING_USER_NUMBER     = $plugin_cfg_array['SIPCMD_CALLING_USER_NUMBER'.$guide    ];
    $SIPCMD_CALLING_USER_PASSWORD   = $plugin_cfg_array['SIPCMD_CALLING_USER_PASSWORD'.$guide  ];
    $SIPCMD_CALLING_USER_NAME       = $plugin_cfg_array['SIPCMD_CALLING_USER_NAME'.$guide      ];
    $SIPCMD_SIP_PROXY               = $plugin_cfg_array['SIPCMD_SIP_PROXY'.$guide              ];
    $SIPCMD_CALLED_USER             = $plugin_cfg_array['SIPCMD_CALLED_USER'.$guide            ];
    $SIPCMD_CALL_PAUSE_BEFORE_GUIDE = $plugin_cfg_array['SIPCMD_CALL_PAUSE_BEFORE_GUIDE'.$guide];
    $SIPCMD_CALL_PAUSE_AFTER_GUIDE  = $plugin_cfg_array['SIPCMD_CALL_PAUSE_AFTER_GUIDE'.$guide ];
    $SIPCMD_CALL_RESULT_VI          = $plugin_cfg_array['SIPCMD_CALL_RESULT_VI'.$guide         ];
    $SIPCMD_CALL_TIMEOUT            = $plugin_cfg_array['SIPCMD_CALL_TIMEOUT'.$guide           ];
    $SIPCMD_CONFIRMATION_DIGIT      = $plugin_cfg_array['SIPCMD_CONFIRMATION_DIGIT'.$guide     ];
    $SIPCMD_MSINFO                  = $plugin_cfg_array['SIPCMD_MSINFO'.$guide                 ];

    if ( preg_match('/[0-9\*\#]/', $SIPCMD_CONFIRMATION_DIGIT) )
    {
      $SIPCMD_CONFIRMATION_DIGIT = $SIPCMD_CONFIRMATION_DIGIT;
    }
    else
    {
      $SIPCMD_CONFIRMATION_DIGIT = "-";
    };

    if       ($P2W_lang == "gb" ) { $P2W_lang = "en-GB"; $unknown = "unknown";    }
    else if  ($P2W_lang == "us" ) { $P2W_lang = "en-US"; $unknown = "unknown";    }
    else if  ($P2W_lang == "es" ) { $P2W_lang = "es-ES"; $unknown = "desconocido";}
    else if  ($P2W_lang == "fr" ) { $P2W_lang = "fr-FR"; $unknown = "inconnu";    }
    else if  ($P2W_lang == "it" ) { $P2W_lang = "it-IT"; $unknown = "sconosciuto";}
    else if  ($P2W_lang == "de" ) { $P2W_lang = "de-DE"; $unknown = "unbekannt";  }
    else
    {
      debug('DBG_INVALID_LANGUAGE',$P2W_lang,3);
      $P2W_lang = "de-DE";
      $unknown = "unbekannt";
    }

    if(isset($_REQUEST["info"]))
    {
      $state = file_get_contents($_REQUEST["info"]);
      $P2W_Text = $P2W_Text." ".preg_replace("/[^A-Za-z0-9‰ˆ¸ﬂA÷‹.,-_]/", '', stripos ( stristr('value="',$state,true), '" Code', 20 ));
    }


    $tempname_prefix = tempnam("$plugindatadir/", "Text2SIP_WEB_");
    $pluginjobfile   = $tempname_prefix.".tsp";
    $plugintmpfile   = $tempname_prefix.".tmp.wav";
    $pluginwavfile   = $tempname_prefix."_wav";
    $pluginjobfile_handle = fopen($pluginjobfile, "w");
    if ( !$pluginjobfile_handle )
    {
      error_log( date('Y-m-d H:i:s ').$plugin_phrase_array['ERROR0004']."\n", 3, $pluginlogfile);
      die($plugin_phrase_array['ERROR0004']);
    }

    system ('echo | nc -w 1 "'.$SIPCMD_SIP_PROXY.'" 5060',$code);
    if ( $code == 0 )
    {
      debug('DBG_OK_CONNECT_PROXY'," Proxy: $SIPCMD_SIP_PROXY",5);
    }
    else
    {
      error_log( date('Y-m-d H:i:s ').$plugin_phrase_array['ERROR0005']." ($SIPCMD_SIP_PROXY)\n", 3, $pluginlogfile);
      die($plugin_phrase_array['ERROR0005']." ($SIPCMD_SIP_PROXY)");
    }

    if ( preg_match("/[0-9\*\#]/",$SIPCMD_CONFIRMATION_DIGIT) )
    {
      $SIPCMD_CONFIRMATION_DIGIT = $SIPCMD_CONFIRMATION_DIGIT;
    }
    else
    {
      $SIPCMD_CONFIRMATION_DIGIT = "-";
    };

    if ( "$SIPCMD_MSINFO" <> "" )
    {
      $cmd = '/usr/bin/wget -a "'.$pluginlogfile.'" --retry-connrefused --tries=2 --waitretry=1 --timeout=1 --passive-ftp -nH -qO- "'.$SIPCMD_MSINFO.'" 2>&1|grep value|cut -d\" -f4';
      $msinfo = exec( $cmd, $output , $retval);
      if ($retval <> 0 || $msinfo == "")
      {
        debug( $plugin_phrase_array['ERROR0006'], " $SIPCMD_MSINFO ", 4);
        $P2W_Text = str_replace("##", $unknown, $P2W_Text);
      }
      else
      {
        debug ( $plugin_phrase_array['TXT_SIPCMD_READ_MS_STATE']," $msinfo \n", 6);
        $P2W_Text = str_replace("##", $msinfo, $P2W_Text);
      }
    }

    debug('DBG_CREATE_JOB',$pluginjobfile,6);
    $cmd = $pico2wave . ' -l "'.$P2W_lang.'" -w "'.$plugintmpfile.'" "'.$P2W_Text.'" 2>&1 >>'.$pluginlogfile;
    fwrite($pluginjobfile_handle, "$cmd \n");
    debug('DBG_ADD_CMD_TO_JOB',$cmd,6 );
    $cmd = $sox  . ' -v 0.9 "'.$plugintmpfile.'" -t wav -b 16 -r 8000 "'.$pluginwavfile.'" 2>&1 >>'.$pluginlogfile;
    fwrite($pluginjobfile_handle, "$cmd \n");
    debug('DBG_ADD_CMD_TO_JOB',$cmd,7);
    $check_result ="";
    $debug_value  ='2>/dev/null';
    if ( $DEBUG_USE == "1" )
    {
      $debug_value = '2>&1';
      $option_o = " -o $sipcmdlogfile ";
    }
 		else
    {
	   	$sclf = @fopen("$sipcmdlogfile", "r+");
			if ($sclf !== false) 
			{
			    ftruncate($sclf, 0);
			    fclose($sclf);
			}
  	}
    
    if ( !$SIPCMD_CALL_RESULT_VI == "" && substr($SIPCMD_CALL_RESULT_VI,0,7) == "http://")
    {
      $check_result = '|while read DTMF_LINE; do echo $DTMF_LINE|grep -q "Exiting."; if [ $? -eq 0 ]; then wget -q -t 1 -T 10 -O /dev/null "'.$SIPCMD_CALL_RESULT_VI.'0"; fi; DTMF_CODE=`echo $DTMF_LINE |grep "receive DTMF:"|cut -c16`; echo "DTMF: $DTMF_CODE"; wget -q -t 1 -T 10 -O /dev/null "'.$SIPCMD_CALL_RESULT_VI.'$DTMF_CODE"; echo $DTMF_LINE|grep -q "receive DTMF:";  if [ "$DTMF_CODE" == "'.$SIPCMD_CONFIRMATION_DIGIT.'" ]; then echo "Confirmation code '.$SIPCMD_CONFIRMATION_DIGIT.' detected. Exit!!" >> '.$pluginlogfile.'; sleep .5; killall -15 '.$sipcmd.'; else if [ ${#DTMF_CODE} -eq 1 ]; then echo "Confirmation code [$DTMF_CODE] detected but ['.$SIPCMD_CONFIRMATION_DIGIT.'] expected. Continue..." >> '.$pluginlogfile.'; fi; fi; done ';
    }
    if ( $SIPCMD_CALL_TIMEOUT < 1 )
    {
      $SIPCMD_CALL_TIMEOUT = 60;
    }
    $cmd = $sipcmd .  $option_o . ' -m "G.711*" -T '.$SIPCMD_CALL_TIMEOUT.' -P sip -u "'.$SIPCMD_CALLING_USER_NUMBER.'" -c "'.$SIPCMD_CALLING_USER_PASSWORD.'" -a "'.$SIPCMD_CALLING_USER_NAME.'" -w "'.$SIPCMD_SIP_PROXY.'" -x "c'.$SIPCMD_CALLED_USER.';w'.$SIPCMD_CALL_PAUSE_BEFORE_GUIDE.';v'.$pluginwavfile.';w'.$SIPCMD_CALL_PAUSE_AFTER_GUIDE.';h" '.$debug_value.' |tee -a '.$pluginlogfile.$check_result;
    fwrite($pluginjobfile_handle, "$cmd \n");
    debug('DBG_ADD_CMD_TO_JOB',$cmd,6);

    $cmd = 'rm -f '.$tempname_prefix.'* 2>&1 >>'.$pluginlogfile;
    fwrite($pluginjobfile_handle, "$cmd \n");

    $cmd = 'cat '.$sipcmdlogfile.' >>'.$pluginlogfile;
    fwrite($pluginjobfile_handle, "$cmd \n");

    $cmd = 'rm -f /tmp/ts-out.* 2>&1 >>'.$pluginlogfile;
    fwrite($pluginjobfile_handle, "$cmd \n");

    debug('DBG_ADD_CMD_TO_JOB',$cmd,6);
    $cmd = "tsp bash $pluginjobfile  2>&1 >>$pluginlogfile \n";
    error_log( date('Y-m-d H:i:s ').$plugin_phrase_array['DBG_ADD_JOB_TO_QUEUE']." ->".$plugin_phrase_array['DBG_ADD_JOB_TO_QUEUE_ID'], 3, $pluginlogfile);
	exec( "/bin/chmod +x $sipcmd" );
    exec( $cmd );
    fclose($pluginjobfile_handle);
    echo ":o)";
    exit;
}
else
{
    $result = "?! :o(";
}

header('Content-Type: text/plain; charset=utf-8');
echo "$result";
exit;
