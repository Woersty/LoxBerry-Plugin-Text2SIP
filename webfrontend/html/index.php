<?php
// LoxBerry Text2SIP-Plugin
// Christian Woerstenfeld - git@loxberry.woerstenfeld.de
// 12.02.2019 19:04:57

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
#********************** Added/changed by OL ***********************************
$lame 				  = "/usr/bin/lame";
#******************************************************************************
$sipcmd               = $mydir."/../../../../webfrontend/htmlauth/plugins/$psubdir/bin/sipcmd";
$option_o             = ""; # Heavy sipcmd Debug 


$plugin_phrase_array  = parse_ini_file("$pluginlanguagefile");
$plugin_cfg_array     = parse_ini_file("$plugincfgfile");
$DEBUG_USE            = $plugin_cfg_array['DEBUG_USE'                            ];
$PLUGIN_USE           = $plugin_cfg_array['PLUGIN_USE'                           ];

if ( !$PLUGIN_USE == "on" ) { die( $PLUGIN_USE.$plugin_phrase_array['ERROR0003'] ); }

if (!is_dir($lbplogdir)) 
{
	if (!mkdir($lbplogdir)) 
	{
		die($plugin_phrase_array['ERROR0007']);
	}
}
if (!touch($pluginlogfile)) die($plugin_phrase_array['ERROR0008']);
if (!touch($sipcmdlogfile)) die($plugin_phrase_array['ERROR0008']);

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
      $P2W_Text = $P2W_Text." ".preg_replace("/[^A-Za-z0-9����A��.,-_]/", '', stripos ( stristr('value="',$state,true), '" Code', 20 ));
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

    if ( preg_match("/[0-9\*\#]/",$SIPCMD_CONFIRMATION_DIGIT) )
    {
      $SIPCMD_CONFIRMATION_DIGIT = $SIPCMD_CONFIRMATION_DIGIT;
    }
    else
    {
      $SIPCMD_CONFIRMATION_DIGIT = "-";
    };

    if ( "$SIPCMD_MSINFO" <> "" || "$SIPCMD_MSINFO" == "tts" )
    {
	  if ( "$SIPCMD_MSINFO" == "tts" )
	  {
		debug('DBG_TTS_OPTION_USED',"", 7);
		$msinfo = "";
		$retval = 1;
	  }
	  else
	  {
		$cmd = '/usr/bin/wget -a "'.$pluginlogfile.'" --retry-connrefused --tries=2 --waitretry=1 --timeout=1 --passive-ftp -nH -qO- "'.$SIPCMD_MSINFO.'" 2>&1|grep value|cut -d\" -f4';
		debug('DBG_ADD_CMD_TO_JOB',$cmd,4);
		$msinfo = exec( $cmd, $output , $retval);
	  }
      if ($retval <> 0 || $msinfo == "")
      {
        if (isset($_REQUEST["tts"])) { $unknown = $_REQUEST["tts"]; }
		if ( "$SIPCMD_MSINFO" == "tts" )
		{
			debug( 'DBG_TTS_OPTION_USED',$_REQUEST["tts"], 7);
		}
		else
		{
			debug( $plugin_phrase_array['ERROR0006'], " $SIPCMD_MSINFO ", 4);
		}
        $P2W_Text = str_replace("##", $unknown, $P2W_Text);
      }
      else
      {
        debug ( $plugin_phrase_array['TXT_SIPCMD_READ_MS_STATE']," $msinfo \n", 6);
        $P2W_Text = str_replace("##", $msinfo, $P2W_Text);
      }
    }
	
	#********************** Added/changed by OL ***********************************
	$plugins = LBSystem::get_plugins();
	# Text-2-Speech Plugin Name from Plugins DB
	$T2SPlugin = "Text-2-Speech";
	$T2S_INSTALLED = "false";
	$minreleaset2s = "1.2.1";
	# check if Text-2-Speech Plugin is installed
	foreach($plugins as $plugin) {
		if ($plugin['PLUGINDB_TITLE'] == $T2SPlugin) {
			# check if min Version of Text-2-Speech is installed
			if ($plugin['PLUGINDB_VERSION'] >= $minreleaset2s) {
				$T2S_INSTALLED = "true";
			}
		}
	}
	$T2S_USE = $plugin_cfg_array['T2S_USE'];
	if ($T2S_INSTALLED == "false" or $T2S_USE == "") {
		usepico();
	} else {
		uset2s();
	}
	#*******************************************************************************
	
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



#********************** Added by OL ***********************************
/**
/* Funktion : usepico --> Use Pico to create voice
/*
/* @param: 	none
/* @return: empty
**/	

function usepico()   {
	
	global $pluginjobfile, $cmd, $pico2wave, $P2W_lang, $plugintmpfile, $P2W_Text, $pluginlogfile, $sox, $pluginwavfile, $pluginjobfile_handle;
	
	debug('DBG_CREATE_JOB',$pluginjobfile,6);
	$cmd = $pico2wave . ' -l "'.$P2W_lang.'" -w "'.$plugintmpfile.'" "'.$P2W_Text.'" 2>&1 >>'.$pluginlogfile;
	fwrite($pluginjobfile_handle, "$cmd \n");
	return;
}



/**
/* Funktion : uset2s --> Use Text-2-Speech Interface to create voice
/*
/* @param: 	none
/* @return: empty
**/	

function uset2s()   {
	
	global $pluginjobfile, $plugintmpfile, $P2W_Text, $pluginlogfile, $sox, $pluginwavfile, $lame, $ttsfile, $pluginjobfile_handle, $cmd;
	
	debug('DBG_CREATE_JOB',$pluginjobfile,6);
	$jsonstr = t2s_post_request($P2W_Text);
	$json = json_decode($jsonstr, True);
	# Additional Error handling if something went wrong during Text-2-speech Voice file creation
	if ($json['success'] != "1")  {
		error_log( date('Y-m-d H:i:s ').$plugin_phrase_array['DBG_ADD_CMD_TO_JOB'].$json['warning']."\n", 3, $pluginlogfile);
		error_log( date('Y-m-d H:i:s ').$plugin_phrase_array['DBG_ADD_CMD_TO_JOB']."Fall back to Pico\n", 3, $pluginlogfile);
		debug('DBG_ADD_CMD_TO_JOB',$pluginjobfile,6);
		$cmd = $json['warning'].' >>'.$pluginlogfile;
		fwrite($pluginjobfile_handle, "$cmd \n");
		$cmd = 'Fall back to Pico >>'.$pluginlogfile;
		fwrite($pluginjobfile_handle, "$cmd \n");
		# Fall back to Pico
		usepico();
    } 
	$ttsfile = $json['fullttspath'];
	debug('DBG_CREATE_JOB',$pluginjobfile,6);
	$cmd = exec($lame.' --decode '.$ttsfile.' '.$plugintmpfile).' 2>&1 >>'.$pluginlogfile;
	fwrite($pluginjobfile_handle, "$cmd \n");
	return;
}
	
	
	
/**
/* Funktion : t2s_post_request --> generiert einen POST request zum text2speech Plugin
/*
/* @param: 	$text, $greet, $lbplogdir, $plugindata, $pluginlogfile
/* @return: JSON Array
**/	

function t2s_post_request($P2W_Text)   {
	
	global $plugindir, $lbplogdir, $plugindata, $pluginlogfile;
	#echo '<PRE>';
	
	$myIP = LBSystem::get_localip();
	
	// Url
	$url = 'http://'.$myIP.'/plugins/text2speech/index.php';
		
	// Initiate cURL.
	$ch = curl_init($url);
	
	$greet = "0";
	 
	// populate JSON data.
	$jsonData = array(
		'text' => $P2W_Text,
		'greet' => $greet,
		'plugindir' => $plugindata['PLUGINDB_FOLDER'],
		'pluginlogdir' => $lbplogdir,
		'pluginlogfile' => $pluginlogfile
	);
		 
	// Encode the array into JSON.
	$jsonDataEncoded = json_encode($jsonData);
				 
	// Tell cURL that we want to send a POST request.
	curl_setopt($ch, CURLOPT_POST, 1);
	 
	// Attach our encoded JSON string to the POST fields.
	curl_setopt($ch, CURLOPT_POSTFIELDS, $jsonDataEncoded);
	 
	// Set the content type to application/json
	curl_setopt($ch, CURLOPT_HTTPHEADER, array('Content-Type: application/json')); 
	
	// Request response from Call
	curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
		 
	// Execute the request
	$result = curl_exec($ch);
	
	#print_r(json_decode($result));
	// was the request successful?
	if($result === false)  {
		error_log( date('Y-m-d H:i:s ')." POST Request wasn't successfull\n", 3, $pluginlogfile);
	} else {
		error_log( date('Y-m-d H:i:s ')." POST Request was successfull. Data has been returned.\n", 5, $pluginlogfile);
	}
	// close cURL
	curl_close($ch);
	return $result;
}
#**********************************************************************

header('Content-Type: text/plain; charset=utf-8');
echo "$result";
exit;
